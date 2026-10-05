// Coluna da direita: em cima os avisos, embaixo a conversa da tarefa que está rodando.
// É aqui que você corrige o rumo enquanto ele trabalha, em vez de descobrir no fim.

import { tarefas, tarefa, ui, set, esc, faz, pessoa, precisaDeMim, fila, ativos } from './estado.js';
import { STATUS } from './constantes.js';
import { avatar } from './lista.js';
import { acoes } from './fluxo.js';
import { campoAnexos, anexosDe, limparAnexos, ligarRascunhos } from './rascunhos.js';

const QUEM = { voce: 'Você', agente: 'Claude', sistema: 'Inbox' };

// Decisão que chegou e você ainda não abriu fica marcada. Guardado no navegador
// pra não "piscar de novo" a cada recarga da página.
const CHAVE_VISTAS = 'inbox-vistas';
const vistas = new Set(JSON.parse(localStorage.getItem(CHAVE_VISTAS) || '[]'));

export function marcarVista(id) {
  if (!id || vistas.has(id)) return;
  vistas.add(id);
  try { localStorage.setItem(CHAVE_VISTAS, JSON.stringify([...vistas].slice(-200))); } catch { /* aba anônima */ }
}

let falas = [];        // conversa carregada da tarefa mostrada
let mostrando = null;  // id da tarefa dessa conversa
let carregando = false;

/** A conversa é sobre a tarefa ABERTA; sem nenhuma aberta, sobre a que está rodando.
 *  Sem as duas, não há conversa: o bloco some e a coluna fica só com as decisões. */
export function tarefaDaConversa() {
  return tarefa(ui.selecionada) || rodando()[0] || null;
}

/** Tarefas trabalhando agora (uma por repositório). */
const rodando = () => {
  const dos_ativos = ativos().map((a) => tarefa(a.tarefa)).filter(Boolean);
  return dos_ativos.length ? dos_ativos : tarefas().filter((t) => ['execucao', 'triagem'].includes(t.status));
};

export function novaFala(f) {
  if (f.tarefa !== mostrando) return;
  falas.push(f);
  desenharConversa();
}

async function carregar(tid) {
  if (carregando) return;
  carregando = true;
  try {
    const r = await fetch(`/api/tarefas/${tid}/falas`);
    const d = await r.json();
    if (mostrando === tid) { falas = d.falas || []; desenharConversa(); }
  } catch { /* offline: a próxima mudança tenta de novo */ } finally {
    carregando = false;
  }
}

const linhaFala = (f) => `
  <div class="fala ${esc(f.quem)}">
    <span class="fala-quem">${QUEM[f.quem] || f.quem}</span>
    <p>${esc(f.texto)}</p>
  </div>`;

function desenharConversa() {
  const corpo = document.querySelector('#conversa-corpo');
  if (!corpo) return;
  const t = tarefa(mostrando);
  const colado = corpo.scrollHeight - corpo.scrollTop - corpo.clientHeight < 60;
  corpo.innerHTML = falas.length
    ? falas.map(linhaFala).join('')
    : `<p class="nada">${t ? 'Nada dito ainda. Escreva e ele lê no próximo passo.' : ''}</p>`;
  if (colado) corpo.scrollTop = corpo.scrollHeight;
}

const O_QUE_FAZER = (t) => ({
  identificada: t.tipo === 'duvida' ? 'Pesquisar' : 'Liberar plano',
  comigo: 'Finalizar', pergunta: 'Responder', resposta: 'Enviar resposta',
  aprovacao: 'Liberar execução', revisao: 'Revisar e subir',
}[t.status] || 'Ver');

/** Em cima: tudo que espera uma decisão sua, inclusive o que já saiu como aviso. */
function desenharPendentes(el) {
  const pendentes = tarefas().filter(precisaDeMim);
  // Sem nada esperando (e sem aviso novo), o bloco recolhe e a conversa fica com a tela toda.
  el.querySelector('.avisos').classList.toggle('sem-pendentes', pendentes.length === 0);
  el.querySelector('#avisos-conta').textContent = pendentes.length || 'nada esperando';
  el.querySelector('#pendentes').innerHTML = pendentes.length
    ? pendentes.map((t) => `
      <button class="pendente-linha ${ui.selecionada === t.id ? 'aberta' : ''} ${vistas.has(t.id) ? '' : 'nova'}" data-id="${t.id}">
        ${avatar(t.pessoa, 'p')}
        <span class="pendente-texto">
          <b>${esc(t.titulo)}</b>
          <span>${esc(pessoa(t.pessoa).nome.split(' ')[0])} · ${esc(STATUS[t.status])}</span>
        </span>
        <span class="pendente-acao">${O_QUE_FAZER(t)}</span>
      </button>`).join('')
    : '<p class="nada">Nada esperando você.</p>';
}

