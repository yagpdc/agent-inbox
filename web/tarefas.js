// Tela Tarefas (estilo ClickUp): Lista, Quadro, Calendário e Linha do tempo sobre as mesmas tarefas.
// Toda tarefa aparece aqui, seja de um agente ou sua. Prioridade, prazo e responsável se mudam na hora.

import { set, tarefas, atendimentos, agentesNomes, esc, pessoa, config } from './estado.js';
import { decidir } from './api.js';
import { avatar } from './lista.js';
import { icone } from './icones.js';
import { falar } from './pet.js';

const VISOES = [['lista', 'Lista', 'tarefas'], ['quadro', 'Quadro', 'quadro'], ['calendario', 'Calendário', 'calendario'], ['tempo', 'Linha do tempo', 'linhaTempo']];
const AGRUPAR = [['status', 'Status'], ['agente', 'Responsável'], ['pessoa', 'Quem pediu'], ['prioridade', 'Prioridade'], ['prazo', 'Prazo']];
const PRIORIDADE = { P0: ['Urgente', 'p-urgente'], P1: ['Alta', 'p-alta'], P2: ['Normal', 'p-normal'], P3: ['Baixa', 'p-baixa'] };
const COR_AGENTE = { hub: '#4f46e5', mapa: '#0f8b8d', camadas: '#1b8ec9', reativacao: '#c2408a', site: '#d98a06', duvida: '#7b6ff8' };
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const MESES_LONGOS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'];

const guardado = (chave, padrao) => { try { return JSON.parse(localStorage.getItem(chave)) ?? padrao; } catch { return padrao; } };
const guardar = (chave, valor) => { try { localStorage.setItem(chave, JSON.stringify(valor)); } catch { /* sem storage */ } };

const estado = {
  visao: guardado('tarefas.visao', 'lista'),
  agrupar: guardado('tarefas.agrupar', 'status'),
  busca: '',
  adicionando: null,   // grupo com a linha "nova tarefa" aberta
  mes: null,           // calendário: primeiro dia do mês mostrado
};
const fechados = new Set(guardado('tarefas.fechados', ['st:feito']));
const expandidos = new Set(guardado('tarefas.expandidos', []));
let subNova = null;     // tarefa-mãe com a linha "nova subtarefa" aberta
let renomeando = null;  // tarefa com o título em edição

/* ---------- datas ---------- */

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const hoje = () => iso(new Date());
const somar = (base, dias) => { const d = new Date(`${base}T12:00:00`); d.setDate(d.getDate() + dias); return iso(d); };

function dataCurta(dia) {
  if (dia === hoje()) return 'Hoje';
  if (dia === somar(hoje(), 1)) return 'Amanhã';
  if (dia === somar(hoje(), -1)) return 'Ontem';
  const [, m, d] = dia.split('-');
  return `${Number(d)} ${MESES[Number(m) - 1]}`;
}

/* ---------- situação de cada tarefa ---------- */

export function situacao(t) {
  const e = t.esperando || '';
  if (t.status === 'feito') {
    if (t.descartada) return ['Descartada', 'st-cinza'];
    return [t.marcos?.no_ar || t.resultado?.pr?.mergeado ? 'No ar' : 'Concluída', 'st-verde'];
  }
  if (e.includes('falhou')) return ['Travou', 'st-vermelho'];
  if (e.startsWith('Pausado')) return ['Pausado', 'st-cinza'];
  switch (t.status) {
    case 'revisao': return [t.resultado?.pr ? 'PR aberto' : 'Pronto pra deploy', 'st-teal'];
    case 'pergunta': return [t.pergunta?.etapa === 'conversa' ? 'Conversa com você' : 'Esperando você', 'st-laranja'];
    case 'resposta': return ['Resposta pronta', 'st-laranja'];
    case 'comigo': return ['Com você', 'st-amarelo'];
    case 'execucao': return ['Fazendo', 'st-azul'];
    case 'triagem': return ['Planejando', 'st-roxo'];
    case 'aprovacao': return ['Plano pronto', 'st-roxo'];
    default:
      if (e.startsWith('Perguntei a quem pediu')) return ['Esperando quem pediu', 'st-cinza'];
      if (e.startsWith('Na fila')) return ['Na fila', 'st-cinza'];
      return ['A fazer', 'st-cinza'];
  }
}

