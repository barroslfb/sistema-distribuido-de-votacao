"""Cliente TCP interativo com mensagens UTF-8 delimitadas por newline."""

import socket
import threading

try:
    from .protocol import COMMAND_JOIN, NewlineFramer, encode_message
except ImportError:  # Compatibilidade com a execução direta de src/client.py.
    from protocol import COMMAND_JOIN, NewlineFramer, encode_message

HOST = "127.0.0.1"
PORT = 5000
BUFFER_SIZE = 4096


def receber_mensagens(cliente, ao_receber=print):
    """Recebe mensagens até a desconexão, mesmo com UTF-8 fragmentado."""
    framer = NewlineFramer()
    try:
        while True:
            dados = cliente.recv(BUFFER_SIZE)
            if not dados:
                mensagem_final = framer.finish()
                if mensagem_final is not None:
                    ao_receber(mensagem_final)
                print("Servidor encerrou a conexão TCP.")
                return
            for mensagem in framer.feed(dados):
                ao_receber(mensagem)
    except (OSError, UnicodeError) as erro:
        print(f"Recepção encerrada: {erro}")


def executar_cliente(host=HOST, port=PORT):
    """Conecta por TCP, registra o cliente e envia comandos digitados."""
    try:
        identificador = input("Identificador: ").strip()
    except EOFError:
        print("Entrada encerrada antes de informar o identificador.")
        return
    with socket.create_connection((host, port)) as cliente:
        # A thread dedicada recebe dados TCP enquanto o fluxo principal envia comandos.
        receptor = threading.Thread(
            target=receber_mensagens, args=(cliente,), daemon=True
        )
        receptor.start()
        try:
            cliente.sendall(encode_message(f"{COMMAND_JOIN} {identificador}"))
            while True:
                try:
                    mensagem = input()
                except EOFError:
                    break
                cliente.sendall(encode_message(mensagem))
        except (OSError, UnicodeError) as erro:
            print(f"Envio encerrado: {erro}")
        finally:
            try:
                cliente.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            receptor.join(timeout=2)


if __name__ == "__main__":
    try:
        executar_cliente()
    except (OSError, KeyboardInterrupt) as erro:
        print(f"Cliente encerrado: {erro}")