/** Faixa do que está rodando: dá pra acompanhar enquanto você fala de outra tarefa. */
function desenharRodando(el, aberta) {
  const emCurso = rodando();
  const faixa = el.querySelector('#rodando-agora');
  faixa.hidden = emCurso.length === 0;
  faixa.innerHTML = emCurso.map((t) => {
    const e = t.execucao || {};
    const pct = Math.round((e.progresso ?? 0.05) * 100);
    return `
      <button class="rodando-item ${t.id === aberta?.id ? 'aberta' : ''}" data-id="${t.id}">
        <span class="rodando-topo"><b>${esc(t.id)}</b>${esc(t.titulo)}</span>
        <span class="progresso"><i style="width:${pct}%"></i></span>
        <span class="rodando-passo">${esc(e.passo || t.esperando || 'trabalhando')}</span>
      </button>`;
  }).join('');
}

export function renderColuna(el) {
  marcarVista(ui.selecionada);  // abriu, deixou de ser novidade
  desenharPendentes(el);
  const t = tarefaDaConversa();
  desenharRodando(el, t);
  el.querySelector('.conversa').hidden = !t;
  if (!t) { mostrando = null; falas = []; return; }
  const emAndamento = t && ['execucao', 'triagem'].includes(t.status);
  if (t?.id !== mostrando) {
    mostrando = t?.id || null;
    falas = [];
    if (mostrando) carregar(mostrando);
  }

  const cabecalho = `<button class="conversa-tarefa" data-id="${t.id}">
         <span class="conversa-id">${t.id}</span>
         <b>${esc(t.titulo)}</b>
         <span class="conversa-sub">${emAndamento
           ? esc(t.execucao?.passo || t.esperando || 'trabalhando')
           : `${esc(pessoa(t.pessoa).nome.split(' ')[0])} · há ${faz(t.criadaEm)}`}</span>
       </button>`;

  const outras = rodando().filter((x) => x.id !== t?.id);
  const esperando = fila().filter((x) => x.tarefa !== t?.id);
  el.querySelector('#conversa-estado').textContent = emAndamento
    ? 'trabalhando agora' + (esperando.length ? ` · ${esperando.length} na fila` : '')
    : t ? 'parada' : '';
  el.querySelector('#conversa-cabecalho').innerHTML = cabecalho
    + (outras.length ? `<p class="conversa-fila">Também rodando:
        ${outras.map((x) => `<button class="link" data-id="${x.id}">${x.id}</button>`).join(' ')}
        — o que você escrever aqui é sobre ${esc(t.id)}.</p>` : '')
    + (esperando.length ? `<p class="conversa-fila">Na fila: ${esperando.map((x) => esc(x.tarefa)).join(', ')}</p>` : '');
  // Deixa explícito pra onde a mensagem vai e o que ela dispara.
  const destino = { pergunta: 'responde e ele segue', aprovacao: 'manda executar',
    identificada: 'manda planejar', comigo: 'manda planejar', revisao: 'pede ajuste' }[t.status]
    || (emAndamento ? 'entra na sessão que está rodando' : 'fica anotado');
  el.querySelector('#conversa-destino').innerHTML =
    `<b>${esc(t.id)}</b> · ${esc(t.titulo)} <span>— ${destino}</span>`;
  const caixaAnexos = el.querySelector('#conversa-anexos');
  if (caixaAnexos.dataset.tarefa !== t.id) {  // só redesenha ao trocar de tarefa (não perde o que já subiu)
    caixaAnexos.dataset.tarefa = t.id;
    caixaAnexos.innerHTML = campoAnexos(t.id, `conversa-${t.id}`);
  }
  el.querySelector('#conversa-campo').dataset.chaveAnexo = `conversa-${t.id}`;
  el.querySelector('#conversa-campo').placeholder = emAndamento
    ? `Corrija o rumo de ${t.id}: ele lê no próximo passo`
    : `Escreva pra ${t.id} — ${destino}`;
  desenharConversa();
}

export function ligarConversa(el) {
  const campo = el.querySelector('#conversa-campo');
  ligarRascunhos(el.querySelector('.conversa'));  // anexar e colar imagem na conversa
  const enviar = () => {
    const texto = campo.value.trim();
    const chave = `conversa-${mostrando}`;
    const arquivos = anexosDe(chave);
    if ((!texto && !arquivos.length) || !mostrando) return;
    campo.value = '';
    acoes.falar(mostrando, texto, arquivos)
      .then(() => {
        limparAnexos(chave);
        const caixa = el.querySelector('#conversa-anexos');
        caixa.dataset.tarefa = '';  // redesenha vazio
        renderColuna(el);
      })
      .catch(() => { campo.value = texto; });
  };
  campo.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
  });
  el.querySelector('#conversa-enviar').addEventListener('click', enviar);
  el.querySelector('#conversa-cabecalho').addEventListener('click', (e) => {
    const b = e.target.closest('[data-id]');
    if (b) set({ selecionada: b.dataset.id });
  });
}
