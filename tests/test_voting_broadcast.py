import select
import socket
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from src.server import atender_cliente, atender_conexoes
from src.voting import Voting


class VotingBroadcastTests(unittest.TestCase):
    def setUp(self):
        self.clients = []
        self.server = None
        self.server_thread = None

    def start_server(self, duration=10):
        self.voting = Voting(duration)
        self.voting.iniciar_votacao()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.server.settimeout(0.05)
        self.server_thread = threading.Thread(
            target=atender_conexoes,
            args=(self.server,),
            kwargs={"votacao": self.voting},
            daemon=True,
        )
        self.server_thread.start()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        if self.server is not None:
            self.server.close()
        if self.server_thread is not None:
            self.server_thread.join(timeout=2)
            self.assertFalse(self.server_thread.is_alive())

    def connect(self, identifier):
        client = socket.create_connection(self.server.getsockname(), timeout=2)
        client.settimeout(2)
        self.clients.append(client)
        client.sendall(f"JOIN {identifier}\n".encode())
        self.assertEqual(self.read_line(client), "SUCCESS")
        return client

    @staticmethod
    def read_line(client):
        data = bytearray()
        while not data.endswith(b"\n"):
            block = client.recv(1)
            if not block:
                raise AssertionError("socket encerrou antes da mensagem completa")
            data.extend(block)
        return data.decode("utf-8").rstrip("\r\n")

    def assert_no_message(self, client):
        self.assertEqual(select.select([client], [], [], 0.1)[0], [])

    def test_update_e_enviado_a_todos_incluindo_votante(self):
        self.start_server()
        votante = self.connect("ana")
        observador = self.connect("bia")

        votante.sendall(b"VOTE B\n")
        self.assertEqual(self.read_line(votante), "SUCCESS")
        esperado = "UPDATE A:0 B:1 C:0"
        self.assertEqual(self.read_line(votante), esperado)
        self.assertEqual(self.read_line(observador), esperado)

    def test_voto_rejeitado_nao_emite_update_nem_altera_resultados(self):
        self.start_server()
        votante = self.connect("ana")
        observador = self.connect("bia")

        votante.sendall(b"VOTE A\n")
        self.assertEqual(self.read_line(votante), "SUCCESS")
        self.assertEqual(self.read_line(votante), "UPDATE A:1 B:0 C:0")
        self.assertEqual(self.read_line(observador), "UPDATE A:1 B:0 C:0")

        votante.sendall(b"VOTE C\n")
        self.assertTrue(self.read_line(votante).startswith("ERROR"))
        self.assert_no_message(votante)
        self.assert_no_message(observador)
        self.assertEqual(self.voting.obter_resultados(), {"A": 1, "B": 0, "C": 0})

    def test_end_e_broadcastado_no_encerramento_manual(self):
        self.start_server()
        a = self.connect("ana")
        b = self.connect("bia")
        a.sendall(b"VOTE C\n")
        self.assertEqual(self.read_line(a), "SUCCESS")
        self.assertEqual(self.read_line(a), "UPDATE A:0 B:0 C:1")
        self.assertEqual(self.read_line(b), "UPDATE A:0 B:0 C:1")

        self.voting.encerrar_votacao()
        esperado = "END A:0 B:0 C:1"
        self.assertEqual(self.read_line(a), esperado)
        self.assertEqual(self.read_line(b), esperado)

    def test_end_e_broadcastado_automaticamente_ao_expirar_prazo(self):
        self.start_server(duration=0.5)
        a = self.connect("ana")
        b = self.connect("bia")
        self.assertEqual(self.read_line(a), "END A:0 B:0 C:0")
        self.assertEqual(self.read_line(b), "END A:0 B:0 C:0")

    def test_votos_concorrentes_publicam_snapshots_na_mesma_ordem(self):
        self.start_server()
        clients = [self.connect(f"id{index}") for index in range(6)]

        def vote(index):
            clients[index].sendall(f"VOTE {'ABC'[index % 3]}\n".encode())

        with ThreadPoolExecutor(max_workers=len(clients)) as pool:
            list(pool.map(vote, range(len(clients))))

        updates_by_client = []
        for client in clients:
            messages = [self.read_line(client) for _ in range(len(clients) + 1)]
            self.assertEqual(messages.count("SUCCESS"), 1)
            updates = [message for message in messages if message.startswith("UPDATE ")]
            self.assertEqual(len(updates), len(clients))
            updates_by_client.append(updates)

        self.assertTrue(all(updates == updates_by_client[0] for updates in updates_by_client))
        totals = [sum(int(part.split(":")[1]) for part in update.split()[1:])
                  for update in updates_by_client[0]]
        self.assertEqual(totals, list(range(1, len(clients) + 1)))

    def test_atender_cliente_direto_sem_registro_de_clientes_broadcasta_update(self):
        voting = Voting(10)
        voting.iniciar_votacao()
        client, server = socket.socketpair()
        thread = threading.Thread(
            target=atender_cliente,
            args=(server, "local"),
            kwargs={"votacao": voting},
            daemon=True,
        )
        thread.start()
        try:
            client.sendall(b"JOIN ana\nVOTE A\n")
            self.assertEqual(self.read_line(client), "SUCCESS")
            self.assertEqual(self.read_line(client), "SUCCESS")
            self.assertEqual(self.read_line(client), "UPDATE A:1 B:0 C:0")
        finally:
            client.close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_falha_ao_enviar_success_nao_impede_broadcast_do_voto(self):
        voting = Voting(10)
        voting.iniciar_votacao()

        class BrokenReplyClient:
            def __init__(self):
                self.reads = iter((b"JOIN ana\n", b"VOTE B\n", b""))
                self.successes = 0

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def recv(self, _size):
                return next(self.reads)

            def sendall(self, data):
                if data == b"SUCCESS\n":
                    self.successes += 1
                    if self.successes == 2:
                        raise OSError("resposta TCP indisponível")

        broken = BrokenReplyClient()
        observer_server, observer_client = socket.socketpair()
        clients = {broken: threading.Lock(), observer_server: threading.Lock()}
        thread = threading.Thread(
            target=atender_cliente,
            args=(broken, "broken"),
            kwargs={"votacao": voting, "clientes": clients},
            daemon=True,
        )
        thread.start()
        observer_client.settimeout(2)
        try:
            self.assertEqual(self.read_line(observer_client), "UPDATE A:0 B:1 C:0")
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(voting.obter_resultados(), {"A": 0, "B": 1, "C": 0})
        finally:
            observer_server.close()
            observer_client.close()

    def test_servidor_fechado_encerra_thread_observadora(self):
        self.start_server(duration=10)
        self.server.close()
        self.server_thread.join(timeout=2)
        self.assertFalse(self.server_thread.is_alive())
        self.assertFalse(
            any(thread.name == "voting-deadline-observer" for thread in threading.enumerate())
        )


if __name__ == "__main__":
    unittest.main()
