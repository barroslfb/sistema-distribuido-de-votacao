"""Servidor TCP simples, com uma thread para cada cliente conectado."""

import socket
import threading

try:
    from .protocol import NewlineFramer, encode_message
    from .voting import Voting
except ImportError:  # Compatibilidade com a execução direta de src/server.py.
    from protocol import NewlineFramer, encode_message
    from voting import Voting

HOST = "127.0.0.1"
PORT = 5000
BUFFER_SIZE = 4096
DURACAO_VOTACAO = 300


def processar_dados(dados):
    """Processa uma mensagem de texto recebida do cliente."""
    print(f"Dados recebidos: {dados}")


class SessaoVotacao:
    """Associa o ID à conexão e traduz comandos em operações da votação."""

    def __init__(self, votacao):
        self.votacao = votacao
        self.participante = None

    def processar(self, mensagem):
        partes = mensagem.split()
        if len(partes) != 2:
            return "ERROR Use JOIN identificador ou VOTE opcao."
        comando, argumento = partes
        if comando == "JOIN":
            if self.participante is not None:
                return "ERROR A conexão já possui um identificador."
            if not argumento.isprintable():
                return "ERROR Identificador inválido."
            self.participante = argumento
            return "SUCCESS"
        if comando == "VOTE":
            if self.participante is None:
                return "ERROR Identifique-se com JOIN antes de votar."
            try:
                self.votacao.registro_voto(argumento, self.participante)
            except (ValueError, RuntimeError) as erro:
                return f"ERROR {erro}"
            return "SUCCESS"
        return "ERROR Comando desconhecido."


def atender_cliente(cliente, endereco, processador=None, votacao=None):
    """Recebe mensagens UTF-8 delimitadas por newline até desconexão."""
    with cliente:
        print(f"Cliente conectado: {endereco}")
        sessao = SessaoVotacao(votacao) if processador is None else None

        def processar(mensagem):
            if sessao is not None:
                cliente.sendall(encode_message(sessao.processar(mensagem)))
            else:
                processador(mensagem)

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
                    processar(mensagem)
            except OSError:
                break
            except UnicodeDecodeError:
                print(f"Mensagem UTF-8 inválida de {endereco}")
                break
        try:
            mensagem_final = framer.finish()
        except UnicodeDecodeError:
            mensagem_final = None
            print(f"Mensagem UTF-8 inválida de {endereco}")
        if mensagem_final is not None:
            try:
                processar(mensagem_final)
            except OSError:
                pass
        print(f"Cliente desconectado: {endereco}")


def atender_conexoes(servidor, processador=None, votacao=None):
    """Aceita conexões e inicia uma thread dedicada a cada cliente."""
    if processador is None and votacao is None:
        votacao = Voting(DURACAO_VOTACAO)
        votacao.iniciar_votacao()
    while True:
        try:
            cliente, endereco = servidor.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(
            target=atender_cliente,
            args=(cliente, endereco, processador, votacao),
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
