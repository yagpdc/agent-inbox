# agent-inbox

Assistente local que atende pedidos que chegam por DM no Google Chat e os transforma em trabalho feito por agentes de IA, com revisão humana no PR.

> **Quer entender ou montar o seu?**
> - [**Apresentação**](https://yagpdc.github.io/agent-inbox/apresentacao/): 15 slides explicando como funciona, para quem não é dev. Abre direto no navegador ([arquivos](apresentacao/)).
> - [**Prompt**](apresentacao/PROMPT.md): cole no Claude Code e ele monta um app igual com você, adaptado ao seu trabalho.

## Como funciona

1. **Vigia**: lê as DMs pela API do Google Chat.
2. **Orquestrador**: é o único que conversa com as pessoas. Responde em JSON validado por schema: responder, montar ficha, pedir confirmação, recusar fora do escopo, chamar o dono. Monta a ficha do pedido no contrato do agente certo e confirma com quem pediu.
3. **Servidor**: garante as regras no código, e não no prompt:
   - a confirmação vale por 3 h;
   - cada pessoa tem no máximo 2 tarefas abertas;
   - o workspace só pode vir do catálogo;
   - pedido fora do escopo não vira tarefa.
4. **Agentes por tipo** (`agentes/<tipo>/agente.json`): planejam com um modelo maior, executam com um menor, trabalham num worktree isolado e abrem PR.
5. **PR**: o merge é a aprovação e dispara o deploy. Um "request changes" devolve a tarefa ao agente com os comentários.
6. **Marcos**: quem pediu recebe avisos em linguagem simples (vamos fazer, estamos fazendo, terminamos, está no ar). Mensagem que falha vai para uma fila de reenvio.

Stack: Python (só stdlib), SQLite, SSE e um painel em JavaScript puro, sem build, em `http://localhost:8787`. Os agentes rodam no [Claude Code](https://claude.com/claude-code) em modo headless (`claude -p`). No Windows, os processos dos agentes ficam presos num Job Object e morrem junto com o servidor.

## Rodar

Requisitos: Python 3.12+, git, o CLI `claude` no PATH e um projeto no Google Cloud com a API do Chat.

1. Configure as credenciais e os valores locais. Nada disso vai pro git:
   - `credenciais/google-oauth.json`: cliente OAuth do tipo "Desktop app".
   - `credenciais/webhook-chat.json` (opcional): webhook de um espaço do Chat para avisos no celular.
   - `local.json`: copie de `local.exemplo.json` e preencha.
2. Faça o login do Google (só na primeira vez; o token fica em `credenciais/token.json`):
   ```
   python -m servidor login
   ```
3. Suba o painel:
   ```
   python -m servidor
   ```
   Ou `pythonw iniciar.pyw`, que sobe sem janela.

Os repos que os agentes alteram ficam na pasta **acima** desta (`../<repo>`).

## Agentes

Cada tipo tem um `agente.json` versionado, com o resumo, exemplos, campos obrigatórios da ficha, modelos e regra de deploy.

O conhecimento específico de cada instalação fica fora do git:
- `agentes/<tipo>/CONTEXTO.md`
- `agentes/<tipo>/APRENDIZADOS.md`
- `agentes/_comum/*.md`

Esses arquivos costumam ter clientes, hosts e pessoas. Crie-os à mão em cada máquina. Sem eles, os agentes funcionam com menos contexto.

## Testes

```
python testes/replay.py                         # reprocessa conversas reais numa cópia do banco, sem enviar nada
python testes/plano.py testes/fichas/exemplo.json   # só o plano de uma ficha, sem executar
```
