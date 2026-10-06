# Apresentação: como meus agentes trabalham

Slides para explicar o agent-inbox a quem não é dev: o que é um agente, como o orquestrador e os especialistas se dividem, como o programa conversa com o Claude, qual modelo vai em cada etapa e o que fica fora da mão da IA.

| Arquivo | O que é |
|---|---|
| [`index.html`](index.html) | Os slides (15). Abra no Chrome ou no Edge. |
| [`PROMPT.md`](PROMPT.md) | O prompt para montar um app igual, pronto para copiar. |
| [`prompt.html`](prompt.html) | A página com o prompt e o botão de copiar, a mesma de [atlas.driva.io/agentes](https://atlas.driva.io/agentes/). |
| [`qr-agentes.svg`](qr-agentes.svg) | O QR code do último slide, que leva para essa página. |

## Apresentar

1. Baixe a pasta e abra `index.html` no navegador.
2. Aperte F11 para tela cheia.
3. Para navegar:
   - **Avançar:** clique ou use → (espaço e Enter também funcionam).
   - **Voltar:** clique no quinto esquerdo da tela ou use ←.
   - **Primeiro e último slide:** Home e End.
   - **No celular:** deslize para os lados.

Para abrir direto num slide, coloque o número no fim do endereço: `index.html#7`.

O arquivo é um só, sem dependências. Só as fontes vêm do Google Fonts; sem internet, o navegador usa uma fonte parecida. O QR code está desenhado dentro do próprio arquivo, então funciona offline.

## Roteiro

| # | Slide | Ideia |
|---|---|---|
| 1 | Capa | Os especialistas em órbita do orquestrador |
| 2 | O problema | Todo pedido passava por mim |
| 3 | O que é um agente | Pensa, age, confere, repete |
| 4 | Do que é feito | O crachá: modelo, instruções, ferramentas, contexto |
| 5 | Como organizei | Um atendente e seis especialistas |
| 6 | O especialista | O mesmo Claude, com uma pasta diferente |
| 7 | Os três arquivos | Ficha, contexto e aprendizados |
| 8 | Conexão com o Claude | O programa "digita" a tarefa |
| 9 | Modelos | Opus planeja, Sonnet executa |
| 10 | Vida de um pedido | Do Chat até o ar |
| 11 | Segurança | Portões fixos e papéis separados |
| 12 | Resultado | 103 pedidos em 12 dias |
| 13 | Lições | Especialista, memória, teste real, erro visível |
| 14 | Para você | Um Projeto no Claude já é um especialista |
| 15 | QR | Monte o seu app de agentes |

## Editar

Tudo fica em `index.html`: cada slide é uma `<section class="slide">`, na ordem em que aparece. As cores e as fontes ficam no começo do `<style>`, em `:root`.

Se o endereço da página do prompt mudar, gere um QR code novo e troque o `<svg>` do último slide e o `qr-agentes.svg`.
