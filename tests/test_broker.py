import os
import unittest
from unittest.mock import Mock, patch

from src.services.broker import EXCHANGE_NAME, declare_voting_exchange


class RabbitMQConnectionTests(unittest.TestCase):
    @patch("src.services.broker.pika.BlockingConnection")
    @patch("src.services.broker.pika.URLParameters")
    def test_declares_fanout_exchange_then_closes_connection(
        self, url_parameters, blocking_connection
    ):
        url = "amqp://user:secret@broker:5672/votes"
        with patch.dict(os.environ, {"RABBITMQ_URL": url}):
            parameters = Mock()
            url_parameters.return_value = parameters
            connection = Mock()
            blocking_connection.return_value = connection

            declare_voting_exchange()

        url_parameters.assert_called_once_with(url)
        blocking_connection.assert_called_once_with(parameters)
        connection.channel.assert_called_once_with()
        connection.channel.return_value.exchange_declare.assert_called_once_with(
            exchange=EXCHANGE_NAME,
            exchange_type="fanout",
        )
        connection.close.assert_called_once_with()

    @patch("src.services.broker.pika.BlockingConnection", side_effect=OSError("broker unavailable"))
    @patch("src.services.broker.pika.URLParameters")
    def test_connection_failure_has_clear_error(self, url_parameters, _blocking_connection):
        with self.assertRaisesRegex(RuntimeError, "Não foi possível conectar ao RabbitMQ"):
            declare_voting_exchange()

    @patch("src.services.broker.pika.BlockingConnection")
    @patch("src.services.broker.pika.URLParameters")
    def test_declaration_failure_still_closes_connection(
        self, url_parameters, blocking_connection
    ):
        connection = Mock()
        connection.channel.return_value.exchange_declare.side_effect = OSError(
            "declaration rejected"
        )
        blocking_connection.return_value = connection

        with self.assertRaisesRegex(
            RuntimeError, "Não foi possível declarar a exchange 'apuracao.votos' \\(fanout\\)"
        ):
            declare_voting_exchange()

        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
