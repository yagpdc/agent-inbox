// Tela inicial: o que precisa de você primeiro, depois números e atividade.

import { CATEGORIAS } from './constantes.js';
import { tarefas, eventos, metricas, precisaDeMim, contar, esc, faz, fimEventos, maisEventos } from './estado.js';
import { buscarEventos } from './api.js';

// Rolagem infinita da atividade: perto do fim da caixa, busca a próxima página.
let buscando = false;
document.addEventListener('scroll', (e) => {
  const caixa = e.target.closest?.('.eventos-rolagem');
  if (!caixa || buscando || fimEventos()) return;
  if (caixa.scrollTop + caixa.clientHeight < caixa.scrollHeight - 80) return;
  const ultimo = eventos().at(-1);
  if (!ultimo?.id) return;
  buscando = true;
  buscarEventos(ultimo.id).then(maisEventos).catch(() => {}).finally(() => { buscando = false; });
}, true);
import { nomeCategoria, avatar } from './lista.js';
import { icone } from './icones.js';

const O_QUE_FAZER = (t) =>
  ({
    identificada: t.tipo === 'duvida' ? 'Pesquisar e responder' : 'Liberar plano',
    comigo: 'Finalizar', pergunta: 'Responder', resposta: 'Enviar resposta', aprovacao: 'Liberar execução',
  })[t.status] || 'Liberar deploy';

function saudacao() {
  const h = new Date().getHours();
  return h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite';
}

export function renderInicio(el) {
  const rolagem = el.querySelector('.eventos-rolagem')?.scrollTop || 0; // redesenhar não pode voltar pro topo
  const todas = tarefas();
  const m = metricas();
  const pendentes = todas.filter(precisaDeMim);
  const abertas = todas.filter((t) => t.status !== 'feito');
  const maxCat = Math.max(1, ...CATEGORIAS.map((c) => abertas.filter((t) => t.categoria === c.id).length));
  const porId = Object.fromEntries(todas.map((t) => [t.id, t]));

  const n = pendentes.length;
  const manchete = n
    ? `Você tem <em>${n} ${n === 1 ? 'decisão pendente' : 'decisões pendentes'}</em>.`
    : 'Nada esperando você agora.';

  el.innerHTML = `
    <div class="inicio">
      <div class="inicio-principal">
      <p class="sobre">${saudacao()}, Yago</p>
      <h1 class="manchete">${manchete}</h1>

      ${n ? `
      <div class="pendentes">
        ${pendentes.map((t) => `
          <button class="pendente" data-id="${t.id}">
            ${avatar(t.pessoa)}
            <span class="pendente-corpo">
              <b>${esc(t.titulo)}</b>
              <span>${esc(nomeCategoria(t))} · há ${faz(t.criadaEm)}${t.prioridade === 'P0' ? ' · <b class="urgente">Urgente</b>' : ''}</span>
            </span>
            <span class="pendente-acao">${O_QUE_FAZER(t)}</span>
          </button>`).join('')}
      </div>` : ''}

        <section class="bloco-inicio">
          <h3>Atividade recente</h3>
          <div class="eventos-rolagem">
          ${eventos().map((e) => {
            const t = porId[e.tarefa];
            const pessoa = t?.pessoa || e.pessoa;
            if (!pessoa) return '';
            return `
              <button class="evento" ${t ? `data-id="${t.id}"` : ''}>
                ${avatar(pessoa, 'p')}
                <span><b>${esc(e.texto)}</b> · ${esc(t ? t.titulo : e.detalhe)}</span>
                <time>${faz(e.quando)}</time>
              </button>`;
          }).join('')}
          ${fimEventos() ? '' : '<p class="eventos-mais">Carregando mais…</p>'}
          </div>
        </section>
      </div>

      <aside class="inicio-lateral">
        <div class="numeros">
          <div><b>${contar('execucao')}</b><span>em execução</span></div>
          <div><b>${todas.filter((t) => t.status === 'triagem').length}</b><span>sendo planejadas</span></div>
          <div><b>${m.concluidas7d ?? 0}</b><span>concluídas em 7 dias</span></div>
          <div><b>${m.ignoradas ?? 0}</b><span>mensagens ignoradas</span></div>
          <div><b>${m.respostasDm ?? 0}</b><span>DMs respondidas</span></div>
          <div><b>${contar('sem-categoria')}</b><span>sem categoria</span></div>
        </div>

        <section class="bloco-inicio">
          <h3>Abertas por categoria</h3>
          ${CATEGORIAS.map((c) => {
            const q = abertas.filter((t) => t.categoria === c.id).length;
            return `
              <button class="barra-cat" data-visao="cat:${c.id}">
                ${icone(c.id, 16)}<span>${c.nome}</span>
                <span class="trilho"><i style="width:${(q / maxCat) * 100}%"></i></span>
                <b>${q}</b>
              </button>`;
          }).join('')}
        </section>
      </aside>
    </div>`;
  const caixa = el.querySelector('.eventos-rolagem');
  if (caixa) caixa.scrollTop = rolagem;
}
