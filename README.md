# Sistema distribuído de votação — Grupo 7

Projeto da disciplina CIN0143: votação com clientes e servidor que se comunicam por sockets TCP.

## Arquitetura e funcionamento

- `src/server.py` inicia o servidor TCP e cria uma thread para cada conexão. A votação compartilhada é iniciada pelo servidor.
- `src/client.py` conecta ao servidor, envia o identificador e permite digitar comandos. Uma thread separada recebe respostas e atualizações enquanto o usuário digita.
- `src/voting.py` mantém em memória os votos para as opções A, B e C. Uma trava protege a validação e o registro; cada identificador pode votar uma única vez durante a votação.
- `src/protocol.py` codifica mensagens UTF-8 terminadas por newline e reúne os fragmentos recebidos pelo TCP até completar cada mensagem.

O protocolo aceita `JOIN identificador` e `VOTE A`, `VOTE B` ou `VOTE C`. O servidor responde `SUCCESS` ou `ERROR mensagem`. Após cada voto aceito, envia `UPDATE A:n B:n C:n` a todos os clientes conectados, inclusive quem votou. Ao expirar o prazo, envia `END A:n B:n C:n`. O cliente exibe essas mensagens recebidas.

O identificador é definido no `JOIN` e não pode ser trocado na mesma conexão. Uma reconexão pode usar o mesmo identificador, mas não registrar outro voto. Identificadores não têm autenticação. Os votos e o histórico existem apenas na memória do processo; reiniciar o servidor inicia uma votação nova.

## Requisitos

Python 3.10 ou superior. O projeto usa apenas a biblioteca padrão do Python; não requer instalação de dependências externas.

## Executar

Na raiz do projeto, inicie o servidor:

```sh
python -m src.server
```

Por padrão, ele escuta em `127.0.0.1:5000` e a votação dura 300 segundos. Em cada outro terminal, inicie um cliente:

```sh
python -m src.client
```

Informe o identificador quando solicitado. Depois, envie um voto digitando, por exemplo, `VOTE A` e pressionando Enter. Para encerrar os processos, use Ctrl+C. O host, a porta e a duração são definidos pelas constantes `HOST`, `PORT` e `DURACAO_VOTACAO` em `src/server.py` e `src/client.py`; para máquinas diferentes, configure o servidor para escutar em uma interface acessível e ajuste o `HOST` do cliente para o endereço do servidor.

## Testar

Na raiz do repositório, execute a suíte com a biblioteca `unittest`:

```sh
python -m unittest discover -s tests -v
```

Os testes cobrem validação e prazo da votação, votos duplicados e concorrentes, enquadramento de mensagens TCP fragmentadas ou agrupadas, comunicação cliente-servidor, broadcasts `UPDATE` e `END` e desconexões. Há testes unitários e testes de integração que abrem sockets TCP locais; não é necessário iniciar manualmente o servidor ou clientes para rodar a suíte.

Para conferir manualmente, inicie o servidor e dois clientes. Vote com um identificador e tente votar novamente com o mesmo identificador em outra conexão: o segundo voto deve receber `ERROR`. O voto aceito deve gerar uma atualização nos clientes conectados. Um voto com opção fora de A, B ou C também deve ser rejeitado.