const autonomo = () => config().orquestrador?.autonomo !== false;

function grupoStatus(t) {
  const [rotulo] = situacao(t);
  if (t.status === 'feito') return 'feito';
  if (['Travou', 'Esperando você', 'Conversa com você', 'Resposta pronta', 'PR aberto', 'Pronto pra deploy'].includes(rotulo)) return 'voce';
  if (t.status === 'aprovacao' && !(t.ficha && autonomo())) return 'voce';
  if (t.status === 'comigo') return 'comigo';
  if (['triagem', 'execucao', 'aprovacao'].includes(t.status)) return 'fazendo';
  return 'fila';
}

const nomeAgente = (tipo) => { const a = agentesNomes()[tipo]; return a ? `${a.apelido} · ${a.nome}` : 'Sem agente'; };

function grupoPrazo(t) {
  if (!t.prazo) return 'sem';
  if (t.prazo < hoje() && t.status !== 'feito') return 'atrasada';
  if (t.prazo === hoje()) return 'hoje';
  const domingo = somar(hoje(), 6 - ((new Date().getDay() + 6) % 7));
  return t.prazo <= domingo ? 'semana' : 'depois';
}

// [id do grupo, rótulo, classe da etiqueta, o que uma tarefa nova herda]
function grupos() {
  switch (estado.agrupar) {
    case 'agente':
      return [['ag:yago', 'Você', 'g-amarelo', { responsavel: 'yago' }],
        ...Object.keys(agentesNomes()).map((tipo) => [`ag:${tipo}`, nomeAgente(tipo), `g-ag-${tipo}`, { responsavel: tipo }]),
        ['ag:sem', 'Sem agente', 'g-cinza', { responsavel: 'yago' }]];
    case 'pessoa':
      return [...new Set(tarefas().map((t) => t.pessoa))].map((id) => [`pe:${id}`, pessoa(id).nome, 'g-cinza', {}]);
    case 'prioridade':
      return Object.entries(PRIORIDADE).map(([p, [r]]) => [`pr:${p}`, r, `g-${p}`, { prioridade: p }]);
    case 'prazo':
      return [['pz:atrasada', 'Atrasadas', 'g-vermelho', {}], ['pz:hoje', 'Hoje', 'g-laranja', { prazo: hoje() }],
        ['pz:semana', 'Esta semana', 'g-azul', {}], ['pz:depois', 'Depois', 'g-cinza', {}], ['pz:sem', 'Sem prazo', 'g-cinza', {}]];
    default:
      return [['st:voce', 'Precisa de você', 'g-laranja', {}], ['st:comigo', 'Com você', 'g-amarelo', { responsavel: 'yago' }],
        ['st:fazendo', 'Em andamento', 'g-azul', {}], ['st:fila', 'A fazer', 'g-cinza', {}], ['st:feito', 'Concluídas', 'g-verde', {}]];
  }
}

function grupoDe(t) {
  switch (estado.agrupar) {
    case 'agente': return t.status === 'comigo' ? 'ag:yago' : t.categoria && agentesNomes()[t.categoria] ? `ag:${t.categoria}` : 'ag:sem';
    case 'pessoa': return `pe:${t.pessoa}`;
    case 'prioridade': return `pr:${PRIORIDADE[t.prioridade] ? t.prioridade : 'P2'}`;
    case 'prazo': return `pz:${grupoPrazo(t)}`;
    default: return `st:${grupoStatus(t)}`;
  }
}

