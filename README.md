# Sistema distribuído de votação - Grupo 7

Projeto da disciplina CIN0143. O repositório contém a implementação legada de votação por **TCP** e **UDP**, uma API **FastAPI** e uma conexão inicial com **RabbitMQ**.

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

A API está em `src/controllers/api.py`. FastAPI foi escolhido para expor endpoints HTTP de forma simples e oferecer validação e documentação automática da API. Após instalar as dependências, inicie-a localmente com:

```sh
uvicorn src.controllers.api:app --host 0.0.0.0 --port 8000
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

O Compose inicia o RabbitMQ e, após o broker passar no health check, a API. No startup, a API abre uma conexão AMQP curta, declara o exchange `apuracao.votos` do tipo `fanout` e fecha essa conexão; ela não mantém uma conexão `BlockingConnection` ociosa. O broker fica disponível em `localhost:5672`; a interface de gerenciamento fica em `http://localhost:15672` (usuário e senha padrão: `guest`).

Para verificar disponibilidade, inicialização da API e exchange declarado, execute:

```sh
# Broker saudável (resultado: "Ping succeeded")
docker compose exec rabbitmq rabbitmq-diagnostics -q ping

# API disponível; resultado esperado: {"status":"ok"}
curl http://localhost:8000/health

# O exchange deve aparecer como apuracao.votos / fanout
docker compose exec rabbitmq rabbitmqctl list_exchanges name type

# O startup confirma a declaração; falhas de conexão/declaração aparecem aqui
docker compose logs api
```

Se o broker não estiver disponível ou a declaração falhar, a API não completa o startup; confira os logs e o health check do broker.

Ao executar a API fora do Compose, configure `RABBITMQ_URL` para uma URL AMQP acessível. O padrão local é `amqp://guest:guest@localhost:5672/`. A API não inicia se não conseguir conectar ao broker ou declarar o exchange.

### Registro de votos REST — Feature 14

A API reutiliza a classe `VotingSession` de `src/voting.py`. Ao iniciar, cria a
sessão demonstrativa **entrega1**, com opções A, B e C e duração de 300 segundos.
O estado está em `app.state.sessoes`, apenas em memória. Reiniciar a API zera os
votos e reinicia o prazo. Execute com um único worker: múltiplos processos teriam
sessões independentes. Esta feature não adiciona cadastro de sessões ou publicação
de eventos; a apuração via RabbitMQ será implementada na Feature 16.

Envie `POST /sessoes/{sessao_id}/votos`, com corpo JSON:

```json
{"eleitor_id":"ana","opcao":"A"}
```

Os dois campos são strings obrigatórias de 1 a 100 caracteres, sem caracteres de
controle nem espaços nas extremidades. Campos adicionais são rejeitados. As opções
são comparadas exatamente como configuradas na sessão, inclusive maiúsculas.

Após validar o formato e localizar a sessão, a ordem é **opção válida → prazo →
voto duplicado → registro**. O prazo inclui o início e exclui o fim. Uma trava por
sessão protege a sequência completa, evitando que dois pedidos simultâneos do mesmo
eleitor sejam registrados. Votos rejeitados não alteram o estado. O método
`registrar_voto()` atualiza o placar e o histórico do eleitor e retorna uma cópia
do placar. As consultas da sessão também são protegidas pela mesma trava.

| HTTP | Resultado |
| --- | --- |
| 201 | Voto registrado; retorna `mensagem`, `sessao_id` e `placar` |
| 400 | `opcao_invalida` |
| 403 | `fora_do_prazo` (ainda não iniciou ou já terminou) |
| 404 | `sessao_inexistente` |
| 409 | `voto_duplicado` |
| 422 | Corpo JSON ou formato dos campos inválido, descrito em `detail` |

Exemplo de resposta 201:

```json
{"mensagem":"Voto registrado com sucesso.","sessao_id":"entrega1","placar":{"A":1,"B":0,"C":0}}
```

Os erros de negócio usam este formato (exemplo de resposta 409):

