# Sistema distribuído de votação - Grupo 7

Projeto da disciplina CIN0143. O repositório contém a implementação legada de votação por **TCP** e **UDP** e a base inicial de uma API **FastAPI**. A arquitetura distribuída com **RabbitMQ** ainda está planejada e não foi implementada.

## Requisitos

- Python 3.10 ou superior.
- A implementação legada usa apenas a biblioteca padrão. A API requer as dependências de `requirements.txt`.
- Docker e Docker Compose para executar a API em contêineres.
- Um terminal para o servidor e pelo menos um terminal para cada cliente. Execute os comandos a partir da raiz do repositório.

Para instalar as dependências locais da API e dos testes, execute antes de iniciar o Uvicorn ou a suíte:

```sh
python -m pip install -r requirements.txt
```

## Como executar

### API FastAPI

A API inicial está em `src/api.py`. FastAPI foi escolhido para expor endpoints HTTP de forma simples e oferecer validação e documentação automática da API. Após instalar as dependências, inicie-a localmente com:

```sh
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

O health check `GET /health` responde na porta **8000**. Verifique-o com:

```sh
curl http://localhost:8000/health
```

Resposta esperada:

```json
{"status":"ok"}
```

Também é possível iniciar a API pelo Docker Compose:

```sh
docker compose up --build
```

Para encerrar e remover os contêineres:

```sh
docker compose down
```

O Compose atual sobe somente a API. RabbitMQ e sua integração ainda não estão configurados.

### Implementação legada TCP/UDP

Escolha uma das versões e mantenha o servidor em execução enquanto usa os clientes. A votação começa ao iniciar o servidor e dura **300 segundos**, por padrão.

### TCP

Em um terminal, inicie o servidor:

```sh
python -m src.server
```

Em outro terminal, inicie um cliente TCP; repita em outros terminais para adicionar participantes:

```sh
python -m src.client
```

O endereço padrão é `127.0.0.1:5000`.

### UDP

Em um terminal, inicie o servidor:

```sh
python -m src.server_udp
```

Em outro terminal, inicie um cliente UDP; repita em outros terminais para adicionar participantes:

```sh
python -m src.client_udp
```

O endereço padrão é `127.0.0.1:5001`. O cliente UDP também aceita endereço e porta pela linha de comando:

```sh
python -m src.client_udp --host 127.0.0.1 --port 5001
```

Use sempre o cliente correspondente ao protocolo do servidor. TCP e UDP podem ser iniciados simultaneamente nas portas padrão, mas são votações independentes.

### Votar

1. Quando solicitado, informe um identificador sem espaços, por exemplo `alice`. O cliente envia automaticamente `JOIN alice`.
2. Após receber `SUCCESS`, digite `VOTE A`, `VOTE B` ou `VOTE C` e pressione Enter.
3. Um voto aceito recebe `SUCCESS` e gera uma atualização, por exemplo `UPDATE A:1 B:0 C:0`. Ao fim do prazo, os clientes recebem o resultado, por exemplo `END A:1 B:0 C:0`.
4. Para experimentar com mais participantes, abra outros clientes do mesmo protocolo e use identificadores diferentes. Encerre clientes e servidor com `Ctrl+C`.

Cada identificador pode votar uma única vez por votação. Opções inválidas, votos repetidos e votos fora do prazo recebem uma resposta `ERROR` com a descrição do problema.

### Configuração e execução em máquinas diferentes

Por padrão, `127.0.0.1` permite conexões apenas na própria máquina. Para acessar o servidor pela rede, ajuste `HOST` em `src/server.py` ou `src/server_udp.py` para uma interface acessível (por exemplo, `0.0.0.0`) e permita a porta correspondente no firewall. No cliente TCP, altere `HOST` em `src/client.py` para o IP do servidor; no UDP, use `--host IP_DO_SERVIDOR` ou altere `HOST` em `src/client_udp.py`.

As constantes `PORT` nos arquivos do servidor e do cliente devem corresponder; no cliente UDP também é possível usar `--port`. A duração é configurada em segundos pela constante `DURACAO_VOTACAO` do servidor escolhido. Reinicie o servidor após alterar sua configuração.

## Arquitetura e protocolo atuais

Estrutura resumida do repositório:

```text
.
├── src/                 # Implementação legada e API inicial
├── tests/               # Testes de votação, comunicação e API
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

