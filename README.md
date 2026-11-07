# Sistema distribuído de votação - Grupo 7

Projeto da disciplina CIN0143 que implementa um serviço de votação distribuída em duas versões: **TCP** e **UDP**. Ambas oferecem os mesmos comandos e regras de votação, mas usam transportes diferentes. Cada servidor mantém sua própria votação em memória; executar os dois não compartilha votos nem resultados.

## Requisitos

- Python 3.10 ou superior.
- Nenhuma dependência externa: apenas a biblioteca padrão do Python.
- Um terminal para o servidor e pelo menos um terminal para cada cliente. Execute os comandos a partir da raiz do repositório.

## Como executar

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

## Arquitetura e protocolo

| Arquivo | Responsabilidade |
| --- | --- |
| `src/server.py` / `src/client.py` | Servidor e cliente TCP; o servidor usa uma thread por conexão. |
| `src/server_udp.py` / `src/client_udp.py` | Servidor e cliente UDP; o servidor associa a sessão ao endereço IP e porta de origem. |
| `src/voting.py` | Regras, prazo, contagem e histórico de votos, protegidos por trava. |
| `src/protocol.py` | Codificação UTF-8 e enquadramento das mensagens TCP por quebra de linha. |
| `tests/` | Testes automatizados da votação e da comunicação. |

Os clientes enviam `JOIN identificador` e `VOTE opção`; o servidor responde `SUCCESS` ou `ERROR mensagem`. Após cada voto aceito, o servidor envia `UPDATE A:n B:n C:n` aos clientes conectados por TCP ou cadastrados por UDP; ao encerrar, envia `END A:n B:n C:n`. No TCP, as mensagens são delimitadas por quebra de linha e o receptor trata fragmentação e agrupamento. No UDP, são enviados datagramas, sem garantia de entrega ou ordem e sem retransmissão automática.

No TCP, o identificador pertence à conexão e pode ser usado em uma reconexão, mas não permite votar novamente. No UDP, um identificador fica associado ao endereço de origem durante a execução do servidor; outro endereço não pode assumir esse identificador. Identificadores não são autenticados. Votos e associações ficam apenas na memória e são perdidos ao reiniciar o servidor. O projeto é demonstrativo, não um sistema seguro para eleições reais.

## Testes

Execute a suíte a partir da raiz, sem iniciar os servidores manualmente:

```sh
python -m unittest discover -s tests -v
```

Os testes incluem regras de votação, concorrência, comunicação UDP e envio de atualizações e resultado final. Alguns abrem sockets locais.
