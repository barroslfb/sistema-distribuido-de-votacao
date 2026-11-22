"""Regras de registro da Feature 14, usando a sessão da Feature 13."""
import unittest
from datetime import datetime, timedelta, timezone

from src.voting import VotingSession, VotoRejeitado


class VotingSessionVoteTests(unittest.TestCase):
    def setUp(self):
        self.inicio = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.fim = self.inicio + timedelta(minutes=5)
        self.sessao = VotingSession(["A", "B"], self.inicio, self.fim, "teste")

    def test_registro_atualiza_placar_e_eleitores(self):
        self.assertEqual(self.sessao.registrar_voto("ana", "A", self.inicio), {"A": 1, "B": 0})
        self.assertEqual(self.sessao.placar, {"A": 1, "B": 0})
        self.assertEqual(self.sessao.eleitores, {"ana"})

    def test_rejeicoes_seguem_ordem_e_preservam_estado(self):
        self.sessao.registrar_voto("ana", "A", self.inicio)
        anterior = self.sessao.obter_dados()
        for opcao, instante, codigo in (
            ("Z", self.fim, "opcao_invalida"),
            ("A", self.fim, "fora_do_prazo"),
            ("B", self.inicio, "voto_duplicado"),
        ):
            with self.subTest(codigo=codigo):
                with self.assertRaises(VotoRejeitado) as erro:
                    self.sessao.registrar_voto("ana", opcao, instante)
                self.assertEqual(erro.exception.codigo, codigo)
                self.assertEqual(self.sessao.obter_dados(), anterior)

    def test_limites_de_prazo(self):
        for instante in (self.inicio - timedelta(microseconds=1), self.fim,
                         self.fim + timedelta(microseconds=1)):
            with self.assertRaises(VotoRejeitado) as erro:
                self.sessao.registrar_voto("ana", "A", instante)
            self.assertEqual(erro.exception.codigo, "fora_do_prazo")
        self.assertEqual(self.sessao.eleitores, set())
        self.sessao.registrar_voto("ana", "A", self.inicio)
        self.sessao.registrar_voto("bia", "B", self.fim - timedelta(microseconds=1))
        self.assertEqual(self.sessao.placar, {"A": 1, "B": 1})
