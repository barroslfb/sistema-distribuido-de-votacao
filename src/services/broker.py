import os
import logging

import pika

EXCHANGE_NAME = "apuracao.votos"
logger = logging.getLogger(__name__)


def declare_voting_exchange():
    """Connect briefly to RabbitMQ and declare the voting fanout exchange."""
    url = os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@localhost:5672/",
    )
    parameters = pika.URLParameters(url)
    try:
        connection = pika.BlockingConnection(parameters)
    except Exception as exc:
        raise RuntimeError(
            f"Não foi possível conectar ao RabbitMQ; verifique a disponibilidade do broker e RABBITMQ_URL: {exc}"
        ) from exc

    declaration_failed = False
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="fanout")
        logger.info("Declared RabbitMQ exchange %s (fanout)", EXCHANGE_NAME)
    except Exception as exc:
        declaration_failed = True
        raise RuntimeError(
            f"Não foi possível declarar a exchange {EXCHANGE_NAME!r} (fanout) no RabbitMQ: {exc}"
        ) from exc
    finally:
        try:
            connection.close()
        except Exception as exc:
            if not declaration_failed:
                raise RuntimeError(f"Não foi possível encerrar a conexão inicial com o RabbitMQ: {exc}") from exc
