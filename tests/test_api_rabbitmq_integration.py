"""End-to-end tests against a real HTTP API process and RabbitMQ broker.

These tests intentionally do not patch the API's publisher or broker client.
"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from urllib.error import URLError
from urllib.request import Request, urlopen

import pika

from src.services.broker import EXCHANGE_NAME


STARTUP_TIMEOUT = 20
EVENT_TIMEOUT = 3


class ApiRabbitMqIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rabbitmq_url = os.getenv(
            "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        # Fail early with a direct, actionable error if RabbitMQ is unavailable.
        cls._check_broker()

    @classmethod
    def _check_broker(cls):
        connection = pika.BlockingConnection(pika.URLParameters(cls.rabbitmq_url))
        try:
            connection.channel().exchange_declare(
                exchange=EXCHANGE_NAME, exchange_type="fanout"
            )
        finally:
            connection.close()

    def setUp(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["RABBITMQ_URL"] = self.rabbitmq_url
        self.api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.controllers.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self._stop_api)
        self._wait_for_api()

    def _stop_api(self):
        if self.api.poll() is None:
            self.api.terminate()
            try:
                self.api.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.api.kill()
                self.api.wait(timeout=5)

    def _wait_for_api(self):
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self.api.poll() is not None:
                self.fail(f"API process exited with status {self.api.returncode}")
            try:
                with urlopen(f"{self.base_url}/health", timeout=0.5) as response:
                    if response.status == 200:
                        return
            except (OSError, URLError):
                time.sleep(0.05)
        self.fail("API did not become healthy before timeout")

    def _post_vote(self, voter, option):
        request = Request(
            f"{self.base_url}/sessoes/entrega1/votos",
            data=json.dumps({"eleitor_id": voter, "opcao": option}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except Exception as error:
            # urllib raises HTTPError for expected 4xx responses; preserve its body.
            from urllib.error import HTTPError

            if isinstance(error, HTTPError):
                return error.code, json.loads(error.read())
            raise

    def _post_vote_after_barrier(self, barrier, voter, option):
        barrier.wait(timeout=5)
        return self._post_vote(voter, option)

    def _subscriber(self):
        connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
        channel = connection.channel()
        queue = channel.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=queue)
        return connection, channel, queue

    def _next_event(self, channel, queue, timeout=EVENT_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            method, _properties, body = channel.basic_get(queue=queue, auto_ack=True)
            if method is not None:
                return json.loads(body)
            time.sleep(0.02)
        return None

    def _assert_no_event(self, channel, queue):
        self.assertIsNone(self._next_event(channel, queue, timeout=0.4))

    def _assert_two_plausible_concurrent_events(self, events):
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event is not None for event in events))
        final_score = {"A": 1, "B": 1, "C": 0}
        plausible_scores = (
            {"A": 1, "B": 0, "C": 0},
            {"A": 0, "B": 1, "C": 0},
            final_score,
        )
        scores = [event["placar"] for event in events]
        self.assertTrue(all(score in plausible_scores for score in scores))
        for earlier, later in zip(scores, scores[1:]):
            self.assertTrue(
                all(earlier[option] <= later[option] for option in earlier)
            )
        self.assertEqual(scores[-1], final_score)
        self.assertTrue(all(event["sessao_id"] == "entrega1" for event in events))
        self.assertTrue(
            all(
                datetime.fromisoformat(event["data_hora"]).utcoffset().total_seconds() == 0
                for event in events
            )
        )

    def test_simultaneous_votes_from_distinct_voters_publish_current_scores(self):
        connection, channel, queue = self._subscriber()
        self.addCleanup(connection.close)

        with ThreadPoolExecutor(max_workers=2) as executor:
            barrier = Barrier(2)
            futures = [
                executor.submit(self._post_vote_after_barrier, barrier, "ana", "A"),
                executor.submit(self._post_vote_after_barrier, barrier, "bia", "B"),
            ]
            responses = [future.result(timeout=8) for future in futures]

        self.assertEqual([status for status, _ in responses], [201, 201])
        response_scores = {
            tuple(sorted(body["placar"].items())) for _, body in responses
        }
        final_score = (("A", 1), ("B", 1), ("C", 0))
        intermediate_scores = {
            (("A", 1), ("B", 0), ("C", 0)),
            (("A", 0), ("B", 1), ("C", 0)),
        }
        self.assertEqual(len(response_scores), 2)
        self.assertIn(final_score, response_scores)
        self.assertTrue(
            (response_scores - {final_score}).issubset(intermediate_scores)
        )
        events = [self._next_event(channel, queue) for _ in range(2)]
        self._assert_two_plausible_concurrent_events(events)
        self._assert_no_event(channel, queue)

    def test_simultaneous_repeated_vote_has_one_acceptance_and_one_event(self):
        connection, channel, queue = self._subscriber()
        self.addCleanup(connection.close)

        with ThreadPoolExecutor(max_workers=2) as executor:
            barrier = Barrier(2)
            futures = [
                executor.submit(
                    self._post_vote_after_barrier, barrier, "mesmo-eleitor", "A"
                ),
                executor.submit(
                    self._post_vote_after_barrier, barrier, "mesmo-eleitor", "B"
                ),
            ]
            responses = [future.result(timeout=8) for future in futures]

        self.assertEqual(sorted(status for status, _ in responses), [201, 409])
        rejected = next(body for status, body in responses if status == 409)
        self.assertEqual(rejected["detail"]["codigo"], "voto_duplicado")
        accepted = next(body for status, body in responses if status == 201)
        event = self._next_event(channel, queue)
        self.assertIsNotNone(event)
        self.assertEqual(event["placar"], accepted["placar"])
        self.assertEqual(sum(event["placar"].values()), 1)
        self._assert_no_event(channel, queue)

    def test_fanout_delivers_each_vote_to_multiple_subscribers(self):
        subscribers = [self._subscriber(), self._subscriber()]
        self.addCleanup(lambda: [connection.close() for connection, _, _ in subscribers])

        status, response = self._post_vote("ana", "C")
        self.assertEqual(status, 201)
        self.assertEqual(response["placar"], {"A": 0, "B": 0, "C": 1})

        events = [
            self._next_event(channel, queue)
            for _, channel, queue in subscribers
        ]
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event is not None for event in events))
        self.assertEqual(events[0], events[1])
        self.assertEqual(events[0]["placar"], response["placar"])
        for _, channel, queue in subscribers:
            self._assert_no_event(channel, queue)

    def test_rejected_votes_do_not_change_score_or_publish(self):
        connection, channel, queue = self._subscriber()
        self.addCleanup(connection.close)

        invalid_status, invalid = self._post_vote("bia", "Z")
        self.assertEqual(invalid_status, 400)
        self.assertEqual(invalid["detail"]["codigo"], "opcao_invalida")
        self._assert_no_event(channel, queue)

        accepted_status, accepted = self._post_vote("bia", "A")
        self.assertEqual(accepted_status, 201)
        self.assertEqual(accepted["placar"], {"A": 1, "B": 0, "C": 0})
        event = self._next_event(channel, queue)
        self.assertIsNotNone(event)
        self.assertEqual(event["placar"], accepted["placar"])

        duplicate_status, duplicate = self._post_vote("bia", "B")
        self.assertEqual(duplicate_status, 409)
        self.assertEqual(duplicate["detail"]["codigo"], "voto_duplicado")
        self._assert_no_event(channel, queue)

        next_status, next_vote = self._post_vote("carla", "B")
        self.assertEqual(next_status, 201)
        self.assertEqual(next_vote["placar"], {"A": 1, "B": 1, "C": 0})
        event = self._next_event(channel, queue)
        self.assertIsNotNone(event)
        self.assertEqual(event["placar"], next_vote["placar"])
        self._assert_no_event(channel, queue)


if __name__ == "__main__":
    unittest.main()