function lista() {
  const termo = estado.busca.trim().toLowerCase();
  const limite = new Date(Date.now() - 30 * 86400000).toISOString();
  return tarefas()
    .filter((t) => !termo || `${t.id} ${t.titulo} ${t.pedido} ${pessoa(t.pessoa).nome}`.toLowerCase().includes(termo))
    .filter((t) => t.status !== 'feito' || (t.concluidaEm || t.criadaEm || '') >= limite)
    .sort((a, b) => (a.prioridade || 'P2').localeCompare(b.prioridade || 'P2')
      || (a.prazo || '9999').localeCompare(b.prazo || '9999') || (b.criadaEm || '').localeCompare(a.criadaEm || ''));
}

let filhos = {};

function agrupado() {
  const todas = lista();
  const ids = new Set(todas.map((t) => t.id));
  filhos = {};
  todas.filter((t) => t.pai && ids.has(t.pai)).forEach((t) => { (filhos[t.pai] ||= []).push(t); });
  const por = {};
  todas.filter((t) => !(t.pai && ids.has(t.pai))).forEach((t) => { (por[grupoDe(t)] ||= []).push(t); });
  return grupos()
    .map(([id, rotulo, classe, herda]) => ({ id, rotulo, classe, herda, itens: por[id] || [] }))
    .filter((g) => g.itens.length || !['pe:', 'pz:atrasada', 'ag:sem'].some((p) => g.id.startsWith(p)));
}

/* ---------- pedaços reaproveitados ---------- */

function responsavel(t) {
  if (t.status === 'comigo') return `<span class="t-resp"><span class="t-ag g-amarelo">Y</span>Você</span>`;
  const a = agentesNomes()[t.categoria];
  if (!a) return '<span class="apagado">—</span>';
  return `<span class="t-resp"><span class="t-ag" style="background:${COR_AGENTE[t.categoria] || '#979dab'}">${esc(a.apelido[0])}</span>${esc(a.apelido)}</span>`;
}

function prazo(t) {
  const atrasada = t.prazo && t.prazo < hoje() && t.status !== 'feito';
  return `
    <button class="t-cel t-prazo ${atrasada ? 'atrasada' : ''}" data-abrir-prazo="${t.id}" title="Prazo">
      ${t.prazo ? esc(dataCurta(t.prazo)) : `<span class="apagado">${icone('calendario', 15)}</span>`}
      <input type="date" class="t-data" data-prazo="${t.id}" value="${esc(t.prazo || '')}" tabindex="-1" />
    </button>`;
}

const bandeira = (t, comTexto = true) => {
  const [prio, classe] = PRIORIDADE[t.prioridade] || PRIORIDADE.P2;
  return `<button class="t-cel t-prio ${classe}" data-menu="prioridade" data-tarefa="${t.id}" title="Prioridade">${icone('bandeira', 15)}${comTexto ? `<span>${prio}</span>` : ''}</button>`;
};

/* ---------- desenho ---------- */

const editando = (el) => el.contains(document.activeElement) && /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);

export function renderTarefas(el, { forcar = false } = {}) {
  if (!forcar && el.querySelector('.tarefas') && editando(el)) return;
  const rolagem = el.querySelector('.tarefas-corpo')?.scrollTop || 0;
  const corpo = { lista: visaoLista, quadro: visaoQuadro, calendario: visaoCalendario, tempo: visaoTempo }[estado.visao] || visaoLista;
  const rotuloAgrupar = AGRUPAR.find(([v]) => v === estado.agrupar)?.[1];
  el.innerHTML = `
    <div class="tarefas">
      <header class="tarefas-topo">
        <h1>Tarefas</h1>
        <nav class="t-visoes">${VISOES.map(([v, r, ic]) => `
          <button data-visao-tarefas="${v}" aria-current="${estado.visao === v}">${icone(ic, 16)}<span>${r}</span></button>`).join('')}
        </nav>
      </header>
      <div class="tarefas-ferramentas">
        ${estado.visao === 'calendario' ? '' : `
          <button class="t-ferr" data-menu-agrupar>${icone('camadas', 15)}<span>Agrupar: <b>${esc(rotuloAgrupar)}</b></span></button>`}
        <label class="t-busca">${icone('busca', 15)}<input id="t-busca" placeholder="Buscar tarefa" value="${esc(estado.busca)}" /></label>
        <button class="t-ferr t-nova-btn" data-nova-tarefa>+ Tarefa</button>
      </div>
      <div class="tarefas-corpo">${corpo()}</div>
    </div>`;
  el.querySelector('.tarefas-corpo').scrollTop = rolagem;
  ligar(el);
  if (estado.adicionando) el.querySelector('.t-nova:not(.t-sub) input')?.focus();
}

