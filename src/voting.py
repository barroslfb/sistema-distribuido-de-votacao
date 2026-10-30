import math
import threading
import time


class Voting:
    # Criando os atributos da classe Voting
    def __init__(self, duracao_votacao):
        if isinstance(duracao_votacao, bool) or not isinstance(
            duracao_votacao, (int, float)
        ):
            raise TypeError("A duração da votação deve ser um número.")
        if not math.isfinite(duracao_votacao) or duracao_votacao <= 0:
            raise ValueError(
                "A duração da votação deve ser um número positivo e finito."
            )

        self.votos = {"A": 0, "B": 0, "C": 0}
        self._votos_por_participante = {}
        self.duracao_votacao = duracao_votacao
        self.estado = "não iniciada"
        self._prazo_final = None
        self._lock = threading.Lock()

    # Método para registrar um voto
    def registro_voto(self, candidate, participante):
        """Valida e registra um único voto por ID, atomicamente.

        O histórico pertence à votação, e não ao socket: reconectar não
        permite votar novamente. Falhas não modificam histórico nem contagem.
        """
        # Verifica se o voto está no horário permitido
        with self._lock:
            self._atualizar_estado_pelo_prazo()
            if self.estado != "votando":
                raise RuntimeError("Não é possível votar fora do período ativo.")

            if (
                not isinstance(participante, str)
                or not participante
                or not participante.isprintable()
                or any(caractere.isspace() for caractere in participante)
            ):
                raise ValueError("Informe um identificador válido, sem espaços.")
            if not isinstance(candidate, str) or candidate not in self.votos:
                raise ValueError("Opção inválida. Escolha A, B ou C.")
            if participante in self._votos_por_participante:
                raise ValueError("Este identificador já votou.")

            self._votos_por_participante[participante] = candidate
            self.votos[candidate] += 1

    def obter_resultados(self):
        """Retorna uma cópia consistente da contagem, sem expor o histórico."""
        with self._lock:
            return self.votos.copy()

    # Método para exibir os resultados da votação
    def exibir_resultados(self):
        with self._lock:
            votos = self.votos.copy()

        print("Resultados da votação:")
        for candidate, count in votos.items():
            print(f"Candidato {candidate}: {count} votos")

    # Método para iniciar a votação
    def iniciar_votacao(self):
        with self._lock:
            if self.estado != "não iniciada":
                raise RuntimeError("A votação já foi iniciada ou encerrada.")

            self.estado = "votando"
            self._prazo_final = time.monotonic() + self.duracao_votacao

        print(f"Votação iniciada! Você tem {self.duracao_votacao} segundos para votar.")

    # Método para encerrar a votação manualmente
    def encerrar_votacao(self):
        with self._lock:
            self.estado = "encerrada"

        print("Votação encerrada!")
        self.exibir_resultados()

    # Método para verificar o estado da votação
    def verificar_estado(self):
        with self._lock:
            self._atualizar_estado_pelo_prazo()
            return self.estado

    # Método para atualizar o estado da votação com base no prazo
    def _atualizar_estado_pelo_prazo(self):
        if self.estado == "votando" and time.monotonic() >= self._prazo_final:
            self.estado = "encerrada"
