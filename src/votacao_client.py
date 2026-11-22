"""Envia um voto à API REST pelo terminal."""

import argparse
import sys
from urllib.parse import quote

import httpx


def corpo_json(resposta):
    try:
        corpo = resposta.json()
    except ValueError:
        return {}
    return corpo if isinstance(corpo, dict) else {}


def mensagem_rejeicao(resposta):
    detalhe = corpo_json(resposta).get("detail")
    if isinstance(detalhe, dict) and isinstance(detalhe.get("mensagem"), str):
        return detalhe["mensagem"]
    if isinstance(detalhe, list):
        erros = [
            f"{erro['loc'][-1]}: {erro['msg']}"
            for erro in detalhe
            if isinstance(erro, dict) and isinstance(erro.get("loc"), list)
            and erro["loc"] and isinstance(erro.get("msg"), str)
        ]
        if erros:
            return " | ".join(erros)
    return f"A API recusou a requisição (HTTP {resposta.status_code})."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000", help="endereço base da API")
    parser.add_argument("--sessao", default="entrega1", help="identificador da sessão de votação")
    args = parser.parse_args(argv)

    try:
        eleitor_id = input("Identificador do eleitor: ")
        opcao = input("Opção de voto: ")
    except (EOFError, KeyboardInterrupt):
        print("\nEntrada interrompida. Voto não enviado.", file=sys.stderr)
        return 1

    url = f"{args.api_url.rstrip('/')}/sessoes/{quote(args.sessao, safe='')}/votos"
    try:
        resposta = httpx.post(url, json={"eleitor_id": eleitor_id, "opcao": opcao}, timeout=5.0)
    except httpx.InvalidURL:
        print("Endereço da API inválido. Confira a opção --api-url.", file=sys.stderr)
        return 1
    except (httpx.RequestError, KeyboardInterrupt):
        print("Falha de comunicação com a API. Não foi possível confirmar o registro do voto.",
              file=sys.stderr)
        return 1

    if resposta.status_code == 201:
        corpo = corpo_json(resposta)
        print(corpo.get("mensagem") or "Voto registrado com sucesso.")
        if corpo.get("aviso"):
            print(corpo["aviso"])
        return 0

    if resposta.is_client_error:
        print(f"Voto rejeitado. {mensagem_rejeicao(resposta)}", file=sys.stderr)
        return 1

    print(f"Resposta inesperada da API (HTTP {resposta.status_code}). "
          "Não foi possível confirmar o registro do voto.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
