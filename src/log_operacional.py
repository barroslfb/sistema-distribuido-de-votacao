"""Configuração e campos dos logs operacionais no console."""

import json
import logging


def configurar_logs():
    logger = logging.getLogger("src")
    if not logger.handlers:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(console)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def registrar(logger, nivel, operacao, resultado, **campos):
    partes = [f"operacao={operacao}", f"resultado={resultado}"]
    partes.extend(
        f"{chave}={json.dumps(valor)}" for chave, valor in campos.items() if valor is not None
    )
    logger.log(nivel, " ".join(partes))