/* ---------- Lista ---------- */

const CABECALHO = `
  <div class="t-linha t-cab">
    <span>Nome</span><span>Pedido por</span><span>Responsável</span><span>Prazo</span><span>Status</span><span>Prioridade</span><span>Workspace</span>
  </div>`;

function visaoLista() {
  const montando = estado.agrupar === 'status' ? atendimentos() : [];
  return (montando.length ? montandoBloco(montando) : '') + agrupado().map(grupoLista).join('');
}

function topoGrupo(g) {
  const fechado = fechados.has(g.id);
  return `
    <button class="t-grupo-topo" data-alternar="${g.id}">
      <span class="t-seta ${fechado ? '' : 'aberta'}">${icone('seta', 14)}</span>
      <span class="t-etiqueta ${g.classe}">${esc(g.rotulo)}</span>
      <span class="t-conta">${g.itens.length}</span>
      ${g.herda ? `<span class="t-grupo-mais" data-adicionar="${g.id}" title="Adicionar tarefa">+</span>` : ''}
    </button>`;
}

function grupoLista(g) {
  const fechado = fechados.has(g.id);
  return `
    <section class="t-grupo">
      ${topoGrupo(g)}
      ${fechado ? '' : `
        <div class="t-tabela">
          ${CABECALHO}
          ${g.itens.map(comFilhas).join('')}
          ${estado.adicionando === g.id ? `
            <div class="t-linha t-nova"><input placeholder="Nome da tarefa e Enter (Esc cancela)" data-herda='${esc(JSON.stringify(g.herda))}' /></div>`
            : `<button class="t-adicionar" data-adicionar="${g.id}">+ Adicionar tarefa</button>`}
        </div>`}
    </section>`;
}

function comFilhas(t) {
  const lista = filhos[t.id] || [];
  const aberto = expandidos.has(t.id) || subNova === t.id;
  return linha(t, 0) + (aberto ? lista.map((f) => linha(f, 1)).join('') : '')
    + (subNova === t.id ? `<div class="t-linha t-nova t-sub"><input placeholder="Nome da subtarefa e Enter (Esc cancela)" data-sub-pai="${t.id}" /></div>` : '');
}

function nome(t, nivel) {
  const [, cor] = situacao(t);
  const n = (filhos[t.id] || []).length;
  const seta = nivel ? '' : n
    ? `<button class="t-expandir ${expandidos.has(t.id) ? 'aberto' : ''}" data-expandir="${t.id}" title="Subtarefas">${icone('seta', 13)}</button>`
    : '<span class="t-expandir-vazio"></span>';
  const titulo = renomeando === t.id
    ? `<input class="t-renomear" data-renomear-campo="${t.id}" value="${esc(t.titulo)}" />`
    : `<button class="t-nome" data-id="${t.id}"><i class="t-bola ${cor}"></i><span>${esc(t.titulo)}</span></button>`;
  return `
    <span class="t-nome-cel ${nivel ? 't-filha' : ''}">
      ${seta}${titulo}
      ${n && !nivel ? `<span class="t-subs" title="${n} subtarefa(s)">${icone('sub', 13)}${n}</span>` : ''}
      <small class="t-id">${t.id}</small>
      <span class="t-acoes-hover">
        ${nivel ? '' : `<button data-sub="${t.id}" title="Adicionar subtarefa">+</button>`}
        <button data-renomear="${t.id}" title="Renomear">${icone('lapis', 13)}</button>
      </span>
    </span>`;
}

