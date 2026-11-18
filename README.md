# Sistema distribuído de votação - Grupo 7

Projeto da disciplina CIN0143. A API **FastAPI** recebe e valida votos HTTP; o
**RabbitMQ** distribui eventos de atualização da apuração aos clientes inscritos.
A implementação legada de votação por **TCP** e **UDP** também está disponível.

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

O Compose inicia o RabbitMQ e, após o broker passar no health check, a API. No startup, a API abre uma conexão AMQP curta, declara o exchange `apuracao.votos` do tipo `fanout` e fecha essa conexão; ela não mantém uma conexão `BlockingConnection` ociosa. RabbitMQ foi escolhido para desacoplar quem publica a apuração dos clientes que a consomem: o exchange `fanout` distribui cada evento a todos os assinantes com filas vinculadas, sem a API precisar conhecer ou chamar cada cliente. O broker fica disponível em `localhost:5672`; a interface de gerenciamento fica em `http://localhost:15672` (usuário e senha padrão: `guest`).

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

### Registro de votos REST

A API reutiliza a classe `VotingSession` de `src/voting.py`. Ao iniciar, cria a
sessão demonstrativa **entrega1**, com opções A, B e C e duração de 300 segundos.
O estado está em `app.state.sessoes`, apenas em memória. Reiniciar a API zera os
votos e reinicia o prazo. Execute com um único worker: múltiplos processos teriam
sessões independentes. Após cada voto válido, a API publica o placar atualizado
na exchange `apuracao.votos` do RabbitMQ.

Cada sessão mantém os campos `id` (identificador da sessão), `opcoes` (opções
disponíveis), `placar` (contagem por opção), `eleitores` (identificadores que já
votaram), `inicio` e `fim` (instantes UTC que delimitam o prazo). `inicio` é
inclusivo e `fim` é exclusivo. Nesta API, a sessão demonstrativa usa o
identificador `entrega1`, opções A/B/C e janela de 300 segundos.

Envie `POST /sessoes/{sessao_id}/votos`, com corpo JSON:

```json
{"eleitor_id":"ana","opcao":"A"}
```

Os dois campos são strings obrigatórias de 1 a 100 caracteres, sem caracteres de
controle nem espaços nas extremidades. Campos adicionais são rejeitados. As opções
são comparadas exatamente como configuradas na sessão, inclusive maiúsculas.
Para conferir a rejeição de uma opção inválida, envie, por exemplo,
`{"eleitor_id":"carla","opcao":"Z"}`: a API responde **400** com o código
`opcao_invalida`, não registra o voto e não publica evento.

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

Com a API e o broker iniciados pelos comandos acima, inicie primeiro um cliente
de apuração em cada um de dois terminais separados:

```sh
python -m src.services.apuracao_client
```

Depois envie votos de dois eleitores distintos em outro terminal, usando `curl`
em um shell POSIX:

```sh
curl --request POST --url http://localhost:8000/sessoes/entrega1/votos --header 'Content-Type: application/json' --data-raw '{"eleitor_id":"ana","opcao":"A"}'
curl --request POST --url http://localhost:8000/sessoes/entrega1/votos --header 'Content-Type: application/json' --data-raw '{"eleitor_id":"bruno","opcao":"B"}'
```

Cada chamada normal retorna **201 Created** e o placar atualizado. Repita uma
chamada com o mesmo eleitor para observar o erro 409. A documentação interativa
está em `http://localhost:8000/docs`. Para começar de novo no Compose, execute
`docker compose restart api`.

Ambos os clientes ficam inscritos na exchange `apuracao.votos` (`fanout`) e
devem exibir cada atualização publicada enquanto estiverem conectados. Somente
votos aceitos publicam eventos; votos rejeitados, inclusive opção inválida, não
geram atualização. Inicie o cliente antes de votar: cada cliente cria uma fila
exclusiva e temporária, portanto não recebe eventos publicados antes de se
inscrever; sem clientes conectados não há consumidor para exibir o evento. O
evento publicado é JSON com `sessao_id`, `placar` e `data_hora` UTC,
por exemplo:

```json
{"sessao_id":"entrega1","placar":{"A":1,"B":0,"C":0},"data_hora":"2026-11-17T12:00:00+00:00"}
```

O voto é registrado em memória antes da tentativa de publicação. Se a publicação
falhar, a API ainda retorna **201**, pois o voto já foi registrado; a resposta
inclui `aviso` informando que a atualização não pôde ser publicada. Esta POC não
tem autenticação nem persistência: reiniciar a API apaga a sessão e os votos.
Também não há retry automático nem confirmação/garantia de entrega pelo broker;
uma falha pode deixar o voto registrado sem evento correspondente, e o cliente
não recebe histórico para recuperar atualizações perdidas.

