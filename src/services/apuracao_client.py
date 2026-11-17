"""Cliente de apuração: assina a exchange `apuracao.votos` e exibe o placar.
    
    python -m src.services.apuracao_client

Cada instância cria uma fila exclusiva e temporária ligada à exchange fanout
"""
import json
import sys

import pika

from .broker import EXCHANGE_NAME, _rabbitmq_url


def formatar_atualizacao(corpo):
    try:
        evento = json.loads(corpo)
        sessao_id = evento["sessao_id"]
        data_hora = evento["data_hora"]
        placar = evento["placar"]
        if not isinstance(placar, dict):
            raise TypeError("placar deve ser um objeto")
        itens = " | ".join(f"{opcao}: {votos}" for opcao, votos in placar.items())
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"evento de apuração inválido: {exc}") from exc
    return f"[{data_hora}] Sessão {sessao_id} | {itens}"


def consumir(saida=print):
    connection = pika.BlockingConnection(pika.URLParameters(_rabbitmq_url()))
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="fanout")
        fila = channel.queue_declare(queue="", exclusive=True).method.queue
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=fila)

        def ao_receber(_canal, _metodo, _propriedades, corpo):
            try:
                saida(formatar_atualizacao(corpo))
            except ValueError as erro:
                saida(f"Mensagem ignorada: {erro}")

        channel.basic_consume(queue=fila, on_message_callback=ao_receber, auto_ack=True)
        saida(f"Aguardando atualizações em {EXCHANGE_NAME!r} (Ctrl+C para sair)...")
        channel.start_consuming()
    finally:
        try:
            connection.close()
        except Exception:
            pass


def main():
    try:
        consumir()
    except KeyboardInterrupt:
        print("\nCliente de apuração encerrado.")
    except Exception as erro:
        print(f"Erro no cliente de apuração: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