function linha(t, nivel = 0) {
  const [rotulo, cor] = situacao(t);
  const ws = t.ficha?.workspace?.nome || '';
  return `
    <div class="t-linha t-item">
      ${nome(t, nivel)}
      <span class="t-pessoa">${avatar(t.pessoa)}<span>${esc(pessoa(t.pessoa).nome.split(' ')[0])}</span></span>
      <button class="t-cel" data-menu="responsavel" data-tarefa="${t.id}">${responsavel(t)}</button>
      ${prazo(t)}
      <span class="t-cel"><span class="t-status ${cor}">${esc(rotulo)}</span></span>
      ${bandeira(t)}
      <span class="t-cel apagado t-ws" title="${esc(ws)}">${esc(ws) || '—'}</span>
    </div>`;
}

function montandoBloco(itens) {
  const g = { id: 'st:montando', rotulo: 'Conversando com quem pediu', classe: 'g-roxo', itens };
  return `
    <section class="t-grupo">
      ${topoGrupo(g)}
      ${fechados.has(g.id) ? '' : `<div class="t-tabela">${CABECALHO}${itens.map((a) => `
        <div class="t-linha t-item t-montando">
          <span class="t-nome"><i class="t-bola st-cinza"></i><span>${esc(a.ficha?.titulo || a.ficha?.pedido || 'Pedido em conversa')}</span><small>${a.id}</small></span>
          <span class="t-pessoa">${avatar(a.pessoa)}<span>${esc(pessoa(a.pessoa).nome.split(' ')[0])}</span></span>
          <span class="t-cel">${a.ficha?.tipo ? esc(agentesNomes()[a.ficha.tipo]?.apelido || '') : '<span class="apagado">—</span>'}</span>
          <span class="t-cel apagado">${a.ficha?.prazo ? esc(dataCurta(a.ficha.prazo)) : '—'}</span>
          <span class="t-cel"><span class="t-status st-cinza">${a.estado === 'confirmando' ? 'Esperando confirmar' : a.estado === 'na_espera' ? 'Na espera' : 'Montando'}</span></span>
          <span class="t-cel apagado">${esc(a.ficha?.prioridade || '')}</span>
          <span class="t-cel apagado t-ws">${esc(a.ficha?.workspace?.nome || '—')}</span>
        </div>`).join('')}</div>`}
    </section>`;
}

/* ---------- Quadro ---------- */

function visaoQuadro() {
  return `<div class="t-quadro">${agrupado().filter((g) => g.id !== 'st:feito' || g.itens.length).map((g) => `
    <section class="t-coluna">
      <header><span class="t-etiqueta ${g.classe}">${esc(g.rotulo)}</span><span class="t-conta">${g.itens.length}</span></header>
      <div class="t-coluna-itens">${g.itens.slice(0, g.id === 'st:feito' ? 15 : 200).map(cartao).join('') || '<p class="apagado t-vazio">Nada aqui.</p>'}</div>
    </section>`).join('')}</div>`;
}

function cartao(t) {
  const [rotulo, cor] = situacao(t);
  return `
    <article class="t-cartao">
      <button class="t-cartao-titulo" data-id="${t.id}">${esc(t.titulo)}</button>
      ${(filhos[t.id] || []).length ? `<span class="t-subs">${icone('sub', 13)}${filhos[t.id].length} subtarefa(s)</span>` : ''}
      <div class="t-cartao-meta"><span class="t-status ${cor}">${esc(rotulo)}</span><small>${t.id}</small></div>
      <div class="t-cartao-rodape">
        ${avatar(t.pessoa)}
        <button class="t-cel" data-menu="responsavel" data-tarefa="${t.id}">${responsavel(t)}</button>
        <span class="t-empurra"></span>
        ${prazo(t)}
        ${bandeira(t, false)}
      </div>
    </article>`;
}

