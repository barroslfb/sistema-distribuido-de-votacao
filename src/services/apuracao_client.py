"""Cliente de apuração: assina a exchange `apuracao.votos` e exibe o placar.
    
    python -m src.services.apuracao_client

Cada instância cria uma fila exclusiva e temporária ligada à exchange fanout
"""
import json
import logging
import sys

import pika

from ..log_operacional import configurar_logs, registrar
from .broker import EXCHANGE_NAME, _rabbitmq_url

logger = logging.getLogger("src.services.apuracao_client")


def _ler_atualizacao(corpo):
    try:
        evento = json.loads(corpo)
        sessao_id = evento["sessao_id"]
        data_hora = evento["data_hora"]
        placar = evento["placar"]
        if not isinstance(placar, dict):
            raise TypeError("placar deve ser um objeto")
        itens = " | ".join(f"{opcao}: {votos}" for opcao, votos in placar.items())
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("evento de apuração inválido.") from None
    return sessao_id, data_hora, f"[{data_hora}] Sessão {sessao_id} | {itens}"


def formatar_atualizacao(corpo):
    return _ler_atualizacao(corpo)[2]


def consumir(saida=print):
    connection = None
    operacao = "rabbitmq_conexao"
    try:
        connection = pika.BlockingConnection(pika.URLParameters(_rabbitmq_url()))
        registrar(logger, logging.INFO, operacao, "sucesso",
                  exchange=EXCHANGE_NAME, finalidade="consumo")
        operacao = "rabbitmq_assinatura"
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="fanout")
        fila = channel.queue_declare(queue="", exclusive=True).method.queue
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=fila)

        def ao_receber(_canal, _metodo, _propriedades, corpo):
            try:
                sessao_id, data_hora, placar = _ler_atualizacao(corpo)
                saida(placar)
            except ValueError as erro:
                saida(f"Mensagem ignorada: {erro}")
            else:
                registrar(logger, logging.INFO, "rabbitmq_recebimento", "sucesso",
                          exchange=EXCHANGE_NAME,
                          sessao_id=sessao_id if isinstance(sessao_id, str) else None,
                          data_hora=data_hora if isinstance(data_hora, str) else None)

        channel.basic_consume(queue=fila, on_message_callback=ao_receber, auto_ack=True)
        saida(f"Aguardando atualizações em {EXCHANGE_NAME!r} (Ctrl+C para sair)...")
        operacao = "rabbitmq_consumo"
        channel.start_consuming()
    except Exception as erro:
        registrar(logger, logging.ERROR, operacao, "falha",
                  exchange=EXCHANGE_NAME, finalidade="consumo", motivo=type(erro).__name__,
                  mensagem="Erro no cliente de apuração.")
        raise
    finally:
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except Exception as erro:
                registrar(logger, logging.WARNING, "rabbitmq_encerramento", "falha",
                          exchange=EXCHANGE_NAME, finalidade="consumo", motivo=type(erro).__name__)


def main():
    try:
        consumir()
    except KeyboardInterrupt:
        print("\nCliente de apuração encerrado.")
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    configurar_logs()
    sys.exit(main())
