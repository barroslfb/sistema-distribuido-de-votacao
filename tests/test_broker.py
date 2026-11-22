import os
import unittest
from unittest.mock import Mock, patch

from src.services.broker import (
    EXCHANGE_NAME,
    PublicacaoFalhou,
    declare_voting_exchange,
    publish_scoreboard_update,
)


class RabbitMQConnectionTests(unittest.TestCase):
    @patch("src.services.broker.pika.BlockingConnection")
    @patch("src.services.broker.pika.URLParameters")
    def test_declares_fanout_exchange_then_closes_connection(
        self, url_parameters, blocking_connection
    ):
        url = "amqp://user:secret@broker:5672/votes"
        with patch.dict(os.environ, {"RABBITMQ_URL": url}), self.assertLogs("src.services.broker") as logs:
            parameters = Mock()
            url_parameters.return_value = parameters
            connection = Mock()
            blocking_connection.return_value = connection

            declare_voting_exchange()

        url_parameters.assert_called_once_with(url)
        blocking_connection.assert_called_once_with(parameters)
        connection.channel.assert_called_once_with()
        connection.channel.return_value.exchange_declare.assert_called_once_with(
            exchange=EXCHANGE_NAME,
            exchange_type="fanout",
        )
        connection.close.assert_called_once_with()
        self.assertEqual(len(logs.output), 2)
        self.assertIn("operacao=rabbitmq_conexao resultado=sucesso", logs.output[0])
        self.assertIn("operacao=rabbitmq_declaracao resultado=sucesso", logs.output[1])
        self.assertNotIn("secret", " ".join(logs.output))

    @patch("src.services.broker.pika.BlockingConnection",
           side_effect=OSError("amqp://user:secret@broker:5672/votes"))
    @patch("src.services.broker.pika.URLParameters")
    def test_connection_failure_has_clear_error(self, url_parameters, _blocking_connection):
        with self.assertLogs("src.services.broker", "ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "Não foi possível conectar ao RabbitMQ") as erro:
                declare_voting_exchange()
        self.assertEqual(len(logs.output), 1)
        self.assertIn("operacao=rabbitmq_conexao resultado=falha", logs.output[0])
        self.assertNotIn("secret", logs.output[0])
        self.assertNotIn("secret", str(erro.exception))
        self.assertTrue(erro.exception.__suppress_context__)

    @patch("src.services.broker.pika.BlockingConnection")
    @patch("src.services.broker.pika.URLParameters")
    def test_declaration_failure_still_closes_connection(
        self, url_parameters, blocking_connection
    ):
        connection = Mock()
        connection.channel.return_value.exchange_declare.side_effect = OSError(
            "declaration rejected"
        )
        blocking_connection.return_value = connection

        with self.assertRaisesRegex(
            RuntimeError, "Não foi possível declarar a exchange 'apuracao.votos' \\(fanout\\)"
        ):
            declare_voting_exchange()

        connection.close.assert_called_once_with()

    @patch("src.services.broker.pika.BlockingConnection")
    def test_publicacao_registra_sucesso_e_falha_sem_credencial(self, conectar):
        canal = conectar.return_value.channel.return_value
        with self.assertLogs("src.services.broker") as sucesso:
            evento = publish_scoreboard_update("entrega1", {"A": 1})
        self.assertEqual(len(sucesso.output), 2)
        self.assertIn("operacao=rabbitmq_publicacao resultado=sucesso", sucesso.output[1])
        self.assertIn('sessao_id="entrega1"', sucesso.output[1])
        self.assertIn(f'data_hora="{evento["data_hora"]}"', sucesso.output[1])

        canal.basic_publish.side_effect = OSError("amqp://user:secret@broker:5672/votes")
        with self.assertLogs("src.services.broker", "ERROR") as falha:
            with self.assertRaises(PublicacaoFalhou):
                publish_scoreboard_update("entrega1", {"A": 1})
        self.assertEqual(len(falha.output), 1)
        self.assertIn("operacao=rabbitmq_publicacao resultado=falha", falha.output[0])
        self.assertIn('sessao_id="entrega1"', falha.output[0])
        self.assertNotIn("secret", falha.output[0])


if __name__ == "__main__":
    unittest.main()
