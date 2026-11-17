import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.controllers.api import app
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

    def test_requisicoes_simultaneas_do_mesmo_eleitor(self):
        barreira = Barrier(2)
        def votar(_):
            barreira.wait(timeout=5)
            return self.client.post(self.url, json={"eleitor_id": "ana", "opcao": "A"}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(votar, range(2)))
        self.assertEqual(sorted(resultados), [201, 409])
        self.assertEqual(self.sessao.placar, {"A": 1, "B": 0})
        self.assertEqual(self.sessao.eleitores, {"ana"})

    def test_sessao_demonstrativa_disponivel_no_startup(self):
        response = self.client.post("/sessoes/entrega1/votos", json={"eleitor_id": "ana", "opcao": "C"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["placar"], {"A": 0, "B": 0, "C": 1})
