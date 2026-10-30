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
            mensagem = "dados arbitrarios\x00 sem protocolo"
            cliente.sendall(mensagem.encode("utf-8") + b"\n")
            self.assertEqual(self.recebidos.get(timeout=2), mensagem)

    def test_atende_clientes_concorrentes_em_threads_separadas(self):
        clientes = [self.conectar() for _ in range(3)]
        try:
            for indice, cliente in enumerate(clientes):
                cliente.sendall(bytes([65 + indice]) + b"\n")
            self.assertEqual(
                {self.recebidos.get(timeout=2) for _ in clientes}, {"A", "B", "C"}
            )
            self.assertEqual(len(self.thread_ids), len(clientes))
        finally:
            for cliente in clientes:
                cliente.close()

    def test_desconexao_nao_impede_atendimento_de_outro_cliente(self):
        desconectado = self.conectar()
        desconectado.close()
        with self.conectar() as cliente:
            cliente.sendall(b"ainda ativo\n")
            self.assertEqual(self.recebidos.get(timeout=2), "ainda ativo")

    def test_processa_join_vote_fragmentados_e_update_agrupados_com_utf8(self):
        with self.conectar() as cliente:
            mensagens = ["JOIN ana", "VOTE A", "UPDATE A:2 B:1 C:0", "NOTICE café 🗳️"]
            payload = "\n".join(mensagens).encode("utf-8") + b"\n"
            corte = payload.index("é".encode("utf-8")) + 1
            cliente.sendall(payload[:corte])
            cliente.sendall(payload[corte:])

            self.assertEqual([self.recebidos.get(timeout=2) for _ in mensagens], mensagens)

    def test_entrega_join_vote_e_outras_mensagens_completas(self):
        mensagens = ["JOIN ana", "VOTE A", "UPDATE A:2 B:1 C:0", "PING"]
        with self.conectar() as cliente:
            cliente.sendall(b"".join(mensagem.encode("utf-8") + b"\n" for mensagem in mensagens))

            self.assertEqual(
                [self.recebidos.get(timeout=2) for _ in mensagens], mensagens
            )

    def test_desconexao_entrega_mensagem_final_sem_newline(self):
        cliente = self.conectar()
        cliente.sendall("NOTICE final=ão".encode("utf-8"))
        cliente.shutdown(socket.SHUT_WR)
        cliente.close()

        self.assertEqual(self.recebidos.get(timeout=2), "NOTICE final=ão")


if __name__ == "__main__":
    unittest.main()
