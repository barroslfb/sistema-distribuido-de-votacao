# Testes

A suíte contém exatamente 12 testes:

1. Integração: votos simultâneos de eleitores diferentes.
2. Integração: votos simultâneos repetidos pelo mesmo eleitor.
3. Integração: entrega `fanout` a dois assinantes.
4. Integração: votos rejeitados não alteram o placar nem publicam evento.
5. Regras: registra voto válido e atualiza placar e eleitores.
6. Regras: opção inválida, voto duplicado e fora do prazo rejeitam sem alterar estado.
7. Regras: valida o prazo com início inclusivo e fim exclusivo.
8. API: entradas inválidas e sessão inexistente são rejeitadas sem alterar estado.
9. API: falha na publicação preserva o voto e retorna aviso.
10. Cliente de votação: exibe o resultado de voto aceito e rejeitado.
11. Cliente de apuração: recebe e exibe a atualização do placar.
12. Broker: falha de conexão apresenta erro claro sem expor credenciais.

## Dependências e execução

Instale as dependências de `requirements.txt` e inicie o RabbitMQ:

```sh
pip install -r requirements.txt
docker compose up -d rabbitmq
python -m unittest discover -s tests -v
```

Os testes de integração usam a API em processo real e RabbitMQ acessível em
`amqp://guest:guest@localhost:5672/`. Para outro endereço, defina `RABBITMQ_URL`.
Os demais testes substituem as dependências HTTP/RabbitMQ por mocks. Sem broker
disponível, os testes de integração falham; não são ignorados automaticamente.
