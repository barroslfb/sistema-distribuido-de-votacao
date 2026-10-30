"""Servidor TCP simples, com uma thread para cada cliente conectado."""

import socket
import threading

try:
    from .protocol import NewlineFramer
except ImportError:  # Compatibilidade com a execução direta de src/server.py.
    from protocol import NewlineFramer

HOST = "127.0.0.1"
PORT = 5000
BUFFER_SIZE = 4096


def processar_dados(dados):
    """Processa uma mensagem de texto recebida do cliente."""
    print(f"Dados recebidos: {dados}")


def atender_cliente(cliente, endereco, processador=processar_dados):
    """Recebe mensagens UTF-8 delimitadas por newline até desconexão."""
    with cliente:
        print(f"Cliente conectado: {endereco}")
        framer = NewlineFramer()
        while True:
            try:
                dados = cliente.recv(BUFFER_SIZE)
            except OSError:
                break
            if not dados:
                break
            try:
                for mensagem in framer.feed(dados):
                    processador(mensagem)
            except UnicodeDecodeError:
                print(f"Mensagem UTF-8 inválida de {endereco}")
                break
        try:
            mensagem_final = framer.finish()
        except UnicodeDecodeError:
            mensagem_final = None
            print(f"Mensagem UTF-8 inválida de {endereco}")
        if mensagem_final is not None:
            processador(mensagem_final)
        print(f"Cliente desconectado: {endereco}")


def atender_conexoes(servidor, processador=processar_dados):
    """Aceita conexões e inicia uma thread dedicada a cada cliente."""
    while True:
        try:
            cliente, endereco = servidor.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(
            target=atender_cliente,
            args=(cliente, endereco, processador),
            daemon=True,
        ).start()


def executar_servidor(host=HOST, port=PORT):
    """Cria e executa o socket servidor até interrupção do processo."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((host, port))
        servidor.listen()
        servidor.settimeout(0.5)
        print(f"Servidor escutando em {host}:{port}")
        atender_conexoes(servidor)


if __name__ == "__main__":
    try:
        executar_servidor()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
