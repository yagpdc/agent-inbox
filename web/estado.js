// Estado do painel: cópia local do que está no servidor + o que a tela está mostrando.
// O servidor é a fonte da verdade; as mudanças chegam pelo canal ao vivo (api.js).

// visao: 'inicio' | 'config' | 'minhas' | 'tudo' | 'execucao' | 'feitas' | 'sem-categoria' | 'cat:<id>' | 'cat:mapa:<sub>'
export const ui = { visao: 'inicio', selecionada: null, busca: '', pessoa: '', agente: null, agenteAba: 'atividade' };

const dados = { tarefas: [], eventos: [], config: {}, metricas: {}, fila: [], ativos: [], atendimentos: [], agentes: {} };
export const PESSOAS = {}; // preenchido pelo servidor; mesmo objeto sempre (é importado em vários lugares)

const ouvintes = [];
export const aoMudar = (fn) => ouvintes.push(fn);
export const avisar = () => ouvintes.forEach((fn) => fn());

export function set(patch) {
  Object.assign(ui, patch);
  avisar();
}

/* ---------- dados vindos do servidor ---------- */

export function carregar(estado) {
  Object.assign(dados, estado);
  dados.fimEventos = estado.eventos.length < 30;
  Object.keys(PESSOAS).forEach((k) => delete PESSOAS[k]);
  Object.assign(PESSOAS, estado.pessoas);
  avisar();
}

export function trocarPessoas(pessoas) {
  Object.assign(PESSOAS, pessoas);
  avisar();
}

export function trocarTarefa(t) {
  const i = dados.tarefas.findIndex((x) => x.id === t.id);
  if (i >= 0) dados.tarefas[i] = t;
  else dados.tarefas.unshift(t);
  avisar();
}

export function novoEvento(e) {
  dados.eventos.unshift(e);
  avisar();
}

export function trocarMetricas(m) {
  dados.metricas = m;
  avisar();
}

export const tarefas = () => dados.tarefas;
export const atendimentos = () => dados.atendimentos || [];
export const agentesNomes = () => dados.agentes || {};

export function trocarAtendimentos(lista) {
  dados.atendimentos = lista || [];
  avisar();
}
export const tarefa = (id) => dados.tarefas.find((t) => t.id === id);
export const eventos = () => dados.eventos;
export const fimEventos = () => dados.fimEventos;

// Página mais antiga da atividade (rolagem infinita).
export function maisEventos(lista) {
  const vistos = new Set(dados.eventos.map((e) => e.id));
  dados.eventos.push(...lista.filter((e) => !vistos.has(e.id)));
  dados.fimEventos = lista.length < 30;
  avisar();
}
export const metricas = () => dados.metricas;
export const config = () => dados.config;
export const fila = () => dados.fila;
export const jornada = () => dados.jornada;

export function trocarJornada(j) {
  dados.jornada = j;
  avisar();
}
export const ativos = () => dados.ativos;

// Uma execução por repositório: quem está rodando agora e quem espera a vez.
export function trocarFila({ ativos: a, fila: f }) {
  dados.ativos = a || [];
  dados.fila = f || [];
  avisar();
}
export const conversaAssumida = (t) => !!t?.espaco && config().conversas?.[t.espaco]?.modo === 'assumida';

export function trocarConversas(conversas) {
  dados.config.conversas = conversas;
  avisar();
}
export const pessoa = (id) => PESSOAS[id] || { nome: 'Colega', iniciais: '?', cor: '#979dab' };

/* ---------- regras de visão ---------- */

// Com o orquestrador, tarefa confirmada pela pessoa (tem ficha) não espera você até ficar pronta pro deploy.
// Travou (falhou) sempre precisa de você: no modo autônomo ninguém mais olha a tarefa.
export const precisaDeMim = (t) => (t.status !== 'feito' && (t.esperando || '').includes('falhou')) || (
  t.ficha && config().orquestrador?.autonomo !== false
    ? ['pergunta', 'resposta', 'revisao'].includes(t.status)
    : ['identificada', 'comigo', 'pergunta', 'resposta', 'aprovacao', 'revisao'].includes(t.status));

export function naVisao(t, visao) {
  if (visao === 'minhas') return precisaDeMim(t);
  if (visao === 'tarefas') return t.status !== 'feito' && !t.descartada;
  if (['tudo', 'quadro', 'inicio', 'config', 'agentes'].includes(visao)) return true;
  if (visao === 'execucao') return t.status === 'execucao';
  if (visao === 'feitas') return t.status === 'feito';
  if (visao === 'sem-categoria') return !t.categoria && t.status !== 'comigo' && t.status !== 'feito';
  if (visao.startsWith('cat:')) {
    const [, cat, sub] = visao.split(':');
    return t.categoria === cat && (!sub || t.sub === sub);
  }
  return true;
}

export function daLista() {
  const termo = ui.busca.trim().toLowerCase();
  return tarefas()
    .filter((t) => naVisao(t, ui.visao))
    .filter((t) => !ui.pessoa || t.pessoa === ui.pessoa)
    .filter((t) => !termo || `${t.id} ${t.titulo} ${t.pedido}`.toLowerCase().includes(termo))
    .sort((a, b) => (precisaDeMim(b) - precisaDeMim(a)) || (new Date(b.criadaEm) - new Date(a.criadaEm)));
}

export const contar = (visao) => tarefas().filter((t) => naVisao(t, visao)).length;

/* ---------- formatação ---------- */

export const esc = (s = '') =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export function faz(iso) {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (min < 1) return 'agora';
  if (min < 60) return `${min} min`;
  if (min < 60 * 24) return `${Math.round(min / 60)} h`;
  return `${Math.round(min / 1440)} d`;
}
