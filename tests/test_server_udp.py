"""Testes de integração do servidor UDP de votação."""

import socket
import threading
import time
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

    def test_end_e_broadcastado_ao_expirar_prazo_sem_novos_votos(self):
        ana = self.novo_cliente()
        bia = self.novo_cliente()
        self.enviar_comando(ana, "JOIN ana")
        self.enviar_comando(bia, "JOIN bia")
        self.assertEqual(self.receber(ana), "SUCCESS")
        self.assertEqual(self.receber(bia), "SUCCESS")

        # Encurta o prazo da votação já iniciada para manter o teste rápido.
        self.votacao._prazo_final = time.monotonic() + 0.1

        esperado = "END A:0 B:0 C:0"
        self.assertEqual(self.receber(ana), esperado)
        self.assertEqual(self.receber(bia), esperado)
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 0})

    def test_falha_na_resposta_unicast_nao_impede_broadcast_do_voto(self):
        # Substitui o servidor do fixture por um adaptador que simula a perda
        # somente da resposta SUCCESS ao VOTE; os demais datagramas são reais.
        self.servidor.close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

        servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        servidor.bind(("127.0.0.1", 0))
        servidor.settimeout(0.1)
        self.servidor = servidor
        self.endereco = servidor.getsockname()

        class ServidorComFalhaUnicast:
            def __init__(self, socket_servidor):
                self.socket = socket_servidor
                self.endereco_votante = None
                self.falhar_proxima_resposta = False

            def recvfrom(self, tamanho):
                return self.socket.recvfrom(tamanho)

            def sendto(self, dados, endereco):
                if (
                    self.falhar_proxima_resposta
                    and endereco == self.endereco_votante
                    and dados == b"SUCCESS\n"
                ):
                    self.falhar_proxima_resposta = False
                    raise OSError("resposta unicast indisponível")
                return self.socket.sendto(dados, endereco)

        adaptador = ServidorComFalhaUnicast(servidor)
        self.thread = threading.Thread(
            target=atender_datagramas,
            args=(adaptador,),
            kwargs={"votacao": self.votacao},
            daemon=True,
        )
        self.thread.start()

        ana = self.novo_cliente()
        bia = self.novo_cliente()
        self.enviar_comando(ana, "JOIN ana")
        self.enviar_comando(bia, "JOIN bia")
        self.assertEqual(self.receber(ana), "SUCCESS")
        self.assertEqual(self.receber(bia), "SUCCESS")

        adaptador.endereco_votante = ana.getsockname()
        adaptador.falhar_proxima_resposta = True
        self.enviar_comando(ana, "VOTE B")

        esperado = "UPDATE A:0 B:1 C:0"
        self.assertEqual(self.receber(ana), esperado)
        self.assertEqual(self.receber(bia), esperado)
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 1, "C": 0})


if __name__ == "__main__":
    unittest.main()