| Arquivo | Responsabilidade |
| --- | --- |
| `src/server.py` / `src/client.py` | Servidor e cliente TCP; o servidor usa uma thread por conexão. |
| `src/server_udp.py` / `src/client_udp.py` | Servidor e cliente UDP; o servidor associa a sessão ao endereço IP e porta de origem. |
| `src/voting.py` | Regras, prazo, contagem e histórico de votos, protegidos por trava. |
| `src/protocol.py` | Codificação UTF-8 e enquadramento das mensagens TCP por quebra de linha. |
| `src/api.py` | API FastAPI inicial, com o endpoint `GET /health`. |
| `Dockerfile` / `docker-compose.yml` | Imagem e execução da API na porta 8000; o Compose ainda não inclui RabbitMQ. |
| `requirements.txt` | Dependências iniciais da API. |
| `tests/` | Testes automatizados da votação, comunicação legada e health check da API. |

Os clientes enviam `JOIN identificador` e `VOTE opção`; o servidor responde `SUCCESS` ou `ERROR mensagem`. Após cada voto aceito, o servidor envia `UPDATE A:n B:n C:n` aos clientes conectados por TCP ou cadastrados por UDP; ao encerrar, envia `END A:n B:n C:n`. No TCP, as mensagens são delimitadas por quebra de linha e o receptor trata fragmentação e agrupamento. No UDP, são enviados datagramas, sem garantia de entrega ou ordem e sem retransmissão automática.

No TCP, o identificador pertence à conexão e pode ser usado em uma reconexão, mas não permite votar novamente. No UDP, um identificador fica associado ao endereço de origem durante a execução do servidor; outro endereço não pode assumir esse identificador. Identificadores não são autenticados. Votos e associações ficam apenas na memória e são perdidos ao reiniciar o servidor. O projeto é demonstrativo, não um sistema seguro para eleições reais.

## Arquitetura planejada e próximos passos

A evolução planejada é integrar a API FastAPI ao RabbitMQ para comunicação distribuída. RabbitMQ é planejado como broker de mensagens para desacoplar os serviços e transportar eventos de votação; o broker, os fluxos de mensagens e sua orquestração ainda **não foram implementados**. A API e o health check já têm uma implementação inicial, mas o projeto disponível hoje não apresenta um sistema de votação HTTP integrado ao broker.

Componentes previstos, ainda sem arquivos ou implementação:

- **Cliente de apuração:** futuro consumidor de resultados/eventos para reunir ou consultar a apuração distribuída.
- **Integração com o broker:** futuro componente responsável pela publicação e pelo consumo de mensagens via RabbitMQ. Os nomes/caminhos dos módulos serão definidos durante a implementação.

Próximos passos não implementados:

1. Adicionar RabbitMQ ao Docker Compose e definir sua configuração de saúde e inicialização.
2. Implementar a integração da API com o broker e os fluxos distribuídos de votação.
3. Criar testes para os endpoints e a integração com RabbitMQ.
4. Atualizar esta documentação conforme os componentes forem implementados.

## Testes

Execute a suíte a partir da raiz, sem iniciar os servidores manualmente:

```sh
python -m unittest discover -s tests -v
```

Os testes incluem regras de votação, concorrência, comunicação UDP, envio de atualizações e resultado final, além do health check da API. Alguns abrem sockets locais. Ainda não há testes para integração com RabbitMQ.

## Branches

Branches locais observadas no repositório:

- `main`
- `main-tcp-udp-implementation`
- `feature-12/organizacao-base` (branch atual durante a atualização deste README)

`main` é a linha principal do projeto; `main-tcp-udp-implementation` identifica a implementação legada TCP/UDP. `feature-12/organizacao-base` é a branch atual durante a atualização deste README. Esses nomes não significam que RabbitMQ já esteja implementado.