```json
{"detail":{"codigo":"voto_duplicado","mensagem":"Este eleitor já votou nesta sessão."}}
```

Com a API e o broker iniciados pelos comandos acima, envie no PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/sessoes/entrega1/votos -ContentType 'application/json' -Body '{"eleitor_id":"ana","opcao":"A"}'
```

Repita para observar o erro 409 ou use outro eleitor. A documentação interativa
está em `http://localhost:8000/docs`. Para começar de novo no Compose, execute
`docker compose restart api`.

Os testes em `tests/test_api_votes.py` e `tests/test_voting_session_votes.py`
cobrem os códigos HTTP, formato, regras, limites do prazo, isolamento entre sessões,
cópias de consulta e votos simultâneos. São executados pelo mesmo comando da suíte
abaixo; a conexão inicial com RabbitMQ é simulada nos testes da API.

### Implementação legada TCP/UDP

Escolha uma das versões e mantenha o servidor em execução enquanto usa os clientes. A votação começa ao iniciar o servidor e dura **300 segundos**, por padrão.

### TCP

Em um terminal, inicie o servidor:

```sh
python -m src.tcp_udp.server
```

Em outro terminal, inicie um cliente TCP; repita em outros terminais para adicionar participantes:

```sh
python -m src.tcp_udp.client
```

O endereço padrão é `127.0.0.1:5000`.

### UDP

Em um terminal, inicie o servidor:

```sh
python -m src.tcp_udp.server_udp
```

Em outro terminal, inicie um cliente UDP; repita em outros terminais para adicionar participantes:

```sh
python -m src.tcp_udp.client_udp
```

O endereço padrão é `127.0.0.1:5001`. O cliente UDP também aceita endereço e porta pela linha de comando:

```sh
python -m src.tcp_udp.client_udp --host 127.0.0.1 --port 5001
```

Use sempre o cliente correspondente ao protocolo do servidor. TCP e UDP podem ser iniciados simultaneamente nas portas padrão, mas são votações independentes.

### Votar

1. Quando solicitado, informe um identificador sem espaços, por exemplo `alice`. O cliente envia automaticamente `JOIN alice`.
2. Após receber `SUCCESS`, digite `VOTE A`, `VOTE B` ou `VOTE C` e pressione Enter.
3. Um voto aceito recebe `SUCCESS` e gera uma atualização, por exemplo `UPDATE A:1 B:0 C:0`. Ao fim do prazo, os clientes recebem o resultado, por exemplo `END A:1 B:0 C:0`.
4. Para experimentar com mais participantes, abra outros clientes do mesmo protocolo e use identificadores diferentes. Encerre clientes e servidor com `Ctrl+C`.

Cada identificador pode votar uma única vez por votação. Opções inválidas, votos repetidos e votos fora do prazo recebem uma resposta `ERROR` com a descrição do problema.

### Configuração e execução em máquinas diferentes

Por padrão, `127.0.0.1` permite conexões apenas na própria máquina. Para acessar o servidor pela rede, ajuste `HOST` em `src/tcp_udp/server.py` ou `src/tcp_udp/server_udp.py` para uma interface acessível (por exemplo, `0.0.0.0`) e permita a porta correspondente no firewall. No cliente TCP, altere `HOST` em `src/tcp_udp/client.py` para o IP do servidor; no UDP, use `--host IP_DO_SERVIDOR` ou altere `HOST` em `src/tcp_udp/client_udp.py`.

As constantes `PORT` nos arquivos do servidor e do cliente devem corresponder; no cliente UDP também é possível usar `--port`. A duração é configurada em segundos pela constante `DURACAO_VOTACAO` do servidor escolhido. Reinicie o servidor após alterar sua configuração.

## Arquitetura e protocolo atuais

Estrutura resumida do repositório:

