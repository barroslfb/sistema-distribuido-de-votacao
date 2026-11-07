import socket
import threading
import time
import unittest

from src.server import atender_conexoes
from src.voting import Voting


class VotingTCPTests(unittest.TestCase):
    def setUp(self):
        self.voting = Voting(10)
        self.voting.iniciar_votacao()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.server.settimeout(0.05)
        self.clients = []
        self.thread = threading.Thread(
            target=atender_conexoes,
            args=(self.server,),
            kwargs={"votacao": self.voting},
            daemon=True,
        )
        self.thread.start()

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.close()
        self.thread.join(timeout=2)

    def connect(self, identifier):
        client = socket.create_connection(self.server.getsockname(), timeout=2)
        client.settimeout(2)
        self.clients.append(client)
        self.send(client, f"JOIN {identifier}")
        self.assertEqual(self.read_line(client), "SUCCESS")
        return client

    @staticmethod
    def send(client, command):
        client.sendall(f"{command}\n".encode())

    @staticmethod
    def read_line(client):
        data = bytearray()
        while not data.endswith(b"\n"):
            block = client.recv(1)
            if not block:
                raise AssertionError("conexão encerrada antes da mensagem completa")
            data.extend(block)
        return data.decode().rstrip("\r\n")

    def test_update_do_voto_valido_chega_a_todos_os_participantes(self):
        voter = self.connect("ana")
        participant = self.connect("bia")

        self.send(voter, "VOTE B")
        self.assertEqual(self.read_line(voter), "SUCCESS")
        update = "UPDATE A:0 B:1 C:0"
        self.assertEqual(self.read_line(voter), update)
        self.assertEqual(self.read_line(participant), update)
        self.assertEqual(self.voting.obter_resultados(), {"A": 0, "B": 1, "C": 0})

    def test_end_e_broadcastado_por_prazo_sem_novos_comandos(self):
        first = self.connect("ana")
        second = self.connect("bia")
        self.voting._prazo_final = time.monotonic() + 0.1

        end = "END A:0 B:0 C:0"
        self.assertEqual(self.read_line(first), end)
        self.assertEqual(self.read_line(second), end)
        self.assertEqual(self.voting.obter_resultados(), {"A": 0, "B": 0, "C": 0})


if __name__ == "__main__":
    unittest.main()
