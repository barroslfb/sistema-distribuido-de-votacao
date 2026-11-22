import unittest
from unittest.mock import patch

from src.services.broker import declare_voting_exchange


class RabbitMQConnectionTests(unittest.TestCase):
    @patch(
        "src.services.broker.pika.BlockingConnection",
        side_effect=OSError("amqp://user:secret@broker:5672/votes"),
    )
    @patch("src.services.broker.pika.URLParameters")
    def test_falha_de_conexao_tem_erro_claro_sem_credenciais(
        self, _url_parameters, _blocking_connection
    ):
        with self.assertLogs("src.services.broker", "ERROR") as logs:
            with self.assertRaisesRegex(
                RuntimeError, "Não foi possível conectar ao RabbitMQ"
            ) as erro:
                declare_voting_exchange()

        self.assertEqual(len(logs.output), 1)
        self.assertIn("operacao=rabbitmq_conexao resultado=falha", logs.output[0])
        self.assertNotIn("secret", logs.output[0])
        self.assertNotIn("secret", str(erro.exception))
        self.assertTrue(erro.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
