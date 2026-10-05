// Quadro (kanban): as mesmas tarefas em colunas por status.
// Arrastar um card pra outra coluna dispara a ação real da tarefa; colunas sem ação ficam apagadas.

import { ui, set, daLista, esc, pessoa } from './estado.js';
import { nomeCategoria, avatar } from './lista.js';
import { acoes } from './fluxo.js';
import { recomendado, descricaoExecucao } from './modelos.js';

const SEMANA = 7 * 24 * 3600 * 1000;

const COLUNAS = [
  { id: 'novas', nome: 'Novas', status: ['identificada'] },
  { id: 'comigo', nome: 'Com você', status: ['comigo'] },
  { id: 'decidir', nome: 'Precisa de mim', status: ['pergunta', 'resposta', 'aprovacao'] },
  { id: 'andamento', nome: 'Em andamento', status: ['triagem', 'execucao'] },
  { id: 'deploy', nome: 'Aguardando deploy', status: ['revisao'] },
  { id: 'feito', nome: 'Concluídas', status: ['feito'] },
];

const SUBSTATUS = {
  pergunta: 'Pergunta', resposta: 'Resposta pronta', aprovacao: 'Plano pronto',
  triagem: 'Planejando', execucao: 'Executando',
};

// O que acontece ao soltar a tarefa t na coluna. null = não dá pra mover pra lá.
function movimento(t, coluna) {
  if (COLUNAS.find((c) => c.id === coluna).status.includes(t.status)) return null;
  const livre = ['identificada', 'comigo'].includes(t.status);
  switch (coluna) {
    case 'comigo':
      return t.status === 'identificada' ? { fazer: () => acoes.assumir(t.id) } : null;
    case 'andamento':
      if (livre) return { fazer: () => (t.tipo === 'duvida' ? acoes.pesquisar(t.id) : acoes.fazer(t.id)) };
      if (t.status === 'aprovacao' && t.categoria) {
        const escolha = recomendado(t);
        return {
          confirmar: `Executar ${t.id} com ${descricaoExecucao(escolha.modelo, escolha.esforco)}?`,
          fazer: () => acoes.aprovar(t.id, escolha),
        };
      }
      return null;
    case 'feito':
      return t.status === 'feito' ? null : {
        confirmar: `Marcar ${t.id} como concluída por você?`,
        fazer: () => acoes.finalizar(t.id),
      };
    case 'novas':
      return t.status === 'feito' ? { fazer: () => acoes.reabrir(t.id) } : null;
    default:
      return null;
  }
}

const recente = (t) => t.status !== 'feito' || Date.now() - new Date(t.concluidaEm || t.atualizadaEm || 0) < SEMANA;

function card(t) {
  const p = pessoa(t.pessoa);
  const sub = SUBSTATUS[t.status];
  return `
    <button class="q-card" draggable="true" data-id="${t.id}" data-arrastar="${t.id}">
      <span class="q-topo">
        ${avatar(t.pessoa, 'mini')}
        <span class="q-quem">${esc(p.nome.split(' ')[0])}</span>
        ${t.prioridade === 'P0' ? '<b class="urgente">Urgente</b>' : ''}
      </span>
      <b class="q-titulo">${esc(t.titulo)}</b>
      <span class="q-meta">
        ${sub ? `<span class="q-sub"><i class="ponto s-${t.status}"></i>${sub}</span>` : ''}
        <span>${t.tipo === 'duvida' ? 'Dúvida' : esc(nomeCategoria(t))}</span>
      </span>
    </button>`;
}

let arrastando = null; // tarefa sendo arrastada: o quadro não redesenha no meio do gesto

export const quadroOcupado = () => arrastando !== null;

export function renderQuadro(el) {
  // Cada coluna rola sozinha; redesenhar mantém onde você estava.
  const rolagem = Object.fromEntries([...el.querySelectorAll('.q-coluna')].map((c) => [c.dataset.coluna, c.querySelector('.q-itens').scrollTop]));
  const lista = daLista().filter(recente);
  el.innerHTML = `
    <div class="quadro">
      ${COLUNAS.map((c) => {
        const itens = lista.filter((t) => c.status.includes(t.status));
        return `
          <section class="q-coluna" data-coluna="${c.id}">
            <h3>${c.nome} <span>${itens.length}</span></h3>
            <div class="q-itens">${itens.map(card).join('') || '<p class="nada">Nada aqui.</p>'}</div>
          </section>`;
      }).join('')}
    </div>`;
  el.querySelectorAll('.q-coluna').forEach((c) => { c.querySelector('.q-itens').scrollTop = rolagem[c.dataset.coluna] || 0; });
}

const tarefaArrastada = () => daLista().find((t) => t.id === arrastando);

document.addEventListener('dragstart', (e) => {
  const c = e.target.closest?.('[data-arrastar]');
  if (!c) return;
  arrastando = c.dataset.arrastar;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', arrastando);
  c.classList.add('arrastando');
  const t = tarefaArrastada();
  document.querySelectorAll('.q-coluna').forEach((col) => {
    col.classList.toggle('q-bloqueada', !movimento(t, col.dataset.coluna)
      && !COLUNAS.find((x) => x.id === col.dataset.coluna).status.includes(t.status));
  });
});

document.addEventListener('dragover', (e) => {
  const col = e.target.closest?.('.q-coluna');
  if (!col || !arrastando) return;
  const t = tarefaArrastada();
  if (t && movimento(t, col.dataset.coluna)) {
    e.preventDefault();
    document.querySelectorAll('.q-alvo').forEach((x) => x !== col && x.classList.remove('q-alvo'));
    col.classList.add('q-alvo');
  }
});

function soltarTudo() {
  arrastando = null;
  document.querySelectorAll('.q-alvo, .q-bloqueada, .arrastando')
    .forEach((x) => x.classList.remove('q-alvo', 'q-bloqueada', 'arrastando'));
}

document.addEventListener('drop', (e) => {
  const col = e.target.closest?.('.q-coluna');
  const t = arrastando && tarefaArrastada();
  if (!col || !t) return soltarTudo();
  e.preventDefault();
  const m = movimento(t, col.dataset.coluna);
  soltarTudo();
  if (!m || (m.confirmar && !confirm(m.confirmar))) return set({});
  Promise.resolve(m.fazer()).catch(() => {}).finally(() => set({}));
});

document.addEventListener('dragend', () => { if (arrastando) { soltarTudo(); set({}); } });

export const ehQuadro = () => ui.visao === 'quadro';
