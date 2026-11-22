import json
import unittest
from unittest.mock import Mock, patch

from src.services import apuracao_client


class ApuracaoClientTests(unittest.TestCase):
    @patch("src.services.apuracao_client.pika.BlockingConnection")
    def test_exibe_placar_e_registra_recebimento(self, conectar):
        conexao = conectar.return_value
        canal = conexao.channel.return_value
        saida = Mock()
        data_hora = "2026-11-22T12:00:00+00:00"
        evento = {"sessao_id": "entrega1", "data_hora": data_hora, "placar": {"A": 1}}

        def entregar():
            callback = canal.basic_consume.call_args.kwargs["on_message_callback"]
            callback(None, None, None, json.dumps(evento).encode())

        canal.start_consuming.side_effect = entregar
        with self.assertLogs("src.services.apuracao_client") as logs:
            apuracao_client.consumir(saida)

        saida.assert_any_call(f"[{data_hora}] Sessão entrega1 | A: 1")
        conexao.close.assert_called_once()
        self.assertEqual(len(logs.output), 2)
        self.assertIn("operacao=rabbitmq_conexao resultado=sucesso", logs.output[0])
        self.assertIn("operacao=rabbitmq_recebimento resultado=sucesso", logs.output[1])
        self.assertIn('sessao_id="entrega1"', logs.output[1])
        self.assertIn(f'data_hora="{data_hora}"', logs.output[1])