/* ---------- Calendário ---------- */

function visaoCalendario() {
  const base = estado.mes || `${hoje().slice(0, 7)}-01`;
  const primeiro = new Date(`${base}T12:00:00`);
  const inicio = somar(base, -((primeiro.getDay() + 6) % 7)); // segunda da primeira semana
  const porDia = {};
  lista().filter((t) => t.prazo).forEach((t) => { (porDia[t.prazo] ||= []).push(t); });
  const semPrazo = lista().filter((t) => !t.prazo && t.status !== 'feito').length;
  const dias = [];
  for (let i = 0; i < 42; i += 1) dias.push(somar(inicio, i));
  const mes = base.slice(0, 7);
  return `
    <div class="t-cal">
      <div class="t-cal-topo">
        <button class="t-ferr" data-mes="-1">‹</button>
        <b>${MESES_LONGOS[primeiro.getMonth()]} ${primeiro.getFullYear()}</b>
        <button class="t-ferr" data-mes="1">›</button>
        <button class="t-ferr" data-mes="0">Hoje</button>
        <span class="apagado">${semPrazo} em aberto sem prazo (aparecem na Lista)</span>
      </div>
      <div class="t-cal-grade">
        ${DIAS.map((d) => `<div class="t-cal-dia-nome">${d}</div>`).join('')}
        ${dias.map((d) => `
          <div class="t-cal-dia ${d.slice(0, 7) !== mes ? 'fora' : ''} ${d === hoje() ? 'hoje' : ''}">
            <span class="t-cal-num">${Number(d.slice(8))}</span>
            ${(porDia[d] || []).slice(0, 4).map((t) => `
              <button class="t-cal-item ${situacao(t)[1]}" data-id="${t.id}" title="${esc(t.titulo)}">${esc(t.titulo)}</button>`).join('')}
            ${(porDia[d] || []).length > 4 ? `<span class="apagado t-cal-mais">+${porDia[d].length - 4}</span>` : ''}
          </div>`).join('')}
      </div>
    </div>`;
}

/* ---------- Linha do tempo ---------- */

function visaoTempo() {
  const inicio = somar(hoje(), -7);
  const n = 35;
  const dias = Array.from({ length: n }, (_, i) => somar(inicio, i));
  const pos = (dia) => Math.max(0, Math.min(n, Math.round((new Date(`${dia}T12:00:00`) - new Date(`${inicio}T12:00:00`)) / 86400000)));
  const barra = (t) => {
    const de = (t.criadaEm || hoje()).slice(0, 10);
    const ate = t.status === 'feito' ? (t.concluidaEm || de).slice(0, 10) : (t.prazo && t.prazo > hoje() ? t.prazo : hoje());
    const a = pos(de < inicio ? inicio : de);
    const b = Math.max(a + 1, pos(ate) + 1);
    const atrasada = t.prazo && t.prazo < hoje() && t.status !== 'feito';
    const marca = t.prazo && t.prazo >= inicio ? `<i class="t-tl-prazo" style="left:${((pos(t.prazo) + .5) / n) * 100}%" title="Prazo ${esc(dataCurta(t.prazo))}"></i>` : '';
    return `<span class="t-tl-barra ${situacao(t)[1]} ${atrasada ? 'atrasada' : ''}" style="left:${(a / n) * 100}%;width:${((b - a) / n) * 100}%"></span>${marca}`;
  };
  const agora = ((pos(hoje()) + .5) / n) * 100;
  return `
    <div class="t-tl">
      <div class="t-tl-linha t-tl-cab">
        <span></span>
        <div class="t-tl-dias">${dias.map((d) => `<span class="${d === hoje() ? 'hoje' : ''}">${new Date(`${d}T12:00:00`).getDate() === 1 || d === inicio ? `${Number(d.slice(8))} ${MESES[Number(d.slice(5, 7)) - 1]}` : Number(d.slice(8))}</span>`).join('')}</div>
      </div>
      ${agrupado().filter((g) => g.itens.length).map((g) => `
        <div class="t-tl-grupo">${topoGrupo(g)}</div>
        ${fechados.has(g.id) ? '' : g.itens.map((t) => `
          <div class="t-tl-linha">
            <button class="t-nome" data-id="${t.id}"><i class="t-bola ${situacao(t)[1]}"></i><span>${esc(t.titulo)}</span></button>
            <div class="t-tl-trilho"><i class="t-tl-hoje" style="left:${agora}%"></i>${barra(t)}</div>
          </div>`).join('')}`).join('')}
    </div>`;
}

