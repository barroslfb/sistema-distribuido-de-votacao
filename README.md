# Sistema distribuído de votação — Grupo 7

Projeto da CIN0143: votação multiusuário no modelo cliente-servidor com sockets TCP.

## Executar

Requer Python 3.10 ou superior. Não há dependências externas. Na raiz do projeto:

```sh
python -m src.server
```

Em outros terminais (um por participante):

```sh
python -m src.client
```

Informe um ID, por exemplo `theo`. O cliente envia `JOIN theo` automaticamente.
Depois digite `VOTE A`, `VOTE B` ou `VOTE C`, pressionando Enter.
O servidor escuta em `127.0.0.1:5000` e inicia uma votação de 300 segundos.
A duração é definida por `DURACAO_VOTACAO` em `src/server.py`.
Para encerrar o processo, use Ctrl+C.

Por padrão, tudo roda na mesma máquina. Para computadores diferentes na mesma
rede, configure o `HOST` do servidor com o endereço da interface de rede e o
`HOST` dos clientes com o IP do servidor; a porta deve estar acessível na rede.

## Feature 4: registro e validação

O servidor mantém uma instância compartilhada de `Voting` e uma thread por
conexão. Cada conexão tem uma `SessaoVotacao`, que guarda o ID recebido no `JOIN`.
O ID não pode ser trocado durante a conexão. Outro socket pode usar o mesmo ID,
mas o histórico compartilhado impede que esse ID registre dois votos.

Fluxo de exemplo no protocolo (cada mensagem termina com `\n`):

```text
cliente -> servidor: JOIN theo
servidor -> cliente: SUCCESS
cliente -> servidor: VOTE A
servidor -> cliente: SUCCESS
cliente -> servidor: VOTE B
servidor -> cliente: ERROR Este identificador já votou.
```

`Voting.registro_voto(candidate, participante)` verifica o prazo, o ID, a opção
e a existência de voto anterior. Somente então salva o voto no dicionário
`_votos_por_participante` e incrementa a contagem em `votos`.
Uma mesma trava (`threading.Lock`) protege todas essas etapas: duas threads
com o mesmo ID não conseguem passar pela verificação de duplicidade juntas.
Erros lançam `ValueError` ou `RuntimeError`; a sessão os converte em `ERROR mensagem`.
`obter_resultados()` fornece uma cópia da contagem sob a mesma trava para a feature 5.

O TCP entrega um fluxo ordenado de bytes; ele não separa comandos. Por isso,
`NewlineFramer` acumula fragmentos até encontrar `\n`, inclusive quando um comando
chega em vários `recv()` ou vários comandos chegam juntos. O servidor responde
com `sendall()`, usando UTF-8 e o mesmo delimitador. A trava resolve a concorrência
na memória; essa garantia não vem do TCP.

## Testar

```sh
python -m unittest discover -s tests -v
```

Os testes verificam opções e IDs inválidos, duplicidade, prazo, concorrência,
comandos fragmentados e respostas por sockets TCP reais. Para conferir manualmente:
vote com `theo`, reconecte usando `theo` e tente votar de novo; o servidor rejeita.
Com um novo ID, tente `VOTE D` e depois `VOTE B`: só o segundo deve ser aceito.

## Escopo e limitações

- Os votos ficam em memória enquanto o servidor estiver em execução; reiniciar
  o processo cria outra votação e limpa o histórico.
- O ID é informado pelo usuário, sem autenticação. A regra garante um voto por
  ID, mas não impede uma pessoa de escolher outros IDs.
- A transmissão automática de `UPDATE` e `END` para todos os clientes pertence
  à feature 5 e ainda não está implementada nesta alteração. A rejeição de votos
  após o prazo já está ativa. Antes da entrega final do grupo, é necessário
  integrar e validar essa transmissão.

Enunciado: [APS01.pdf — Equipe 07](https://drive.google.com/file/d/1LNG6CI6kbngRP2qx7o4vVL51vPYGQAOB/view).
Entrega: link do GitHub com código organizado e instruções neste README,
até 30/10/2026 às 23:59, por um integrante do grupo.
