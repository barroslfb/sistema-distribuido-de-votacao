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

    def test_voto_aceito_e_duplicado(self):
        body = {"eleitor_id": "ana", "opcao": "A"}
        response = self.client.post(self.url, json=body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"mensagem": "Voto registrado com sucesso.",
            "sessao_id": "teste", "placar": {"A": 1, "B": 0}})
        anterior = self.sessao.obter_dados()
        response = self.client.post(self.url, json=body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["codigo"], "voto_duplicado")
        self.assertEqual(self.sessao.obter_dados(), anterior)

    def test_opcao_invalida_e_sessao_inexistente(self):
        anterior = self.sessao.obter_dados()
        response = self.client.post(self.url, json={"eleitor_id": "ana", "opcao": "Z"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["codigo"], "opcao_invalida")
        response = self.client.post("/sessoes/ausente/votos", json={"eleitor_id": "ana", "opcao": "A"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["codigo"], "sessao_inexistente")
        self.assertEqual(self.sessao.obter_dados(), anterior)

    def test_fora_do_prazo_e_precedencia_da_opcao(self):
        agora = datetime.now(timezone.utc)
        for inicio in (agora + timedelta(days=1), agora - timedelta(days=1)):
            sessao = VotingSession(["A"], inicio, inicio + timedelta(minutes=5), "prazo")
            app.state.sessoes["prazo"] = sessao
            for opcao, status, codigo in (("Z", 400, "opcao_invalida"),
                                         ("A", 403, "fora_do_prazo")):
                response = self.client.post("/sessoes/prazo/votos", json={"eleitor_id": "ana", "opcao": opcao})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["detail"]["codigo"], codigo)
            self.assertEqual(sessao.eleitores, set())
            self.assertEqual(sessao.placar, {"A": 0})

    def test_json_e_formatos_invalidos(self):
        for body in ({}, {"eleitor_id": "ana"}, {"opcao": "A"},
                     {"eleitor_id": 123, "opcao": "A"},
                     {"eleitor_id": "ana", "opcao": None},
                     {"eleitor_id": "", "opcao": "A"},
                     {"eleitor_id": " ana", "opcao": "A"},
                     {"eleitor_id": "a\nb", "opcao": "A"},
                     {"eleitor_id": "a" * 101, "opcao": "A"},
                     {"eleitor_id": "ana", "opcao": "A", "extra": True}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.url, json=body).status_code, 422)
        self.assertEqual(self.client.post(self.url, content="{", headers={
            "content-type": "application/json"}).status_code, 422)
        self.assertEqual(self.sessao.eleitores, set())
        self.assertEqual(self.sessao.placar, {"A": 0, "B": 0})

    def test_sessao_demonstrativa_disponivel_no_startup(self):
        response = self.client.post("/sessoes/entrega1/votos", json={"eleitor_id": "ana", "opcao": "C"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["placar"], {"A": 0, "B": 0, "C": 1})

    def test_votos_rejeitados_nao_publicam_atualizacao(self):
        self.sessao.registrar_voto("ana", "A")
        prazo_encerrado = datetime.now(timezone.utc) - timedelta(minutes=2)
        sessao_fora_do_prazo = VotingSession(
            ["A"], prazo_encerrado - timedelta(minutes=5), prazo_encerrado, "encerrada"
        )
        app.state.sessoes[sessao_fora_do_prazo.id] = sessao_fora_do_prazo

        with patch("src.controllers.api.publish_scoreboard_update") as publicar:
            duplicado = self.client.post(
                self.url, json={"eleitor_id": "ana", "opcao": "A"}
            )
            invalido = self.client.post(
                self.url, json={"eleitor_id": "bia", "opcao": "Z"}
            )
            fora_do_prazo = self.client.post(
                "/sessoes/encerrada/votos",
                json={"eleitor_id": "bia", "opcao": "A"},
            )

        self.assertEqual(duplicado.status_code, 409)
        self.assertEqual(invalido.status_code, 400)
        self.assertEqual(fora_do_prazo.status_code, 403)
        publicar.assert_not_called()

    def test_falha_de_publicacao_preserva_voto_e_retorna_aviso(self):
        with patch(
            "src.controllers.api.publish_scoreboard_update",
            side_effect=PublicacaoFalhou("broker indisponível"),
        ):
            response = self.client.post(
                self.url, json={"eleitor_id": "ana", "opcao": "A"}
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["aviso"],
            "Voto registrado, mas a atualização da apuração não pôde ser publicada.",
        )
        self.assertEqual(self.sessao.eleitores, {"ana"})
        self.assertEqual(self.sessao.placar, {"A": 1, "B": 0})