/* ---------- menus e ações ---------- */

function menu(alvo, opcoes, escolher) {
  document.querySelector('.t-menu')?.remove();
  const r = alvo.getBoundingClientRect();
  const m = document.createElement('div');
  m.className = 't-menu';
  m.innerHTML = opcoes.map(([v, html]) => `<button data-v="${esc(v)}">${html}</button>`).join('');
  m.style.left = `${Math.min(r.left, innerWidth - 260)}px`;
  m.style.top = `${r.bottom + 4}px`;
  document.body.appendChild(m);
  m.addEventListener('click', (e) => {
    const b = e.target.closest('[data-v]');
    if (!b) return;
    m.remove();
    escolher(b.dataset.v);
  });
  setTimeout(() => document.addEventListener('click', function fora(e) {
    if (!m.contains(e.target)) { m.remove(); document.removeEventListener('click', fora); }
  }), 0);
}

const mudar = (id, acao, corpo) => decidir(id, acao, corpo).catch((e) => falar(e.message));

async function criar(titulo, herda) {
  const r = await fetch('/api/tarefas', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ titulo, ...herda }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { falar(d.erro || 'Não consegui criar a tarefa.'); return false; }
  falar(`${d.id} criada.`);
  return true;
}

function ligar(el) {
  const busca = el.querySelector('#t-busca');
  busca.addEventListener('input', () => {
    estado.busca = busca.value;
    const cursor = busca.selectionStart;
    renderTarefas(el, { forcar: true });
    const nova = el.querySelector('#t-busca');
    nova.focus();
    nova.setSelectionRange(cursor, cursor);
  });
  el.querySelectorAll('[data-prazo]').forEach((i) => i.addEventListener('change', () => {
    mudar(i.dataset.prazo, 'editar', { prazo: i.value });
    i.blur();
  }));
  const campoNome = el.querySelector('[data-renomear-campo]');
  if (campoNome) {
    campoNome.focus();
    campoNome.select();
    campoNome.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { renomeando = null; campoNome.blur(); renderTarefas(el, { forcar: true }); }
      if (e.key === 'Enter' && campoNome.value.trim()) {
        mudar(campoNome.dataset.renomearCampo, 'editar', { titulo: campoNome.value.trim() });
        renomeando = null; campoNome.blur(); renderTarefas(el, { forcar: true });
      }
    });
  }
  const sub = el.querySelector('[data-sub-pai]');
  if (sub) {
    sub.focus();
    sub.addEventListener('keydown', async (e) => {
      if (e.key === 'Escape') { subNova = null; sub.blur(); return renderTarefas(el, { forcar: true }); }
      if (e.key !== 'Enter' || !sub.value.trim()) return;
      if (await criar(sub.value.trim(), { pai: sub.dataset.subPai })) { sub.value = ''; expandidos.add(sub.dataset.subPai); }
    });
  }
  const nova = el.querySelector('.t-nova:not(.t-sub) input');
  nova?.addEventListener('keydown', async (e) => {
    if (e.key === 'Escape') { estado.adicionando = null; nova.blur(); return renderTarefas(el, { forcar: true }); }
    if (e.key !== 'Enter' || !nova.value.trim()) return;
    if (await criar(nova.value.trim(), JSON.parse(nova.dataset.herda || '{}'))) nova.value = '';
  });
}

