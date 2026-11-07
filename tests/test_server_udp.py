"""Testes de integração do servidor UDP de votação."""

import socket
import threading
import unittest

from src.server_udp import atender_datagramas
from src.voting import Voting


class UDPServerTests(unittest.TestCase):
    def setUp(self):
        self.votacao = Voting(60)
        self.votacao.iniciar_votacao()
        self.servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.servidor.bind(("127.0.0.1", 0))
        self.servidor.settimeout(0.1)
        self.endereco = self.servidor.getsockname()
        self.thread = threading.Thread(
            target=atender_datagramas,
            args=(self.servidor,),
            kwargs={"votacao": self.votacao},
            daemon=True,
        )
        self.thread.start()
        self.clientes = []

    def tearDown(self):
        for cliente in self.clientes:
            cliente.close()
        self.servidor.close()
        self.thread.join(timeout=2)

    def novo_cliente(self):
        cliente = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cliente.bind(("127.0.0.1", 0))
        cliente.settimeout(2)
        self.clientes.append(cliente)
        return cliente

    def enviar_comando(self, cliente, mensagem):
        cliente.sendto(mensagem.encode("utf-8"), self.endereco)

    @staticmethod
    def receber(cliente):
        dados, _ = cliente.recvfrom(4096)
        return dados.decode("utf-8").rstrip("\n")

    def test_multiplos_clientes_recebem_resposta_e_update_no_endereco_correto(self):
        ana = self.novo_cliente()
        bia = self.novo_cliente()
        self.enviar_comando(ana, "JOIN ana")
        self.enviar_comando(bia, "JOIN bia")
        self.assertEqual(self.receber(ana), "SUCCESS")
        self.assertEqual(self.receber(bia), "SUCCESS")

        self.enviar_comando(ana, "VOTE A")
        # A resposta e a atualização chegam somente ao remetente correto,
        # enquanto a atualização também é encaminhada ao outro cliente.
        self.assertEqual(self.receber(ana), "SUCCESS")
        self.assertEqual(self.receber(ana), "UPDATE A:1 B:0 C:0")
        self.assertEqual(self.receber(bia), "UPDATE A:1 B:0 C:0")
        self.assertEqual(self.votacao.obter_resultados(), {"A": 1, "B": 0, "C": 0})

    def test_cliente_invalido_nao_interrompe_atendimento_dos_demais(self):
        ana = self.novo_cliente()
        bia = self.novo_cliente()
        ana.sendto(b"\xff", self.endereco)
        self.enviar_comando(bia, "JOIN bia\nVOTE C")

        self.assertEqual(self.receber(bia), "SUCCESS")
        self.assertEqual(self.receber(bia), "SUCCESS")
        self.assertEqual(self.receber(bia), "UPDATE A:0 B:0 C:1")
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 1})

    def test_vote_sem_join_e_rejeitado(self):
        cliente = self.novo_cliente()

        self.enviar_comando(cliente, "VOTE A")

        self.assertEqual(
            self.receber(cliente),
            "ERROR Identifique-se com JOIN antes de votar.",
        )
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 0})

    def test_identificador_nao_pode_ser_associado_a_outro_endereco(self):
        ana = self.novo_cliente()
        outro_endereco = self.novo_cliente()

        self.enviar_comando(ana, "JOIN ana")
        self.assertEqual(self.receber(ana), "SUCCESS")

        self.enviar_comando(outro_endereco, "JOIN ana")
        self.assertEqual(
            self.receber(outro_endereco),
            "ERROR Este identificador já está associado a outro endereço.",
        )

        self.enviar_comando(outro_endereco, "VOTE B")
        self.assertEqual(
            self.receber(outro_endereco),
            "ERROR Identifique-se com JOIN antes de votar.",
        )
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 0})

    def test_opcao_invalida_e_voto_duplicado_nao_alteram_resultados(self):
        cliente = self.novo_cliente()
        self.enviar_comando(cliente, "JOIN ana")
        self.assertEqual(self.receber(cliente), "SUCCESS")

        self.enviar_comando(cliente, "VOTE D")
        self.assertTrue(self.receber(cliente).startswith("ERROR Opção inválida"))
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 0})

        self.enviar_comando(cliente, "VOTE A")
        self.assertEqual(self.receber(cliente), "SUCCESS")
        self.assertEqual(self.receber(cliente), "UPDATE A:1 B:0 C:0")

        self.enviar_comando(cliente, "VOTE B")
        self.assertTrue(self.receber(cliente).startswith("ERROR Este identificador já votou."))
        self.assertEqual(self.votacao.obter_resultados(), {"A": 1, "B": 0, "C": 0})


if __name__ == "__main__":
    unittest.main()
