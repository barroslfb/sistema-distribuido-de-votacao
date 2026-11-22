import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import httpx

from src import votacao_client


class VotacaoClientTests(unittest.TestCase):
    def executar_cliente(self, responder, argv=(), entrada=("ana", "A")):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            httpx.Client(transport=httpx.MockTransport(responder)) as cliente,
            patch("builtins.input", side_effect=entrada) as ler,
            patch.object(votacao_client.httpx, "post", cliente.post),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            codigo = votacao_client.main(argv)
        self.assertEqual(ler.call_count, 2)
        return codigo, stdout.getvalue(), stderr.getvalue()

    def test_voto_aceito_na_sessao_padrao(self):
        def responder(requisicao):
            self.assertEqual(requisicao.method, "POST")
            self.assertEqual(str(requisicao.url), "http://localhost:8000/sessoes/entrega1/votos")
            self.assertEqual(json.loads(requisicao.content), {"eleitor_id": "ana", "opcao": "A"})
            self.assertEqual(requisicao.extensions["timeout"]["read"], 5.0)
            return httpx.Response(201, json={"mensagem": "Voto registrado com sucesso."})

        codigo, saida, erro = self.executar_cliente(responder)

        self.assertEqual((codigo, saida, erro), (0, "Voto registrado com sucesso.\n", ""))

        def rejeitar(requisicao):
            self.assertEqual(json.loads(requisicao.content), {"eleitor_id": "ana", "opcao": "Z"})
            return httpx.Response(400, json={"detail": {
                "codigo": "opcao_invalida",
                "mensagem": "Opção inválida para esta sessão.",
            }})

        codigo, saida, erro = self.executar_cliente(rejeitar, entrada=("ana", "Z"))
        self.assertEqual(
            (codigo, saida, erro),
            (1, "", "Voto rejeitado. Opção inválida para esta sessão.\n"),
        )
