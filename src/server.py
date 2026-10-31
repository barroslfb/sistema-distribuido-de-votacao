"""Servidor TCP simples, com uma thread para cada cliente conectado."""

import socket
import threading
from contextlib import nullcontext

try:
    from .protocol import COMMAND_END, COMMAND_UPDATE, NewlineFramer, encode_message
    from .voting import Voting
except ImportError:  # Compatibilidade com a execução direta de src/server.py.
    from protocol import COMMAND_END, COMMAND_UPDATE, NewlineFramer, encode_message
    from voting import Voting

HOST = "127.0.0.1"
PORT = 5000
BUFFER_SIZE = 4096
DURACAO_VOTACAO = 300
_CLIENTES_LOCK = threading.Lock()
_EVENTOS_VOTACAO_LOCK = threading.Lock()


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


def _mensagem_resultados(comando, votacao):
    resultados = votacao.obter_resultados()
    return "{} {}".format(
        comando,
        " ".join(f"{opcao}:{resultados[opcao]}" for opcao in ("A", "B", "C")),
    )


def _broadcast(clientes, mensagem, excluir=None):
    if not clientes:
        return
    dados = encode_message(mensagem)
    with _CLIENTES_LOCK:
        conectados = [item for item in clientes.items() if item[0] is not excluir]
    for cliente, trava in conectados:
        try:
            with trava:
                cliente.sendall(dados)
        except OSError:
            with _CLIENTES_LOCK:
                clientes.pop(cliente, None)


def atender_cliente(cliente, endereco, processador=None, votacao=None, clientes=None):
    """Recebe mensagens UTF-8 delimitadas por newline até desconexão."""
    with cliente:
        print(f"Cliente conectado: {endereco}")
        sessao = SessaoVotacao(votacao) if processador is None else None

        def processar(mensagem):
            if sessao is not None:
                eh_voto = mensagem.split()[:1] == ["VOTE"]
                # A validação, snapshot e transmissão do UPDATE formam uma
                # seção serializada: votos concorrentes não podem publicar
                # snapshots fora de ordem nem ultrapassar o END.
                trava_evento = _EVENTOS_VOTACAO_LOCK if eh_voto else nullcontext()
                with trava_evento:
                    resposta = sessao.processar(mensagem)
                    if clientes is not None:
                        with _CLIENTES_LOCK:
                            trava = clientes.get(cliente)
                    else:
                        trava = None
                    erro_envio = None
                    try:
                        if trava is None:
                            cliente.sendall(encode_message(resposta))
                        else:
                            with trava:
                                cliente.sendall(encode_message(resposta))
                    except OSError as erro:
                        erro_envio = erro
                    if resposta == "SUCCESS" and eh_voto:
                        mensagem_update = _mensagem_resultados(COMMAND_UPDATE, votacao)
                        if clientes is None:
                            _broadcast({cliente: threading.Lock()}, mensagem_update)
                        else:
                            _broadcast(clientes, mensagem_update)
                    if erro_envio is not None:
                        raise erro_envio
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
        if clientes is not None:
            with _CLIENTES_LOCK:
                clientes.pop(cliente, None)


def atender_conexoes(servidor, processador=None, votacao=None):
    """Aceita conexões e inicia uma thread dedicada a cada cliente."""
    if processador is None and votacao is None:
        votacao = Voting(DURACAO_VOTACAO)
        votacao.iniciar_votacao()
    clientes = {}
    estado_final_enviado = threading.Event()
    servidor_parado = threading.Event()

    def observar_encerramento():
        if votacao is None or processador is not None:
            return
        while not estado_final_enviado.is_set() and not servidor_parado.is_set():
            with _EVENTOS_VOTACAO_LOCK:
                if votacao.verificar_estado() == "encerrada":
                    _broadcast(clientes, _mensagem_resultados(COMMAND_END, votacao))
                    estado_final_enviado.set()
                    return
            if servidor_parado.wait(0.05):
                return

    observador = threading.Thread(
        target=observar_encerramento,
        name="voting-deadline-observer",
        daemon=True,
    )
    observador.start()
    try:
        while True:
            try:
                cliente, endereco = servidor.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with _CLIENTES_LOCK:
                clientes[cliente] = threading.Lock()
            threading.Thread(
                target=atender_cliente,
                args=(cliente, endereco, processador, votacao, clientes),
                daemon=True,
            ).start()
    finally:
        servidor_parado.set()
        observador.join(timeout=1)


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
