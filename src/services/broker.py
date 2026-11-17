import json
import os
import logging
from datetime import datetime, timezone

import pika

EXCHANGE_NAME = "apuracao.votos"
logger = logging.getLogger(__name__)


class PublicacaoFalhou(RuntimeError):
    """Não foi possível publicar a atualização de apuração no RabbitMQ."""


def _rabbitmq_url():
    return os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def declare_voting_exchange():
    """Connect briefly to RabbitMQ and declare the voting fanout exchange."""
    parameters = pika.URLParameters(_rabbitmq_url())
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


def publish_scoreboard_update(sessao_id, placar, data_hora=None):
    if data_hora is None:
        data_hora = datetime.now(timezone.utc)
    evento = {
        "sessao_id": sessao_id,
        "placar": dict(placar),
        "data_hora": data_hora.astimezone(timezone.utc).isoformat(),
    }
    corpo = json.dumps(evento, ensure_ascii=False).encode("utf-8")

    parameters = pika.URLParameters(_rabbitmq_url())
    parameters.connection_attempts = 1
    parameters.socket_timeout = 5
    try:
        connection = pika.BlockingConnection(parameters)
    except Exception as exc:
        raise PublicacaoFalhou(
            f"Não foi possível conectar ao RabbitMQ para publicar a apuração: {exc}"
        ) from exc

    try:
        channel = connection.channel()
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key="",
            body=corpo,
            properties=pika.BasicProperties(content_type="application/json"),
        )
    except Exception as exc:
        raise PublicacaoFalhou(
            f"Não foi possível publicar a apuração na exchange {EXCHANGE_NAME!r}: {exc}"
        ) from exc
    finally:
        try:
            connection.close()
        except Exception:
            logger.warning("Falha ao encerrar a conexão após publicar a apuração", exc_info=True)
    logger.info("Atualização de apuração publicada para a sessão %s", sessao_id)
    return evento
