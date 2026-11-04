"""Servidor de votação UDP que responde ao endereço de cada datagrama."""

import socket
import threading

try:
    from .protocol import COMMAND_END, COMMAND_UPDATE, encode_message
    from .server import SessaoVotacao, _mensagem_resultados
    from .voting import Voting
except ImportError:  # Compatibilidade com execução direta de src/server_udp.py.
    from protocol import COMMAND_END, COMMAND_UPDATE, encode_message
    from server import SessaoVotacao, _mensagem_resultados
    from voting import Voting

HOST = "127.0.0.1"
PORT = 5001
BUFFER_SIZE = 4096
DURACAO_VOTACAO = 300


def _enviar(servidor, endereco, mensagem):
    servidor.sendto(encode_message(mensagem), endereco)


def atender_datagramas(servidor, processador=None, votacao=None):
    """Atende datagramas UTF-8; cada linha recebida é um comando.

    As sessões são associadas ao endereço IP/porta do cliente. Um datagrama
    pode conter mais de um comando, cada qual separado por newline.
    """
    if processador is None and votacao is None:
        votacao = Voting(DURACAO_VOTACAO)
        votacao.iniciar_votacao()

    sessoes = {}
    clientes = set()
    lock = threading.Lock()
    eventos_votacao_lock = threading.Lock()
    encerrado = threading.Event()

    def observar_encerramento():
        if votacao is None or processador is not None:
            return
        while not encerrado.is_set():
            with eventos_votacao_lock:
                if votacao.verificar_estado() == "encerrada":
                    mensagem = _mensagem_resultados(COMMAND_END, votacao)
                    with lock:
                        destinos = tuple(clientes)
                    for destino in destinos:
                        try:
                            _enviar(servidor, destino, mensagem)
                        except OSError:
                            pass
                    return
            encerrado.wait(0.05)

    observador = threading.Thread(
        target=observar_encerramento, name="udp-voting-deadline-observer", daemon=True
    )
    observador.start()
    try:
        while True:
            try:
                dados, endereco = servidor.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                mensagens = dados.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for mensagem in mensagens:
                if not mensagem:
                    continue
                if processador is not None:
                    processador(mensagem)
                    continue
                eh_voto = mensagem.split()[:1] == ["VOTE"]
                evento_lock = eventos_votacao_lock if eh_voto else _NoOpLock()
                with evento_lock:
                    with lock:
                        sessao = sessoes.setdefault(endereco, SessaoVotacao(votacao))
                        clientes.add(endereco)
                    resposta = sessao.processar(mensagem)
                    try:
                        _enviar(servidor, endereco, resposta)
                    except OSError:
                        continue
                    if resposta == "SUCCESS" and eh_voto:
                        update = _mensagem_resultados(COMMAND_UPDATE, votacao)
                        with lock:
                            destinos = tuple(clientes)
                        for destino in destinos:
                            try:
                                _enviar(servidor, destino, update)
                            except OSError:
                                pass
    finally:
        encerrado.set()
        observador.join(timeout=1)


class _NoOpLock:
    """Context manager usado para comandos que não alteram resultados."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def executar_servidor(host=HOST, port=PORT):
    """Inicia o socket UDP e atende até o processo ser interrompido."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as servidor:
        servidor.bind((host, port))
        servidor.settimeout(0.5)
        print(f"Servidor UDP escutando em {host}:{port}")
        atender_datagramas(servidor)


if __name__ == "__main__":
    try:
        executar_servidor()
    except KeyboardInterrupt:
        print("\nServidor UDP encerrado.")
