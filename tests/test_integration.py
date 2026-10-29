import queue
import socket
import threading
import unittest

from src.server import atender_conexoes


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.recebidos = queue.Queue()
        self.thread_ids = set()
        self.thread_ids_lock = threading.Lock()
        self.servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.servidor.bind(("127.0.0.1", 0))
        self.servidor.listen()
        self.servidor.settimeout(0.1)
        self.thread_servidor = threading.Thread(
            target=atender_conexoes,
            args=(self.servidor, self.processar),
            daemon=True,
        )
        self.thread_servidor.start()
        self.endereco = self.servidor.getsockname()

    def processar(self, dados):
        with self.thread_ids_lock:
            self.thread_ids.add(threading.get_ident())
        self.recebidos.put(dados)

    def tearDown(self):
        self.servidor.close()
        self.thread_servidor.join(timeout=2)

    def conectar(self):
        cliente = socket.create_connection(self.endereco, timeout=2)
        cliente.settimeout(2)
        return cliente

    def test_recebe_bytes_e_os_entrega_ao_processador(self):
        with self.conectar() as cliente:
            payload = b"dados arbitrarios\x00 sem protocolo"
            cliente.sendall(payload)
            self.assertEqual(self.recebidos.get(timeout=2), payload)

    def test_atende_clientes_concorrentes_em_threads_separadas(self):
        clientes = [self.conectar() for _ in range(3)]
        try:
            for indice, cliente in enumerate(clientes):
                cliente.sendall(bytes([65 + indice]))
            self.assertEqual(
                {self.recebidos.get(timeout=2) for _ in clientes}, {b"A", b"B", b"C"}
            )
            self.assertEqual(len(self.thread_ids), len(clientes))
        finally:
            for cliente in clientes:
                cliente.close()

    def test_desconexao_nao_impede_atendimento_de_outro_cliente(self):
        desconectado = self.conectar()
        desconectado.close()
        with self.conectar() as cliente:
            cliente.sendall(b"ainda ativo")
            self.assertEqual(self.recebidos.get(timeout=2), b"ainda ativo")


if __name__ == "__main__":
    unittest.main()
