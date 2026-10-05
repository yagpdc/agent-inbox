// Perguntas do agente com opções clicáveis + resposta livre.
// Usado no aviso flutuante e na tela da tarefa; as escolhas ficam guardadas por tarefa.

import { esc } from './estado.js';

const escolhas = {}; // { [tarefaId]: [resposta por pergunta] }

export const respostas = (t) => {
  const itens = t.pergunta?.itens || [];
  const r = escolhas[t.id] || [];
  return itens.map((_, i) => (r[i] || '').trim());
};

export const completas = (t) => respostas(t).every(Boolean);

export function escolher(tid, i, valor) {
  (escolhas[tid] ||= [])[i] = valor;
}

export const limpar = (tid) => { delete escolhas[tid]; };

export function renderPerguntas(t) {
  const r = escolhas[t.id] || [];
  return (t.pergunta?.itens || []).map((p, i) => {
    const livre = r[i] && !p.opcoes.includes(r[i]) ? r[i] : '';
    return `
      <div class="pergunta">
        <p>${esc(p.pergunta)}</p>
        <div class="pergunta-opcoes">
          ${p.opcoes.map((o, j) => `
            <button class="pergunta-opcao" data-resp-t="${t.id}" data-resp-i="${i}" data-resp-v="${esc(o)}" aria-pressed="${r[i] === o}">
              ${esc(o)}${j === 0 ? '<small>recomendada</small>' : ''}
            </button>`).join('')}
        </div>
        ${p.opcoes.length
          ? `<input class="pergunta-livre" data-resp-t="${t.id}" data-resp-i="${i}" placeholder="Outra resposta" value="${esc(livre)}" />`
          : `<textarea class="pergunta-livre" data-resp-t="${t.id}" data-resp-i="${i}" rows="6" placeholder="Sua resposta (pode colar links e textos)">${esc(livre)}</textarea>`}
      </div>`;
  }).join('');
}

export const FALTA_RESPONDER = 'Responda todas as perguntas antes de enviar.';

// Liga cliques e digitação dentro de `raiz`. `aoMudar` redesenha quem precisar.
export function ligarPerguntas(raiz, aoMudar) {
  raiz.addEventListener('click', (e) => {
    const b = e.target.closest('.pergunta-opcao');
    if (!b) return;
    e.stopPropagation();
    escolher(b.dataset.respT, Number(b.dataset.respI), b.dataset.respV);
    aoMudar();
  });
  // Texto livre: guarda enquanto digita, sem redesenhar (senão o clique em Responder se perde).
  raiz.addEventListener('input', (e) => {
    const inp = e.target.closest('.pergunta-livre');
    if (!inp) return;
    escolher(inp.dataset.respT, Number(inp.dataset.respI), inp.value);
    raiz.querySelectorAll(`.pergunta-opcao[data-resp-t="${inp.dataset.respT}"][data-resp-i="${inp.dataset.respI}"]`)
      .forEach((b) => b.setAttribute('aria-pressed', 'false'));
  });
}
