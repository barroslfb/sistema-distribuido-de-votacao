from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from ..services.broker import declare_voting_exchange
from ..voting import VotingSession, VotoRejeitado


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.post("/sessoes/{sessao_id}/votos", status_code=201, response_model=VotoResponse,
          responses={400: {"description": "Opção inválida"},
                     403: {"description": "Fora do prazo"},
                     404: {"description": "Sessão inexistente"},
                     409: {"description": "Voto duplicado"}})
def registrar_voto(sessao_id: str, voto: VotoRequest):
    sessao = app.state.sessoes.get(sessao_id)
    if sessao is None:
        raise HTTPException(404, detail={"codigo": "sessao_inexistente",
                                         "mensagem": "Sessão não encontrada."})
    try:
        placar = sessao.registrar_voto(voto.eleitor_id, voto.opcao)
    except VotoRejeitado as erro:
        status = {"opcao_invalida": 400, "fora_do_prazo": 403, "voto_duplicado": 409}
        raise HTTPException(status[erro.codigo],
                            detail={"codigo": erro.codigo, "mensagem": str(erro)}) from erro
    return {"mensagem": "Voto registrado com sucesso.", "sessao_id": sessao.id,
            "placar": placar}
