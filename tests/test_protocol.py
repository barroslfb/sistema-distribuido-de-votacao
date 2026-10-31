import io
import socket
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src.client import executar_cliente, receber_mensagens
from src.protocol import NewlineFramer, encode_message
from src.server import SessaoVotacao
from src.voting import Voting


class NewlineFramerTests(unittest.TestCase):
    def test_fragmented_utf8_is_decoded_only_after_complete_line(self):
        framer = NewlineFramer()
        mensagem = "NOTICE João 🗳️"
        encoded = encode_message(mensagem)
        inicio_caractere = encoded.index("ã".encode("utf-8"))

        self.assertEqual(framer.feed(encoded[: inicio_caractere + 1]), [])
        self.assertEqual(framer.feed(encoded[inicio_caractere + 1 :]), [mensagem])
        self.assertIsNone(framer.finish())

    def test_grouped_messages_and_final_unterminated_message(self):
        framer = NewlineFramer()

        self.assertEqual(
            framer.feed(b"JOIN ana\nUPDATE A:2 B:1 C:0\r\nVOTE A"),
            ["JOIN ana", "UPDATE A:2 B:1 C:0"],
        )
        self.assertEqual(framer.finish(), "VOTE A")
        self.assertIsNone(framer.finish())

    def test_encode_message_appends_newline_and_rejects_invalid_input(self):
        self.assertEqual(encode_message("JOIN ana"), b"JOIN ana\n")
        with self.assertRaises(TypeError):
            encode_message(b"JOIN ana")
        with self.assertRaises(ValueError):
            encode_message("JOIN ana\nVOTE A")


class VotingCommandProtocolTests(unittest.TestCase):
    def setUp(self):
        self.votacao = Voting(10)
        self.votacao.iniciar_votacao()
        self.sessao = SessaoVotacao(self.votacao)

    def test_aceita_join_e_voto_validos(self):
        self.assertEqual(self.sessao.processar("JOIN ana"), "SUCCESS")
        self.assertEqual(self.sessao.processar("VOTE B"), "SUCCESS")
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 1, "C": 0})

    def test_rejeita_comandos_invalidos_e_voto_sem_identificacao(self):
        for mensagem in ("VOTE A", "JOIN", "JOIN ana bia", "PING x", "VOTE A B"):
            with self.subTest(mensagem=mensagem):
                self.assertTrue(self.sessao.processar(mensagem).startswith("ERROR"))

        self.assertEqual(self.sessao.processar("JOIN ana"), "SUCCESS")
        self.assertTrue(self.sessao.processar("VOTE D").startswith("ERROR"))
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 0})

    def test_rejeita_identificador_duplicado_e_voto_apos_encerramento(self):
        self.assertEqual(self.sessao.processar("JOIN ana"), "SUCCESS")
        self.assertEqual(self.sessao.processar("VOTE A"), "SUCCESS")
        self.assertTrue(self.sessao.processar("VOTE B").startswith("ERROR"))
        self.assertTrue(self.sessao.processar("JOIN bia").startswith("ERROR"))

        self.votacao.encerrar_votacao()
        outra_sessao = SessaoVotacao(self.votacao)
        self.assertEqual(outra_sessao.processar("JOIN bia"), "SUCCESS")
        self.assertTrue(outra_sessao.processar("VOTE C").startswith("ERROR"))
        self.assertEqual(self.votacao.obter_resultados(), {"A": 1, "B": 0, "C": 0})


class ClientReceptionTests(unittest.TestCase):
    def test_receives_update_and_other_messages_asynchronously(self):
        cliente, servidor = socket.socketpair()
        recebidas = []
        terminou = threading.Event()

        def ao_receber(mensagem):
            recebidas.append(mensagem)
            if mensagem == "NOTICE encerrado":
                terminou.set()

        receptor = threading.Thread(
            target=receber_mensagens, args=(cliente, ao_receber), daemon=True
        )
        receptor.start()
        try:
            servidor.sendall(
                encode_message("UPDATE A:2 B:1 C:0")
                + encode_message("NOTICE encerrado")
            )
            servidor.shutdown(socket.SHUT_WR)
            self.assertTrue(terminou.wait(timeout=2))
            receptor.join(timeout=2)
            self.assertFalse(receptor.is_alive())
            self.assertEqual(recebidas, ["UPDATE A:2 B:1 C:0", "NOTICE encerrado"])
        finally:
            cliente.close()
            servidor.close()

    def test_executar_cliente_envia_join_voto_recebe_update_e_desconecta(self):
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        servidor.settimeout(3)
        mensagens = []
        recebido_update = threading.Event()
        liberar_voto = threading.Event()
        cliente_terminou = threading.Event()
        erro_servidor = []

        def input_controlado(prompt=""):
            if prompt.strip() == "Identificador:":
                return "ana"
            if not liberar_voto.wait(timeout=3):
                raise TimeoutError("a votação não foi liberada")
            if not hasattr(input_controlado, "voto_enviado"):
                input_controlado.voto_enviado = True
                return "VOTE A"
            raise EOFError

        def ler_mensagem(conexao):
            dados = bytearray()
            while b"\n" not in dados:
                bloco = conexao.recv(1024)
                if not bloco:
                    break
                dados.extend(bloco)
            if b"\n" in dados:
                linha, _, restante = dados.partition(b"\n")
                mensagens.extend(item.decode("utf-8") for item in restante.splitlines())
                return linha.decode("utf-8")
            return dados.decode("utf-8")

        def atender_servidor():
            try:
                conexao, _ = servidor.accept()
                with conexao:
                    conexao.settimeout(3)
                    mensagens.append(ler_mensagem(conexao))
                    conexao.sendall(encode_message("UPDATE A:2 B:1 C:0"))
                    if not recebido_update.wait(timeout=3):
                        raise AssertionError("UPDATE não foi recebido enquanto input aguardava")
                    liberar_voto.set()
                    mensagens.append(ler_mensagem(conexao))
            except Exception as erro:
                erro_servidor.append(erro)
                liberar_voto.set()

        thread_servidor = threading.Thread(target=atender_servidor, daemon=True)
        thread_servidor.start()

        class SaidaSinalizada(io.StringIO):
            def write(self, texto):
                if "UPDATE A:2 B:1 C:0" in texto:
                    recebido_update.set()
                return super().write(texto)

        saida = SaidaSinalizada()

        def executar():
            try:
                executar_cliente("127.0.0.1", servidor.getsockname()[1])
            finally:
                cliente_terminou.set()

        try:
            with patch("builtins.input", side_effect=input_controlado), redirect_stdout(saida):
                thread_cliente = threading.Thread(target=executar, daemon=True)
                thread_cliente.start()
                thread_cliente.join(timeout=5)
            self.assertFalse(thread_cliente.is_alive(), "cliente não desconectou")
            thread_servidor.join(timeout=3)
            self.assertFalse(thread_servidor.is_alive(), "servidor de teste não terminou")
            self.assertFalse(erro_servidor, str(erro_servidor))
            self.assertTrue(cliente_terminou.is_set())
            self.assertEqual(mensagens, ["JOIN ana", "VOTE A"])
            self.assertIn("UPDATE A:2 B:1 C:0", saida.getvalue())
        finally:
            liberar_voto.set()
            servidor.close()


if __name__ == "__main__":
    unittest.main()
