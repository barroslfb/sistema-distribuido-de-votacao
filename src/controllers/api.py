from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..services.broker import declare_voting_exchange


@asynccontextmanager
async def lifespan(app: FastAPI):
    declare_voting_exchange()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