Os testes em `tests/test_api_votes.py` e `tests/test_voting_session_votes.py`
cobrem os códigos HTTP, formato, regras, limites do prazo e votos simultâneos.
Os testes simulam a declaração da exchange
no startup da API, mas os votos aceitos em `test_api_votes.py` fazem publicação
real: RabbitMQ precisa estar disponível para executar a suíte.

## Arquitetura e protocolo atuais

Estrutura resumida do repositório:

```text
.
├── src/
│   ├── controllers/     # API FastAPI
│   ├── services/        # Integração RabbitMQ e cliente de apuração
│   └── voting.py        # Regras da sessão REST
├── tests/               # Testes da votação, API e RabbitMQ
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

| Arquivo | Responsabilidade |
| --- | --- |
| `src/controllers/api.py` | Health check, sessão demonstrativa, rota REST de votos e publicação da apuração. |
| `src/voting.py` | Sessão em memória e registro sequencial de votos protegido por trava. |
| `src/services/broker.py` | Conexão AMQP usando `RABBITMQ_URL`, declaração de `apuracao.votos` (`fanout`) e publicação de atualizações. |
| `src/services/apuracao_client.py` | Cliente que assina a exchange e exibe os eventos de apuração. |
| `Dockerfile` / `docker-compose.yml` | Imagem e execução da API e RabbitMQ, com health check do broker e inicialização ordenada. |
| `requirements.txt` | Dependências da API e do cliente RabbitMQ. |
| `tests/` | Testes automatizados da votação, API e integração RabbitMQ. |

Esta documentação cobre a API REST e a integração RabbitMQ, além da
implementação TCP/UDP preservada na branch `main-tcp-udp-implementation`
(consulte a seção abaixo). Os caminhos anteriores de compatibilidade da API
foram substituídos: use `src.controllers.api` (antes `src.api`) e
`src.services.broker` (antes `src.broker`).

Na API, cada voto válido tenta publicar no RabbitMQ um evento JSON contendo
`sessao_id`, uma cópia do `placar` e `data_hora` em UTC. A exchange `fanout`
distribui eventos às filas temporárias dos clientes conectados; eventos não são
armazenados para consumidores que iniciem depois.

## Testes

Instale dependências e inicie RabbitMQ antes de executar a suíte a partir da raiz.
O teste da API simula a declaração da exchange no startup, mas votos aceitos
publicam no broker real:

```sh
python -m pip install -r requirements.txt
docker compose up --build -d
python -m unittest discover -s tests -v
```

Os testes incluem regras de votação, concorrência, contrato REST, health check
e declaração/conexão RabbitMQ. O teste de voto aceito em `test_api_votes.py`
publica no broker real; os testes em `test_broker.py` simulam as operações AMQP.
O broker deve estar acessível em
`amqp://guest:guest@localhost:5672/`; para outro endereço, configure
`RABBITMQ_URL`. Encerre e remova os contêineres com `docker compose down`.

Como alternativa sem instalar Python ou dependências no host, com o Compose e o
RabbitMQ ativos, execute a suíte na imagem da API:

```sh
docker compose run --rm --no-deps -v "$PWD/tests:/app/tests:ro" api python -m unittest discover -s tests -v
```

## Branch de trabalho

As instruções deste README descrevem o conteúdo do repositório. Consulte o GitHub
para ver as branches disponíveis e a branch ativa do seu checkout.

## Implementação TCP/UDP (branch separada)

Os módulos e testes TCP/UDP são preservados na branch
`main-tcp-udp-implementation`. Para acessá-los, mude para essa branch:

```sh
git switch main-tcp-udp-implementation
```

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

Na branch TCP/UDP, os clientes enviam `JOIN identificador` e `VOTE opção`; o
servidor responde `SUCCESS` ou `ERROR mensagem`. Após cada voto aceito, envia
`UPDATE A:n B:n C:n`; ao encerrar, envia `END A:n B:n C:n`. TCP enquadra
mensagens por quebra de linha e trata fragmentação/agrupamento; UDP usa
datagramas, sem garantia de entrega ou ordem e sem retransmissão automática.
Identificadores não são autenticados, e votos e associações ficam apenas em
memória. No TCP o identificador está ligado à conexão, mas reconectar não
permite votar novamente; no UDP fica associado ao endereço IP e porta de
origem, e outro endereço não pode assumi-lo. Reiniciar o servidor apaga o
estado. Essa implementação é demonstrativa, não um sistema seguro para eleições
reais.
