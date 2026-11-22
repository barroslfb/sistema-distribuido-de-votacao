import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..log_operacional import configurar_logs, registrar
from ..services.broker import PublicacaoFalhou, declare_voting_exchange, publish_scoreboard_update
from ..voting import VotingSession, VotoRejeitado

logger = logging.getLogger(__name__)

# Serializa as publicações: cada evento lê o placar atual dentro da trava,
# então os consumidores nunca recebem um placar mais antigo depois de um mais novo.
_publicacao_lock = Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configurar_logs()
    declare_voting_exchange()
    inicio = datetime.now(timezone.utc)
    sessao = VotingSession(["A", "B", "C"], inicio,
                          inicio + timedelta(seconds=300), identificador="entrega1")
    app.state.sessoes = {sessao.id: sessao}
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


class VotoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eleitor_id: StrictStr = Field(min_length=1, max_length=100)
    opcao: StrictStr = Field(min_length=1, max_length=100)

    @field_validator("eleitor_id", "opcao")
    @classmethod
    def validar_texto(cls, valor):
        if not valor.strip() or not valor.isprintable() or valor != valor.strip():
            raise ValueError("Use texto sem controles ou espaços nas extremidades.")
        return valor


class VotoResponse(BaseModel):
    mensagem: str
    sessao_id: str
    placar: dict[str, int]
    # Presente apenas quando o voto foi registrado mas a publicação falhou.
    aviso: str | None = None


@app.post("/sessoes/{sessao_id}/votos", status_code=201, response_model=VotoResponse,
          response_model_exclude_none=True,
          responses={400: {"description": "Opção inválida"},
                     403: {"description": "Fora do prazo"},
                     404: {"description": "Sessão inexistente"},
                     409: {"description": "Voto duplicado"}})
def registrar_voto(sessao_id: str, voto: VotoRequest):
    sessao = app.state.sessoes.get(sessao_id)
    if sessao is None:
        registrar(logger, logging.WARNING, "voto", "rejeitado", sessao_id=sessao_id,
                  eleitor_id=voto.eleitor_id, motivo="sessao_inexistente")
        raise HTTPException(404, detail={"codigo": "sessao_inexistente",
                                         "mensagem": "Sessão não encontrada."})
    try:
        placar = sessao.registrar_voto(voto.eleitor_id, voto.opcao)
    except VotoRejeitado as erro:
        status = {"opcao_invalida": 400, "fora_do_prazo": 403, "voto_duplicado": 409}
        registrar(logger, logging.WARNING, "voto", "rejeitado", sessao_id=sessao_id,
                  eleitor_id=voto.eleitor_id, motivo=erro.codigo)
        raise HTTPException(status[erro.codigo],
                            detail={"codigo": erro.codigo, "mensagem": str(erro)}) from erro
    
    registrar(logger, logging.INFO, "voto", "aceito", sessao_id=sessao_id,
              eleitor_id=voto.eleitor_id)
    resposta = {"mensagem": "Voto registrado com sucesso.", "sessao_id": sessao.id,
                "placar": placar}
    # Votos rejeitados não publicam.
    try:
        with _publicacao_lock:
            publish_scoreboard_update(sessao.id, sessao.obter_placar())
    except PublicacaoFalhou:
        resposta["aviso"] = ("Voto registrado, mas a atualização da apuração "
                             "não pôde ser publicada.")
    return resposta


@app.exception_handler(RequestValidationError)
async def registrar_erro_validacao(request: Request, erro: RequestValidationError):
    if request.scope.get("endpoint") is registrar_voto:
        erros = erro.errors()
        eleitor_id = erro.body.get("eleitor_id") if isinstance(erro.body, dict) else None
        if not isinstance(eleitor_id, str) or any(
            tuple(item["loc"]) == ("body", "eleitor_id") for item in erros
        ):
            eleitor_id = None
        registrar(logger, logging.WARNING, "voto", "rejeitado",
                  sessao_id=request.path_params["sessao_id"], eleitor_id=eleitor_id,
                  motivo="validacao_invalida",
                  tipos_erro=sorted({item["type"] for item in erros}))

    return await request_validation_exception_handler(request, erro)


@app.exception_handler(StarletteHTTPException)
async def registrar_erro_leitura(request: Request, erro: StarletteHTTPException):
    # O FastAPI usa 400 com detalhe textual para falhas ao ler o corpo da rota.
    if (request.scope.get("endpoint") is registrar_voto and
            erro.status_code == 400 and isinstance(erro.detail, str)):
        registrar(logger, logging.WARNING, "voto", "rejeitado",
                  sessao_id=request.path_params["sessao_id"], motivo="corpo_invalido")
    return await http_exception_handler(request, erro)
