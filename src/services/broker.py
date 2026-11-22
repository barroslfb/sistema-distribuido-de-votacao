import json
import os
import logging
from datetime import datetime, timezone

import pika

from ..log_operacional import registrar

EXCHANGE_NAME = "apuracao.votos"
logger = logging.getLogger(__name__)


class PublicacaoFalhou(RuntimeError):
    """Não foi possível publicar a atualização de apuração no RabbitMQ."""


def _rabbitmq_url():
    return os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def declare_voting_exchange():
    """Connect briefly to RabbitMQ and declare the voting fanout exchange."""
    try:
        parameters = pika.URLParameters(_rabbitmq_url())
        connection = pika.BlockingConnection(parameters)
    except Exception as exc:
        registrar(logger, logging.ERROR, "rabbitmq_conexao", "falha",
                  exchange=EXCHANGE_NAME, finalidade="declaracao", motivo=type(exc).__name__)
        raise RuntimeError(
            "Não foi possível conectar ao RabbitMQ; verifique a disponibilidade do broker e RABBITMQ_URL."
        ) from None
    registrar(logger, logging.INFO, "rabbitmq_conexao", "sucesso",
              exchange=EXCHANGE_NAME, finalidade="declaracao")

    declaration_failed = False
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="fanout")
        registrar(logger, logging.INFO, "rabbitmq_declaracao", "sucesso", exchange=EXCHANGE_NAME)
    except Exception as exc:
        declaration_failed = True
        registrar(logger, logging.ERROR, "rabbitmq_declaracao", "falha",
                  exchange=EXCHANGE_NAME, motivo=type(exc).__name__)
        raise RuntimeError(
            f"Não foi possível declarar a exchange {EXCHANGE_NAME!r} (fanout) no RabbitMQ."
        ) from None
    finally:
        try:
            connection.close()
        except Exception as exc:
            registrar(logger, logging.WARNING, "rabbitmq_encerramento", "falha",
                      exchange=EXCHANGE_NAME, finalidade="declaracao", motivo=type(exc).__name__)
            if not declaration_failed:
                raise RuntimeError("Não foi possível encerrar a conexão inicial com o RabbitMQ.") from None


def publish_scoreboard_update(sessao_id, placar, data_hora=None):
    if data_hora is None:
        data_hora = datetime.now(timezone.utc)
    evento = {
        "sessao_id": sessao_id,
        "placar": dict(placar),
        "data_hora": data_hora.astimezone(timezone.utc).isoformat(),
    }
    corpo = json.dumps(evento, ensure_ascii=False).encode("utf-8")

    try:
        parameters = pika.URLParameters(_rabbitmq_url())
        parameters.connection_attempts = 1
        parameters.socket_timeout = 5
        connection = pika.BlockingConnection(parameters)
    except Exception as exc:
        registrar(logger, logging.ERROR, "rabbitmq_conexao", "falha", sessao_id=sessao_id,
                  exchange=EXCHANGE_NAME, finalidade="publicacao", motivo=type(exc).__name__)
        raise PublicacaoFalhou(
            "Não foi possível conectar ao RabbitMQ para publicar a apuração."
        ) from None
    registrar(logger, logging.INFO, "rabbitmq_conexao", "sucesso", sessao_id=sessao_id,
              exchange=EXCHANGE_NAME, finalidade="publicacao")

    try:
        channel = connection.channel()
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key="",
            body=corpo,
            properties=pika.BasicProperties(content_type="application/json"),
        )
    except Exception as exc:
        registrar(logger, logging.ERROR, "rabbitmq_publicacao", "falha",
                  sessao_id=sessao_id, exchange=EXCHANGE_NAME, motivo=type(exc).__name__)
        raise PublicacaoFalhou(
            f"Não foi possível publicar a apuração na exchange {EXCHANGE_NAME!r}."
        ) from None
    finally:
        try:
            connection.close()
        except Exception as exc:
            registrar(logger, logging.WARNING, "rabbitmq_encerramento", "falha", sessao_id=sessao_id,
                      exchange=EXCHANGE_NAME, finalidade="publicacao", motivo=type(exc).__name__)
    registrar(logger, logging.INFO, "rabbitmq_publicacao", "sucesso",
              sessao_id=sessao_id, exchange=EXCHANGE_NAME, data_hora=evento["data_hora"])
    return evento