```text
.
├── src/
│   ├── controllers/     # API FastAPI
│   ├── services/        # Serviço RabbitMQ
│   └── tcp_udp/         # Implementação legada TCP/UDP
├── tests/               # Testes de votação, comunicação e API
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

| Arquivo | Responsabilidade |
| --- | --- |
| `src/tcp_udp/server.py` / `src/tcp_udp/client.py` | Servidor TCP (uma thread por conexão) e cliente. |
| `src/tcp_udp/server_udp.py` / `src/tcp_udp/client_udp.py` | Servidor UDP e cliente; o servidor associa a sessão ao endereço IP e porta de origem. |
| `src/tcp_udp/voting.py` | Regras, prazo, contagem e histórico de votos legados, protegidos por trava. |
| `src/tcp_udp/protocol.py` | Codificação UTF-8 e enquadramento das mensagens TCP por quebra de linha. |
| `src/controllers/api.py` | Health check, sessão demonstrativa, rota REST de votos e declaração do exchange no startup. |
| `src/voting.py` | Sessão em memória e registro sequencial de votos protegido por trava. |
| `src/services/broker.py` | Conexão AMQP curta usando `RABBITMQ_URL` e declaração de `apuracao.votos` (`fanout`). |
| `Dockerfile` / `docker-compose.yml` | Imagem e execução da API e RabbitMQ, com health check do broker e inicialização ordenada. |
| `requirements.txt` | Dependências da API e do cliente RabbitMQ. |
| `tests/` | Testes automatizados da votação, comunicação legada, API e criação da conexão RabbitMQ. |

Essa estrutura separa a API e os serviços atuais da implementação legada TCP/UDP. Os caminhos anteriores de compatibilidade foram removidos: use `src.controllers.api` (antes `src.api`), `src.services.broker` (antes `src.broker`) e `src.tcp_udp.*` para clientes, servidores, protocolo e votação legados (antes os módulos equivalentes na raiz de `src`). Os antigos wrappers `src.controllers.server`, `src.controllers.server_udp`, `src.models.voting` e `src.services.protocol` também não existem mais; use os módulos canônicos listados na tabela acima.

Os clientes enviam `JOIN identificador` e `VOTE opção`; o servidor responde `SUCCESS` ou `ERROR mensagem`. Após cada voto aceito, o servidor envia `UPDATE A:n B:n C:n` aos clientes conectados por TCP ou cadastrados por UDP; ao encerrar, envia `END A:n B:n C:n`. No TCP, as mensagens são delimitadas por quebra de linha e o receptor trata fragmentação e agrupamento. No UDP, são enviados datagramas, sem garantia de entrega ou ordem e sem retransmissão automática.

No TCP, o identificador pertence à conexão e pode ser usado em uma reconexão, mas não permite votar novamente. No UDP, um identificador fica associado ao endereço de origem durante a execução do servidor; outro endereço não pode assumir esse identificador. Identificadores não são autenticados. Votos e associações ficam apenas na memória e são perdidos ao reiniciar o servidor. O projeto é demonstrativo, não um sistema seguro para eleições reais.

## Próxima etapa: publicação da apuração

A votação HTTP já está implementada na Feature 14 pela rota
`POST /sessoes/{sessao_id}/votos`. A API valida e registra votos na sessão em
memória, atualizando o placar e impedindo votos duplicados.

A publicação de eventos de apuração no RabbitMQ ainda será implementada na
Feature 16. A configuração do broker no Compose e a declaração inicial do
exchange `apuracao.votos` (`fanout`) já existem; falta publicar o placar após
cada voto válido e disponibilizar as atualizações aos consumidores.

## Testes

Execute a suíte a partir da raiz, sem iniciar os servidores manualmente:

```sh
python -m unittest discover -s tests -v
```

Os testes incluem regras de votação, concorrência, comunicação UDP, envio de atualizações e resultado final, além do health check e teste isolado da criação da conexão RabbitMQ. Alguns abrem sockets locais. Não é necessário iniciar RabbitMQ para executar a suíte.

## Branch de trabalho

As instruções deste README descrevem o conteúdo do repositório. Consulte o GitHub
para ver as branches disponíveis e a branch ativa do seu checkout.
