"""Testes do cliente UDP e do recebimento assíncrono de mensagens."""

import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

from src.client_udp import executar_cliente, main, receber_mensagens
from src.server_udp import atender_datagramas
from src.voting import Voting


class UDPClientTests(unittest.TestCase):
    def test_recebe_datagramas_utf8_e_mensagens_com_multiplas_linhas(self):
        cliente, emissor = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        mensagens = []
        receptor = threading.Thread(
            target=receber_mensagens, args=(cliente, mensagens.append), daemon=True
        )
        receptor.start()
        try:
            emissor.send("SUCCESS\nUPDATE café 🗳️\n".encode("utf-8"))
            # Espera pela mensagem e então encerra o receptor fechando seu socket.
            limite = time.monotonic() + 1
            while len(mensagens) < 2 and time.monotonic() < limite:
                time.sleep(0.005)
            self.assertEqual(mensagens, ["SUCCESS", "UPDATE café 🗳️"])
        finally:
            cliente.close()
            emissor.close()
            receptor.join(timeout=1)

    def test_envia_join_e_comando_digitado_uma_vez_cada(self):
        comandos = iter(("ana", "VOTE B"))
        enviados = []

        def entrada(*_args):
            try:
                return next(comandos)
            except StopIteration:
                raise EOFError

        class FakeSocket:
            def __init__(self, *_args):
                pass

            def connect(self, endereco):
                self.endereco = endereco

            def settimeout(self, _timeout):
                pass

            def send(self, dados):
                enviados.append(dados)
                return len(dados)

            def recv(self, _tamanho):
                raise OSError("socket fechado")

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        with patch("src.client_udp.socket.socket", FakeSocket), patch(
            "builtins.input", side_effect=entrada
        ):
            executar_cliente("localhost", 9876)

        self.assertEqual(enviados, [b"JOIN ana\n", b"VOTE B\n"])

    def test_integracao_udp_recebe_success_e_update_enquanto_input_aguarda(self):
        votacao = Voting(30)
        votacao.iniciar_votacao()
        servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        servidor.bind(("127.0.0.1", 0))
        servidor.settimeout(0.05)
        thread_servidor = threading.Thread(
            target=atender_datagramas,
            args=(servidor,),
            kwargs={"votacao": votacao},
            daemon=True,
        )
        thread_servidor.start()
        recebeu_vote = threading.Event()
        liberar_input = threading.Event()
        input_aguardando = threading.Event()
        mensagens = []
        chamadas = iter(("ana", "VOTE C"))

        def entrada(*_args):
            try:
                return next(chamadas)
            except StopIteration:
                input_aguardando.set()
                liberar_input.wait(2)
                raise EOFError

        def exibir(mensagem):
            mensagens.append(mensagem)
            if mensagem.startswith("UPDATE"):
                recebeu_vote.set()

        cliente = threading.Thread(
            target=lambda: executar_cliente(*servidor.getsockname()), daemon=True
        )
        try:
            with patch("builtins.input", side_effect=entrada), patch(
                "builtins.print", side_effect=exibir
            ):
                cliente.start()
                self.assertTrue(input_aguardando.wait(2))
                self.assertTrue(recebeu_vote.wait(2))
                self.assertIn("SUCCESS", mensagens)
                self.assertIn("UPDATE A:0 B:0 C:1", mensagens)
                self.assertEqual(votacao.obter_resultados(), {"A": 0, "B": 0, "C": 1})
            liberar_input.set()
            cliente.join(timeout=2)
            self.assertFalse(cliente.is_alive())
        finally:
            liberar_input.set()
            servidor.close()
            thread_servidor.join(timeout=2)

    def test_cli_aceita_host_porta_e_valida_intervalo(self):
        with patch("src.client_udp.executar_cliente") as executar:
            main(["--host", "192.0.2.10", "--port", "6000"])
            executar.assert_called_once_with("192.0.2.10", 6000)
        with patch("src.client_udp.executar_cliente") as executar:
            main([])
            executar.assert_called_once_with("127.0.0.1", 5001)
        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit):
                main(["--port", "70000"])


if __name__ == "__main__":
    unittest.main()
