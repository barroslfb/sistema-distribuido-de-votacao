
from datetime import datetime, timezone
import uuid
from threading import Lock


class VotoRejeitado(ValueError):
    """Regra de negócio violada, independente do transporte HTTP."""

    def __init__(self, codigo, mensagem):
        super().__init__(mensagem)
        self.codigo = codigo


class VotingSession:
    # Representa uma sessão de votação e mantém seus dados em memória.

    def __init__(self, opcoes, inicio, fim, identificador=None):
        # Identificador único da sessão
        self._id = (
            str(uuid.uuid4())
            if identificador is None
            else identificador
        )

        if not isinstance(self._id, str) or not self._id.strip():
            raise ValueError("Identificador da sessão inválido.")

        # Valida e armazena as opções
        self._opcoes = self._validar_opcoes(opcoes)

        # Valida e armazena o prazo da votação
        self._inicio = self._validar_data_hora(inicio, "início")
        self._fim = self._validar_data_hora(fim, "fim")

        if self._inicio >= self._fim:
            raise ValueError(
                "O início da votação deve ser anterior ao fim do prazo."
            )

        # Inicializa o placar com zero votos para cada opção
        self._placar = {
            opcao: 0
            for opcao in self._opcoes
        }

        # Armazena os eleitores que já votaram e suas respectivas opções
        self._votos_por_eleitor = {}
        self._lock = Lock()

    def registrar_voto(self, eleitor_id, opcao, agora=None):
        """Valida e registra atomicamente; retorna uma cópia do novo placar.

        O intervalo ativo inclui o início e exclui o fim. `agora` permite
        testar os limites do prazo sem esperas ou alteração da sessão.
        """
        for valor in (eleitor_id, opcao):
            if (not isinstance(valor, str) or not valor.strip()
                    or not valor.isprintable() or valor != valor.strip()):
                raise ValueError("Eleitor e opção devem ser textos válidos sem espaços nas extremidades.")

        with self._lock:
            if opcao not in self._opcoes:
                raise VotoRejeitado("opcao_invalida", "Opção inválida para esta sessão.")
            instante = (datetime.now(timezone.utc) if agora is None
                        else self._validar_data_hora(agora, "agora"))
            if not self._inicio <= instante < self._fim:
                raise VotoRejeitado("fora_do_prazo", "A sessão não está no período de votação.")
            if eleitor_id in self._votos_por_eleitor:
                raise VotoRejeitado("voto_duplicado", "Este eleitor já votou nesta sessão.")

            self._votos_por_eleitor[eleitor_id] = opcao
            self._placar[opcao] += 1
            return self._placar.copy()



    # Validações

    @staticmethod
    def _validar_opcoes(opcoes):
        """Valida a lista de opções da votação."""

        if not isinstance(opcoes, (list, tuple)) or not opcoes:
            raise ValueError("A votação deve possuir pelo menos uma opção.")

        opcoes_validas = []

        for opcao in opcoes:
            if (
                not isinstance(opcao, str)
                or not opcao.strip()
                or not opcao.isprintable()
            ):
                raise ValueError("Opção de votação inválida.")

            opcao = opcao.strip()

            if opcao in opcoes_validas:
                raise ValueError("Não são permitidas opções duplicadas.")

            opcoes_validas.append(opcao)

        return tuple(opcoes_validas)

    @staticmethod
    def _validar_data_hora(data, campo):
        """Valida e normaliza uma data para UTC."""

        if not isinstance(data, datetime):
            raise TypeError(
                f"O campo {campo} deve ser uma data e hora."
            )

        if data.tzinfo is None or data.utcoffset() is None:
            raise ValueError(
                f"O campo {campo} deve possuir fuso horário definido."
            )

        return data.astimezone(timezone.utc)



    # Identificação e consulta

    @property
    def id(self):
        return self._id

    @property
    def opcoes(self):
        return self._opcoes

    @property
    def inicio(self):
        return self._inicio

    @property
    def fim(self):
        return self._fim

    @property
    def placar(self):
        return self.obter_placar()

    @property
    def eleitores(self):
        # Retorna os identificadores dos eleitores que já votaram.

        with self._lock:
            return set(self._votos_por_eleitor.keys())



    # Consulta do placar

    def obter_placar(self):
        # Retorna uma cópia do placar atual.

        with self._lock:
            return self._placar.copy()



    # Consulta completa da sessão

    def obter_dados(self):
        # Retorna todos os dados públicos da sessão.

        with self._lock:
            return {
                "id": self._id,
                "opcoes": list(self._opcoes),
                "placar": self._placar.copy(),
                "eleitores": sorted(self._votos_por_eleitor.keys()),
                "inicio": self._inicio.isoformat(),
                "fim": self._fim.isoformat(),
            }
