// Conversa com o servidor local: chamadas + canal ao vivo (SSE) com reconexão.

import { carregar, trocarTarefa, trocarPessoas, novoEvento, trocarMetricas, trocarConversas, trocarFila, trocarJornada, trocarAtendimentos } from './estado.js';

async function pedir(metodo, url, corpo) {
  const r = await fetch(url, {
    method: metodo,
    headers: corpo ? { 'Content-Type': 'application/json' } : {},
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  const dados = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(dados.erro || `Erro ${r.status}`);
  return dados;
}

let versao = null;

export async function recarregarEstado() {
  const estado = await pedir('GET', '/api/estado');
  if (versao && estado.versao !== versao) return location.reload(); // servidor voltou com painel novo
  versao = estado.versao;
  carregar(estado);
}

// Decisão sobre uma tarefa. A tela se atualiza pelo canal ao vivo.
export async function decidir(id, acao, corpo = {}) {
  const t = await pedir('POST', `/api/tarefas/${id}/${acao}`, corpo);
  trocarTarefa(t);
  return t;
}

export const buscarEventos = (antes) => pedir('GET', `/api/eventos?antes=${antes}&limite=30`).then((d) => d.eventos);

export const salvarConfig = (chave, patch) => pedir('PUT', `/api/config/${chave}`, patch);

/**
 * Abre o canal ao vivo. `ao` recebe os avisos que não são só dados:
 *   aviso(tipo, tarefa) · fala(texto) · conexao(ok) · vigia({ ok, erro })
 */
export function conectar(ao) {
  recarregarEstado(); // não espera o canal abrir pra mostrar os dados
  const fonte = new EventSource('/api/ao-vivo');
  const json = (fn) => (e) => fn(JSON.parse(e.data));

  // Ao (re)conectar, busca tudo de novo: algo pode ter mudado enquanto estava fora.
  fonte.onopen = () => { recarregarEstado(); ao.conexao(true); };
  fonte.onerror = () => ao.conexao(false); // o navegador tenta de novo sozinho

  fonte.addEventListener('tarefa', json((d) => trocarTarefa(d.tarefa)));
  fonte.addEventListener('pessoas', json((d) => trocarPessoas(d.pessoas)));
  fonte.addEventListener('evento', json((d) => novoEvento(d.evento)));
  fonte.addEventListener('metricas', json((d) => trocarMetricas(d.metricas)));
  fonte.addEventListener('aviso', json((d) => ao.aviso(d.aviso, d.tarefa)));
  fonte.addEventListener('fala', json((d) => ao.fala(d.texto)));
  fonte.addEventListener('vigia', json((d) => ao.vigia(d)));
  fonte.addEventListener('devLocal', json((d) => ao.devLocal(d.devLocal)));
  fonte.addEventListener('abrirAba', json((d) => ao.abrirAba(d)));
  fonte.addEventListener('conversas', json((d) => trocarConversas(d.conversas)));
  fonte.addEventListener('fila', json(trocarFila));
  fonte.addEventListener('atendimentos', json((d) => trocarAtendimentos(d.atendimentos)));
  fonte.addEventListener('jornada', json((d) => trocarJornada(d.jornada)));
  fonte.addEventListener('falaTarefa', json((d) => ao.falaTarefa(d.fala)));
  fonte.addEventListener('petResposta', json((d) => ao.petResposta(d)));
  fonte.addEventListener('recarregar', () => location.reload());
}
