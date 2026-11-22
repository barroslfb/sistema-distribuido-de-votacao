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

    def test_url_e_sessao_configuraveis_e_aviso_de_apuracao(self):
        def responder(requisicao):
            self.assertEqual(str(requisicao.url), "http://api.test:9000/sessoes/extra/votos")
            return httpx.Response(201, json={
                "mensagem": "Voto registrado com sucesso.",
                "aviso": "A atualização da apuração não pôde ser publicada.",
            })

        codigo, saida, erro = self.executar_cliente(
            responder, argv=["--api-url", "http://api.test:9000/", "--sessao", "extra"]
        )

        self.assertEqual(codigo, 0)
        self.assertIn("Voto registrado com sucesso.", saida)
        self.assertIn("A atualização da apuração não pôde ser publicada.", saida)
        self.assertEqual(erro, "")

    def test_exibe_motivo_da_rejeicao_da_api(self):
        casos = (
            (400, "Z", "opcao_invalida", "Opção inválida para esta sessão."),
            (403, "A", "fora_do_prazo", "A sessão não está no período de votação."),
            (404, "A", "sessao_inexistente", "Sessão não encontrada."),
            (409, "A", "voto_duplicado", "Este eleitor já votou nesta sessão."),
        )
        for status, opcao, motivo, mensagem in casos:
            with self.subTest(status=status):
                def responder(requisicao):
                    self.assertEqual(json.loads(requisicao.content)["opcao"], opcao)
                    return httpx.Response(status, json={
                        "detail": {"codigo": motivo, "mensagem": mensagem},
                    })

                codigo, saida, erro = self.executar_cliente(responder, entrada=("ana", opcao))

                self.assertEqual((codigo, saida, erro), (1, "", f"Voto rejeitado. {mensagem}\n"))

    def test_exibe_campo_invalido_e_preserva_entrada(self):
        def responder(requisicao):
            self.assertEqual(json.loads(requisicao.content)["eleitor_id"], " ana")
            return httpx.Response(422, json={"detail": [{
                "loc": ["body", "eleitor_id"],
                "msg": "Use texto sem controles ou espaços nas extremidades.",
            }]})

        codigo, saida, erro = self.executar_cliente(responder, entrada=(" ana", "A"))

        self.assertEqual((codigo, saida), (1, ""))
        self.assertIn("Voto rejeitado. eleitor_id:", erro)
        self.assertIn("Use texto sem controles ou espaços nas extremidades.", erro)

    def test_conexao_recusada_ou_tempo_limite(self):
        for tipo_erro in (httpx.ConnectError, httpx.ReadTimeout):
            with self.subTest(tipo_erro=tipo_erro):
                def responder(requisicao):
                    raise tipo_erro("API indisponível", request=requisicao)

                codigo, saida, erro = self.executar_cliente(responder)

                self.assertEqual((codigo, saida), (1, ""))
                self.assertIn("Falha de comunicação com a API.", erro)
                self.assertIn("Não foi possível confirmar o registro do voto.", erro)

    def test_erro_do_servidor_sem_resposta_json(self):
        codigo, saida, erro = self.executar_cliente(
            lambda _: httpx.Response(503, text="Serviço indisponível")
        )

        self.assertEqual((codigo, saida), (1, ""))
        self.assertIn("HTTP 503", erro)
        self.assertIn("Não foi possível confirmar o registro do voto.", erro)
