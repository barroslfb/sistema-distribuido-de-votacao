"""Cliente UDP interativo para o protocolo de votação por datagramas."""

import socket
import threading
import argparse

try:
    from .protocol import COMMAND_JOIN, encode_message
except ImportError:  # Compatibilidade com execução direta de src/client_udp.py.
    from protocol import COMMAND_JOIN, encode_message

HOST = "127.0.0.1"
PORT = 5001
BUFFER_SIZE = 4096
RECEIVE_TIMEOUT = 0.2


def receber_mensagens(cliente, ao_receber=print, parar=None):
    """Recebe e exibe mensagens UTF-8 independentemente do envio do usuário."""
    try:
        while True:
            try:
                dados = cliente.recv(BUFFER_SIZE)
            except socket.timeout:
                if parar is not None and parar.is_set():
                    return
                continue
            if not dados:
                continue
            for mensagem in dados.decode("utf-8").splitlines():
                if mensagem:
                    ao_receber(mensagem)
    except (OSError, UnicodeError) as erro:
        print(f"Recepção encerrada: {erro}")


def executar_cliente(host=HOST, port=PORT):
    """Envia cada comando uma vez por UDP e recebe respostas em outra thread."""
    try:
        identificador = input("Identificador: ").strip()
    except EOFError:
        print("Entrada encerrada antes de informar o identificador.")
        return

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as cliente:
        cliente.connect((host, port))
        cliente.settimeout(RECEIVE_TIMEOUT)
        parar = threading.Event()
        receptor = threading.Thread(
            target=receber_mensagens, args=(cliente, print, parar), daemon=True
        )
        receptor.start()
        try:
            # UDP não oferece confirmação/retransmissão: cada datagrama é enviado uma vez.
            cliente.send(encode_message(f"{COMMAND_JOIN} {identificador}"))
            while True:
                try:
                    mensagem = input()
                except EOFError:
                    break
                cliente.send(encode_message(mensagem))
        except (OSError, UnicodeError, ValueError) as erro:
            print(f"Envio encerrado: {erro}")
        finally:
            parar.set()
            receptor.join(timeout=1)
            cliente.close()


def _porta(valor):
    try:
        porta = int(valor)
    except ValueError as erro:
        raise argparse.ArgumentTypeError("a porta deve ser um inteiro") from erro
    if not 1 <= porta <= 65535:
        raise argparse.ArgumentTypeError("a porta deve estar entre 1 e 65535")
    return porta


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cliente UDP de votação")
    parser.add_argument("--host", default=HOST, help=f"servidor (padrão: {HOST})")
    parser.add_argument("--port", "--porta", dest="port", type=_porta, default=PORT,
                        help=f"porta UDP (padrão: {PORT})")
    argumentos = parser.parse_args(argv)
    executar_cliente(argumentos.host, argumentos.port)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyboardInterrupt) as erro:
        print(f"Cliente encerrado: {erro}")
