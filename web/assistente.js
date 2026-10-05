// O que o pet oferece quando você clica nele, e os cartões que ele mostra:
// resumo do dia, prioridades e agenda de hoje (a agenda só aparece quando você pede).

import { tarefas, precisaDeMim, esc, tarefa } from './estado.js';
import { falar, pular } from './pet.js';
import { icone } from './icones.js';

const OPCOES = [
  ['agenda', 'Minha agenda hoje'],
  ['resumir', 'Resumir o dia'],
  ['priorizar', 'Priorizar pendências'],
  ['tempo', 'Como está o tempo?'],
];

const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : 'Dia todo');

function situacao() {
  const n = tarefas().filter(precisaDeMim).length;
  const rodando = tarefas().filter((t) => t.status === 'execucao').length;
  if (!n && !rodando) return 'Tudo em dia.';
  return [n && `${n} esperando você`, rodando && `${rodando} em execução`].filter(Boolean).join(' · ') + '.';
}

// ---------- cartão (mesmo visual dos avisos, fica até você fechar) ----------

export function cartao({ rotulo, titulo, corpo = '', botoes = [], chave }) {
  const pilha = document.querySelector('#pet-baloes');  // agenda, resumo, tempo: acima do pet
  if (chave) pilha.querySelector(`.toast[data-chave="${chave}"]`)?.remove();
  const el = document.createElement('div');
  el.className = 'toast cartao';
  if (chave) el.dataset.chave = chave;
  el.innerHTML = `
    <div class="toast-topo">
      <span class="toast-rotulo">${esc(rotulo)}</span>
      <button class="toast-x" data-fechar aria-label="fechar">${icone('fechar', 16)}</button>
    </div>
    ${titulo ? `<b class="cartao-titulo">${esc(titulo)}</b>` : ''}
    <div class="cartao-corpo">${corpo}</div>
    ${botoes.length ? `<div class="toast-acoes">${botoes.map((b) =>
      `<a class="${b.classe || ''}" href="${esc(b.href)}" target="_blank" rel="noreferrer">${esc(b.rotulo)}</a>`).join('')}</div>` : ''}`;
  el.addEventListener('click', (e) => {
    if (e.target.closest('[data-fechar]') || e.target.closest('[data-id]')) {
      el.classList.add('saindo');
      setTimeout(() => el.remove(), 250);
    }
  });
  pilha.prepend(el);
  pular();
  return el;
}

const linkTarefa = (id, texto) => {
  const t = tarefa(id);
  return `<button class="cartao-tarefa" data-id="${esc(id)}"><span>${esc(id)}</span>${esc(texto || t?.titulo || '')}</button>`;
};

const sugestoesHtml = (sugestoes = []) => sugestoes.map((s) => `
  <p class="cartao-dica">${esc(s.texto)}</p>
  ${s.tarefas.map((t) => linkTarefa(t.id, t.titulo)).join('')}`).join('');

// ---------- respostas ----------

export function mostrarResposta({ titulo, texto, itens = [] }) {
  cartao({
    rotulo: titulo,
    chave: `pet-${titulo}`,
    corpo: `<p>${esc(texto)}</p>
      ${itens.length ? `<ol class="cartao-lista">${itens.map((i) =>
        `<li>${i.tarefa && tarefa(i.tarefa) ? linkTarefa(i.tarefa, i.texto) : esc(i.texto)}</li>`).join('')}</ol>` : ''}`,
  });
}

function listaAgenda(eventos) {
  if (!eventos.length) return '<p>Nenhum compromisso hoje.</p>';
  return `<ul class="cartao-agenda">${eventos.map((e) => `
    <li>
      <time>${hora(e.inicio)}</time>
      <div>
        <b>${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noreferrer">${esc(e.titulo)}</a>` : esc(e.titulo)}</b>
        ${e.pessoas.length ? `<span>${esc(e.pessoas.slice(0, 4).map((p) => p.nome).join(', '))}${e.pessoas.length > 4 ? ` +${e.pessoas.length - 4}` : ''}</span>` : ''}
        ${sugestoesHtml(e.sugestoes)}
      </div>
    </li>`).join('')}</ul>`;
}

async function agendaHoje() {
  const r = await fetch('/api/agenda');
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return cartao({ rotulo: 'Agenda', chave: 'agenda-hoje', corpo: `<p>${esc(d.erro || 'Não consegui ler a agenda.')}</p>` });
  // Próxima reunião em destaque, com o link pra entrar e quem tem pedido aberto com você.
  const agora = Date.now();
  const proxima = d.eventos.find((e) => e.inicio && new Date(e.fim || e.inicio) > agora);
  let destaque = '';
  const botoes = [];
  if (proxima) {
    const faltam = Math.round((new Date(proxima.inicio) - agora) / 60000);
    const quando = faltam <= 0 ? 'acontecendo agora' : faltam < 60 ? `em ${faltam} min` : `às ${hora(proxima.inicio)}`;
    destaque = `<p class="cartao-dica">Próxima: ${esc(proxima.titulo)}, ${quando}.</p>`;
    if (proxima.link) botoes.push({ rotulo: 'Entrar na próxima', href: proxima.link, classe: 't-sim' });
  }
  cartao({ rotulo: 'Agenda de hoje', chave: 'agenda-hoje', corpo: destaque + listaAgenda(d.eventos), botoes });
}

async function comoEstaOTempo() {
  const r = await fetch('/api/tempo');
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return cartao({ rotulo: 'Tempo', chave: 'tempo', corpo: `<p>${esc(d.erro || 'Não consegui ver o tempo.')}</p>` });
  cartao({
    rotulo: 'Tempo em Curitiba',
    titulo: `${d.temperatura}°, ${d.ceu}`,
    chave: 'tempo',
    corpo: `<p>Sensação de ${d.sensacao}°, umidade ${d.umidade}%, vento ${d.vento} km/h.</p>
      <p>Hoje entre ${d.minima}° e ${d.maxima}°${d.chuva ? `, ${d.chuva}% de chance de chuva` : ', sem chuva prevista'}.</p>`,
  });
}

// ---------- menu do pet ----------

export function menuDoPet(ancora) {
  const aberto = document.querySelector('.pet-menu');
  if (aberto) return aberto.remove();
  const el = document.createElement('div');
  el.className = 'pet-menu';
  el.innerHTML = `
    <p>${esc(situacao())}</p>
    ${OPCOES.map(([id, rotulo]) => `<button data-pet="${id}">${rotulo}</button>`).join('')}`;
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-pet]');
    if (!b) return;
    el.remove();
    escolher(b.dataset.pet);
  });
  ancora.before(el);
  setTimeout(() => document.addEventListener('click', function fora(e) {
    if (!el.contains(e.target) && !e.target.closest('.pet')) { el.remove(); document.removeEventListener('click', fora); }
  }), 0);
}

function escolher(acao) {
  if (acao === 'agenda') return agendaHoje().catch(() => falar('Não consegui ler a agenda.'));
  if (acao === 'tempo') return comoEstaOTempo().catch(() => falar('Não consegui ver o tempo.'));
  falar(acao === 'resumir' ? 'Deixa eu ver o que rolou…' : 'Deixa eu organizar as pendências…');
  fetch(`/api/pet/${acao}`, { method: 'POST' }).catch(() => falar('Não consegui falar com o servidor.'));
}
