import { CATEGORIAS, STATUS } from './constantes.js';
import { ui, daLista, esc, faz, PESSOAS, pessoa, agentesNomes } from './estado.js';

export const nomeCategoria = (t) => {
  const c = CATEGORIAS.find((x) => x.id === t.categoria);
  if (!c) return t.status === 'comigo' ? 'Com você' : 'Sem categoria';
  const s = c.subs?.find((x) => x.id === t.sub);
  const apelido = agentesNomes()[t.categoria]?.apelido;
  const nome = s ? `${c.nome} · ${s.nome}` : c.nome;
  return apelido ? `${apelido} · ${nome}` : nome;
};

export const nomeVisao = (v) => {
  const fixas = { minhas: 'Precisa de mim', tudo: 'Todas', quadro: 'Quadro', execucao: 'Em execução', feitas: 'Concluídas', 'sem-categoria': 'Sem categoria' };
  if (fixas[v]) return fixas[v];
  const [, cat, sub] = v.split(':');
  const c = CATEGORIAS.find((x) => x.id === cat);
  const s = c?.subs?.find((x) => x.id === sub);
  return s ? `${c.nome} · ${s.nome}` : c?.nome || '';
};

export const avatar = (id, classe = '') => {
  const p = pessoa(id);
  const foto = p.foto ? `<img src="${esc(p.foto)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()" />` : '';
  return `<span class="av ${classe}" style="background:${p.cor}" title="${esc(p.nome)}">${esc(p.iniciais)}${foto}</span>`;
};

function linha(t) {
  const p = pessoa(t.pessoa);
  const resumo = t.plano?.resumo || t.esperando || t.pedido;
  return `
    <button class="linha" data-id="${t.id}" aria-current="${ui.selecionada === t.id}">
      ${avatar(t.pessoa)}
      <span class="linha-corpo">
        <span class="linha-topo">
          <span class="linha-nome">${esc(p.nome)}</span>
          <time>${faz(t.criadaEm)}</time>
        </span>
        <span class="linha-titulo">${esc(t.titulo)}</span>
        <span class="linha-previa">${esc(resumo)}</span>
        <span class="linha-status">
          <i class="ponto s-${t.status}"></i>${t.status !== 'feito' ? STATUS[t.status] : t.resultado?.porVoce ? 'Resolvida por você' : t.descartada ? 'Descartada' : STATUS[t.status]}
          ${t.prioridade === 'P0' ? '<b class="urgente">Urgente</b>' : ''}
          <span class="cat">${t.tipo === 'duvida' ? 'Dúvida' : ''}${t.tipo === 'duvida' && !ui.visao.startsWith('cat:') ? ' · ' : ''}${ui.visao.startsWith('cat:') ? '' : esc(nomeCategoria(t))}</span>
        </span>
      </span>
    </button>`;
}

export function renderLista(el) {
  const lista = daLista();
  const opcoes = Object.entries(PESSOAS)
    .map(([k, p]) => `<option value="${k}" ${ui.pessoa === k ? 'selected' : ''}>${esc(p.nome)}</option>`)
    .join('');

  const cabecalho = el.querySelector('.lista-cabecalho');
  cabecalho.querySelector('h2').innerHTML = `${esc(nomeVisao(ui.visao))} <span>${lista.length}</span>`;
  const select = cabecalho.querySelector('select');
  select.innerHTML = `<option value="">Todas as pessoas</option>${opcoes}`;

  el.querySelector('.linhas').innerHTML =
    lista.map(linha).join('') || '<p class="nada">Nada por aqui.</p>';
}
