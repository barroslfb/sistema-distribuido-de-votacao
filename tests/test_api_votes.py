import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.controllers.api import app
from src.services.broker import PublicacaoFalhou
from src.voting import VotingSession


class VoteEndpointTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch("src.controllers.api.declare_voting_exchange"))
        self.client = stack.enter_context(TestClient(app))
        inicio = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.sessao = VotingSession(["A", "B"], inicio,
                                    inicio + timedelta(minutes=10), "teste")
        app.state.sessoes[self.sessao.id] = self.sessao
        self.url = "/sessoes/teste/votos"

    def test_entradas_invalidas_e_sessao_inexistente(self):
        anterior = self.sessao.obter_dados()
        corpos_invalidos = (
            {},
            {"eleitor_id": "ana"},
            {"opcao": "A"},
            {"eleitor_id": 123, "opcao": "A"},
            {"eleitor_id": "ana", "opcao": "A", "extra": True},
        )
        for corpo in corpos_invalidos:
            with self.subTest(corpo=corpo):
                resposta = self.client.post(self.url, json=corpo)
                self.assertEqual(resposta.status_code, 422)
        resposta = self.client.post(
            self.url, content="{", headers={"content-type": "application/json"}
        )
        self.assertEqual(resposta.status_code, 422)
        resposta = self.client.post(
            "/sessoes/ausente/votos", json={"eleitor_id": "ana", "opcao": "A"}
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(resposta.json()["detail"]["codigo"], "sessao_inexistente")
        self.assertEqual(self.sessao.obter_dados(), anterior)
        self.assertEqual(self.sessao.eleitores, set())
        self.assertEqual(self.sessao.placar, {"A": 0, "B": 0})

    def test_falha_de_publicacao_preserva_voto_e_retorna_aviso(self):
        with self.assertLogs("src.controllers.api") as logs, patch(
            "src.controllers.api.publish_scoreboard_update",
            side_effect=PublicacaoFalhou("broker indisponível"),
        ):
            response = self.client.post(
                self.url, json={"eleitor_id": "ana", "opcao": "A"}
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('operacao=voto resultado=aceito sessao_id="teste" eleitor_id="ana"', logs.output[0])
        self.assertEqual(
            response.json()["aviso"],
            "Voto registrado, mas a atualização da apuração não pôde ser publicada.",
        )
        self.assertEqual(self.sessao.eleitores, {"ana"})
        self.assertEqual(self.sessao.placar, {"A": 1, "B": 0})

    def test_voto_expirado_nao_altera_estado_nem_publica_evento(self):
        self.sessao._fim = datetime.now(timezone.utc) - timedelta(seconds=1)

        with patch("src.controllers.api.publish_scoreboard_update") as publicar:
            response = self.client.post(
                self.url, json={"eleitor_id": "ana", "opcao": "A"}
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["codigo"], "fora_do_prazo")
        self.assertEqual(self.sessao.eleitores, set())
        self.assertEqual(self.sessao.placar, {"A": 0, "B": 0})
        publicar.assert_not_called()
