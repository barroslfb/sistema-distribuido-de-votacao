"""Critérios da feature 4, incluindo concorrência e sockets TCP reais."""

import socket
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src.server import atender_conexoes
from src.voting import Voting


class VoteRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.votacao = Voting(300)
        self.votacao.iniciar_votacao()

    def test_registra_uma_opcao_por_participante(self):
        for participante, opcao in (("ana", "A"), ("bia", "B"), ("caio", "C")):
            self.votacao.registro_voto(opcao, participante)
        self.assertEqual(self.votacao.obter_resultados(), {"A": 1, "B": 1, "C": 1})

    def test_duplicado_nao_substitui_nem_incrementa_voto(self):
        self.votacao.registro_voto("A", "ana")
        with self.assertRaisesRegex(ValueError, "já votou"):
            self.votacao.registro_voto("B", "ana")
        self.assertEqual(self.votacao.obter_resultados(), {"A": 1, "B": 0, "C": 0})

    def test_invalidos_nao_consumem_direito_de_votar(self):
        for opcao in ("D", "a", "A B", "", None, ["A"]):
            with self.subTest(opcao=opcao), self.assertRaises(ValueError):
                self.votacao.registro_voto(opcao, "ana")
        for participante in (None, "", "ana bia", "ana\n", 7):
            with self.subTest(participante=participante), self.assertRaises(ValueError):
                self.votacao.registro_voto("A", participante)
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 0})
        self.votacao.registro_voto("C", "ana")
        self.assertEqual(self.votacao.obter_resultados()["C"], 1)

    def test_prazo_rejeita_novo_voto_sem_alterar_contagem(self):
        votacao = Voting(10)
        with patch("src.voting.time.monotonic", side_effect=[100, 109, 110]):
            votacao.iniciar_votacao()
            votacao.registro_voto("A", "ana")
            with self.assertRaises(RuntimeError):
                votacao.registro_voto("B", "bia")
        self.assertEqual(votacao.obter_resultados(), {"A": 1, "B": 0, "C": 0})

    def test_requisicoes_simultaneas_do_mesmo_id_aceitam_so_um_voto(self):
        barreira = threading.Barrier(16)

        def votar(indice):
            barreira.wait(timeout=5)
            try:
                self.votacao.registro_voto("ABC"[indice % 3], "ana")
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=16) as executor:
            aceitos = list(executor.map(votar, range(16)))
        self.assertEqual(sum(aceitos), 1)
        self.assertEqual(sum(self.votacao.obter_resultados().values()), 1)

    def test_participantes_concorrentes_nao_perdem_votos(self):
        with ThreadPoolExecutor(max_workers=16) as executor:
            list(executor.map(
                lambda indice: self.votacao.registro_voto("A", f"id{indice}"), range(100)
            ))
        self.assertEqual(self.votacao.obter_resultados(), {"A": 100, "B": 0, "C": 0})

    def test_resultados_retornados_sao_uma_copia(self):
        copia = self.votacao.obter_resultados()
        copia["A"] = 999
        self.assertEqual(self.votacao.obter_resultados()["A"], 0)


class VotingTCPTests(unittest.TestCase):
    def setUp(self):
        self.votacao = Voting(300)
        self.votacao.iniciar_votacao()
        self.servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servidor.bind(("127.0.0.1", 0))
        self.servidor.listen()
        self.servidor.settimeout(0.1)
        self.endereco = self.servidor.getsockname()
        self.thread = threading.Thread(
            target=atender_conexoes,
            args=(self.servidor,), kwargs={"votacao": self.votacao}, daemon=True
        )
        self.thread.start()

    def tearDown(self):
        self.servidor.close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def trocar(self, comandos):
        with socket.create_connection(self.endereco, timeout=3) as cliente:
            with cliente.makefile("rb") as respostas:
                cliente.sendall(comandos)
                resultado = []
                for comando in comandos.splitlines():
                    resposta = respostas.readline().decode("utf-8").strip()
                    while resposta.startswith(("UPDATE ", "END ")):
                        # Eventos de broadcast podem preceder a resposta do
                        # próprio comando em sockets usados concorrentemente.
                        resposta = respostas.readline().decode("utf-8").strip()
                    resultado.append(resposta)
                return resultado

    def test_confirmacao_erro_e_reconexao_com_mesmo_id(self):
        self.assertEqual(self.trocar(b"JOIN ana\nVOTE A\n"), ["SUCCESS", "SUCCESS"])
        respostas = self.trocar(b"JOIN ana\nVOTE B\n")
        self.assertEqual(respostas[0], "SUCCESS")
        self.assertIn("já votou", respostas[1])
        self.assertEqual(self.votacao.obter_resultados(), {"A": 1, "B": 0, "C": 0})

    def test_comandos_invalidos_e_troca_de_id_na_mesma_conexao(self):
        respostas = self.trocar(
            b"VOTE A\nJOIN\nJOIN ana bia\nJOIN ana\nJOIN bia\n"
            b"VOTE A B\nVOTE D\nPING x\nVOTE C\nVOTE A\n"
        )
        self.assertEqual([r.split()[0] for r in respostas],
                         ["ERROR", "ERROR", "ERROR", "SUCCESS", "ERROR",
                          "ERROR", "ERROR", "ERROR", "SUCCESS", "ERROR"])
        self.assertEqual(self.votacao.obter_resultados(), {"A": 0, "B": 0, "C": 1})

    def test_voto_fragmentado_so_recebe_resposta_quando_completo(self):
        with socket.create_connection(self.endereco, timeout=3) as cliente:
            with cliente.makefile("rb") as respostas:
                cliente.sendall(b"JOIN ana\nVO")
                self.assertEqual(respostas.readline(), b"SUCCESS\n")
                cliente.sendall(b"TE B\n")
                self.assertEqual(respostas.readline(), b"SUCCESS\n")
        self.assertEqual(self.votacao.obter_resultados()["B"], 1)

    def test_dois_sockets_com_mesmo_id_disputam_um_unico_voto(self):
        barreira = threading.Barrier(2)

        def votar(opcao):
            barreira.wait(timeout=3)
            return self.trocar(f"JOIN ana\nVOTE {opcao}\n".encode())[1]

        with ThreadPoolExecutor(max_workers=2) as executor:
            respostas = list(executor.map(votar, ("A", "B")))
        self.assertEqual(respostas.count("SUCCESS"), 1)
        self.assertEqual(sum(r.startswith("ERROR") for r in respostas), 1)
        self.assertEqual(sum(self.votacao.obter_resultados().values()), 1)

    def test_votacao_encerrada_responde_erro_pelo_socket(self):
        self.votacao.encerrar_votacao()
        respostas = self.trocar(b"JOIN ana\nVOTE A\n")
        self.assertTrue(respostas[1].startswith("ERROR"))
        self.assertEqual(sum(self.votacao.obter_resultados().values()), 0)


if __name__ == "__main__":
    unittest.main()