// Cliques da tela (tratados junto com a navegação no app.js). true = era daqui.
export function cliqueTarefas(e) {
  const visao = e.target.closest('[data-visao-tarefas]');
  if (visao) {
    estado.visao = visao.dataset.visaoTarefas;
    guardar('tarefas.visao', estado.visao);
    set({});
    return true;
  }
  const mes = e.target.closest('[data-mes]');
  if (mes) {
    const passo = Number(mes.dataset.mes);
    const base = new Date(`${estado.mes || `${hoje().slice(0, 7)}-01`}T12:00:00`);
    base.setMonth(base.getMonth() + passo);
    estado.mes = passo === 0 ? null : `${iso(base).slice(0, 7)}-01`;
    set({});
    return true;
  }
  if (e.target.closest('[data-menu-agrupar]')) {
    menu(e.target.closest('[data-menu-agrupar]'), AGRUPAR.map(([v, r]) => [v, `${v === estado.agrupar ? '✓ ' : ''}${r}`]), (v) => {
      estado.agrupar = v; guardar('tarefas.agrupar', v); estado.adicionando = null; set({});
    });
    return true;
  }
  if (e.target.closest('[data-nova-tarefa]')) {
    estado.visao = 'lista';
    estado.adicionando = agrupado()[0]?.id || null;
    set({});
    return true;
  }
  const expandir = e.target.closest('[data-expandir]');
  if (expandir) {
    const id = expandir.dataset.expandir;
    expandidos.has(id) ? expandidos.delete(id) : expandidos.add(id);
    guardar('tarefas.expandidos', [...expandidos]);
    set({});
    return true;
  }
  const novaSub = e.target.closest('[data-sub]');
  if (novaSub) { subNova = novaSub.dataset.sub; set({}); return true; }
  const renomear = e.target.closest('[data-renomear]');
  if (renomear) { renomeando = renomear.dataset.renomear; set({}); return true; }
  const maisGrupo = e.target.closest('.t-grupo-mais');
  if (maisGrupo) { estado.adicionando = maisGrupo.dataset.adicionar; set({}); return true; }
  const alternar = e.target.closest('[data-alternar]');
  if (alternar) {
    const id = alternar.dataset.alternar;
    fechados.has(id) ? fechados.delete(id) : fechados.add(id);
    guardar('tarefas.fechados', [...fechados]);
    set({});
    return true;
  }
  const adicionar = e.target.closest('[data-adicionar]');
  if (adicionar) {
    estado.adicionando = adicionar.dataset.adicionar;
    set({});
    return true;
  }
  const abrirPrazo = e.target.closest('[data-abrir-prazo]');
  if (abrirPrazo) {
    const campo = abrirPrazo.querySelector('input[type=date]');
    try { campo.showPicker(); } catch { campo.focus(); }
    return true;
  }
  const alvo = e.target.closest('[data-menu]');
  if (alvo) {
    const id = alvo.dataset.tarefa;
    if (alvo.dataset.menu === 'prioridade') {
      menu(alvo, Object.entries(PRIORIDADE).map(([p, [r, c]]) => [p, `<span class="t-prio ${c}">${icone('bandeira', 14)}</span>${r}`]),
        (p) => mudar(id, 'editar', { prioridade: p }));
    } else {
      const nomes = agentesNomes();
      menu(alvo, [['yago', '<span class="t-ag g-amarelo">Y</span>Você'],
        ...Object.keys(nomes).map((tipo) => [tipo, `<span class="t-ag" style="background:${COR_AGENTE[tipo]}">${esc(nomes[tipo].apelido[0])}</span>${esc(nomeAgente(tipo))}`])],
      (para) => mudar(id, 'responsavel', { para }));
    }
    return true;
  }
  return false;
}
