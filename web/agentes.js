// Tela Agentes: o que cada agente está fazendo, o que já fez, a config dele e o contexto que ele lê.

import { ui, set, esc, faz, pessoa } from './estado.js';
import { salvarConfig } from './api.js';
import { icone } from './icones.js';

const MODELOS = [['opus', 'Opus'], ['sonnet', 'Sonnet'], ['haiku', 'Haiku']];
const ESFORCOS = [['low', 'baixo'], ['medium', 'médio'], ['high', 'alto'], ['xhigh', 'muito alto'], ['max', 'máximo']];
const WORKSPACE = [['obrigatorio', 'Obrigatório'], ['se_bug', 'Só se for bug'], ['opcional', 'Opcional'], ['nao', 'Não se aplica']];
const OBRIGATORIO = [['true', 'Obrigatório'], ['bug', 'Só se for bug'], ['false', 'Opcional']];
const ESTADO_ATENDIMENTO = { coletando: 'Conversando', confirmando: 'Esperando ela confirmar', na_espera: 'Confirmado, na espera' };
const ABAS = [['atividade', 'Atividade'], ['config', 'Configuração'], ['contexto', 'Contexto'], ['aprendizados', 'Aprendizados']];

let dados = null;
let carregando = null;

async function buscar() {
  const r = await fetch('/api/agentes');
  dados = await r.json();
  return dados;
}

async function salvar(url, corpo) {
  const r = await fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erro || `Erro ${r.status}`);
  return d;
}

const opcoes = (lista, atual) =>
  lista.map(([v, r]) => `<option value="${v}" ${String(atual) === v ? 'selected' : ''}>${r}</option>`).join('');

const editando = (el) => el.contains(document.activeElement) && /TEXTAREA|INPUT|SELECT/.test(document.activeElement.tagName);

// Chamado a cada mudança de estado: só redesenha se você não estiver no meio de uma edição.
export function renderAgentes(el, { forcar = false } = {}) {
  if (!forcar && editando(el)) return;
  if (!dados) {
    el.innerHTML = '<div class="agentes"><h1 class="manchete">Agentes</h1><p class="apagado">Carregando…</p></div>';
  }
  if (!carregando) {
    carregando = buscar().then(() => { carregando = null; desenhar(el); }).catch(() => { carregando = null; });
  }
  if (dados) desenhar(el);
}

function desenhar(el) {
  if (editando(el)) return;
  const sel = ui.agente && dados.agentes[ui.agente] ? ui.agente : null;
  el.innerHTML = `<div class="agentes">${sel ? detalhe(sel) : visaoGeral()}</div>`;
  ligar(el);
}

/* ---------- visão geral ---------- */

function visaoGeral() {
  const o = dados.orquestrador || {};
  const cards = Object.entries(dados.agentes).map(([tipo, a]) => cartao(tipo, a)).join('');
  return `
    <h1 class="manchete">Agentes</h1>
    <section class="agente-orq">
      <div class="agente-orq-topo">
        <div>
          <h3>${esc(o.nome || 'Orquestrador')} <span class="apagado">· Orquestrador</span></h3>
          <p class="apagado">Conversa com as pessoas no Chat, monta a ficha, confirma com quem pediu e manda pro agente certo.</p>
        </div>
        <div class="agente-orq-chaves">
          <label class="movel-linha"><span>Modo autônomo</span>
            <span class="chave"><input type="checkbox" id="ag-autonomo" ${o.autonomo !== false ? 'checked' : ''} /><span></span></span>
          </label>
          <label class="agente-num">Pedidos em andamento por pessoa
            <input type="number" id="ag-max" min="1" max="10" value="${o.maxAbertas ?? 2}" />
          </label>
        </div>
      </div>
      <p class="apagado agente-dica">${o.autonomo !== false
        ? 'Pedido confirmado pela pessoa já vai pro agente. Você só faz o deploy.'
        : 'Desligado: o orquestrador continua conversando e montando a ficha, mas a tarefa espera o seu clique.'}</p>
      ${atendimentos()}
    </section>
    <div class="agentes-grade">${cards}</div>`;
}

function atendimentos() {
  const lista = dados.atendimentos || [];
  if (!lista.length) return '<p class="apagado">Nenhum pedido sendo montado agora.</p>';
  return `<ul class="atendimentos">${lista.map((a) => {
    const f = a.ficha || {};
    const nomeAgente = dados.agentes[f.tipo]?.definicao?.nome || 'tipo ainda não definido';
    return `
      <li>
        <span class="avatar" style="background:${pessoa(a.pessoa).cor}">${esc(pessoa(a.pessoa).iniciais)}</span>
        <div>
          <b>${esc(f.titulo || f.pedido || 'Pedido em conversa')}</b>
          <span class="apagado">${esc(pessoa(a.pessoa).nome.split(' ')[0])} · ${esc(nomeAgente)}${f.workspace?.nome ? ` · ${esc(f.workspace.nome)}` : ''} · ${ESTADO_ATENDIMENTO[a.estado] || a.estado} · ${faz(a.atualizado_em)}</span>
        </div>
        <button class="btn fino" data-cancelar-atendimento="${a.id}">Cancelar</button>
      </li>`;
  }).join('')}</ul>`;
}

function cartao(tipo, a) {
  const d = a.definicao;
  const agora = a.agora[0];
  const n = a.numeros;
  const modelo = tipo === 'duvida'
    ? `Pesquisa: ${nomeModelo(d.pesquisa)}`
    : `Plano: ${nomeModelo(d.plano)} · Execução: ${nomeModelo(d.execucao)}`;
  return `
    <button class="agente-card" data-agente="${tipo}">
      <div class="agente-card-topo">
        ${icone(tipo === 'duvida' ? 'interrogacao' : tipo)}
        <b>${esc(d.apelido || d.nome)}</b><span class="apagado">${esc(d.apelido ? d.nome : '')}</span>
        <span class="agente-luz ${agora ? 'ligado' : ''}"></span>
      </div>
      <p class="agente-agora">${agora
        ? `${esc(agora.id)} · ${esc(agora.titulo)}<br><span class="apagado">${esc(agora.passo || agora.status)}</span>`
        : '<span class="apagado">Parado</span>'}</p>
      ${a.fila.length ? `<p class="apagado">${a.fila.length} na fila</p>` : ''}
      <p class="agente-numeros"><span>${n.feitas} feitas</span><span>${n.ajustadas} com ajuste</span><span>${n.abertas} abertas</span></p>
      <p class="apagado agente-modelo">${modelo}</p>
    </button>`;
}

const nomeModelo = (m) => m ? `${(MODELOS.find(([v]) => v === m.modelo) || [, m.modelo])[1]} ${(ESFORCOS.find(([v]) => v === m.esforco) || [, m.esforco])[1]}` : '-';

/* ---------- um agente ---------- */

function detalhe(tipo) {
  const a = dados.agentes[tipo];
  const aba = ui.agenteAba || 'atividade';
  const corpo = { atividade, config: configuracao, contexto: arquivo, aprendizados: arquivo }[aba](tipo, a, aba);
  return `
    <button class="btn fino voltar" data-agente="">← Agentes</button>
    <h1 class="manchete">${esc(a.definicao.apelido || a.definicao.nome)} <span class="apagado">· ${esc(a.definicao.nome)}</span></h1>
    <p class="apagado">${esc(a.definicao.resumo)}</p>
    <nav class="agente-abas">${ABAS.map(([id, r]) =>
      `<button data-agente-aba="${id}" aria-current="${aba === id}">${r}</button>`).join('')}</nav>
    ${corpo}`;
}

function atividade(tipo, a) {
  const linha = (t) => `
    <li data-abrir-tarefa="${t.id}">
      <b>${esc(t.id)}</b><span>${esc(t.titulo)}</span>
      <span class="apagado">${esc(t.passo || rotuloStatus(t))}</span>
    </li>`;
  return `
    <section class="agente-secao">
      <h3>Agora</h3>
      ${a.agora.length ? `<ul class="agente-lista">${a.agora.map(linha).join('')}</ul>` : '<p class="apagado">Parado.</p>'}
      ${a.fila.length ? `<p class="apagado">Na fila: ${a.fila.map((x) => esc(x.tarefa)).join(', ')}</p>` : ''}
    </section>
    <section class="agente-secao">
      <h3>Histórico</h3>
      ${a.historico.length ? `<ul class="agente-lista">${a.historico.map(linha).join('')}</ul>` : '<p class="apagado">Nada ainda.</p>'}
    </section>`;
}

const rotuloStatus = (t) => t.status === 'feito' ? (t.subiu ? 'No ar' : 'Concluída') : ({
  identificada: 'Na fila pra começar', triagem: 'Planejando', aprovacao: 'Plano pronto', execucao: 'Executando',
  pergunta: 'Esperando resposta', revisao: 'Pronto pra deploy', comigo: 'Com você', resposta: 'Resposta pronta',
}[t.status] || t.status);

function configuracao(tipo, a) {
  const d = a.definicao;
  const etapas = tipo === 'duvida' ? [['pesquisa', 'Pesquisa']] : [['plano', 'Plano'], ['execucao', 'Execução']];
  const cam = dados.camadas || {};
  return `
    <section class="agente-secao agente-config">
      <h3>Nome</h3>
      <div class="agente-linha"><span>Chamado de</span><input data-cfg="apelido" value="${esc(d.apelido || '')}" /></div>
      <h3>Modelos</h3>
      ${etapas.map(([id, r]) => `
        <div class="agente-linha">
          <span>${r}</span>
          <select data-cfg="${id}.modelo">${opcoes(MODELOS, d[id]?.modelo)}</select>
          <select data-cfg="${id}.esforco">${opcoes(ESFORCOS, d[id]?.esforco)}</select>
        </div>`).join('')}
      ${tipo === 'duvida' ? '' : `
      <h3>Ficha que o orquestrador precisa montar</h3>
      <div class="agente-linha"><span>Workspace</span><select data-cfg="workspace">${opcoes(WORKSPACE, d.workspace)}</select></div>
      ${(d.campos || []).map((c) => `
        <div class="agente-linha campo-ficha" data-campo="${esc(c.campo)}">
          <span>${esc(c.campo)}</span>
          <select data-cfg-campo="obrigatorio">${opcoes(OBRIGATORIO, c.obrigatorio)}</select>
          <input data-cfg-campo="pergunta" value="${esc(c.pergunta)}" />
        </div>`).join('')}`}
      <h3>O que é deploy pra ele</h3>
      <p class="apagado">${esc(d.deploy || '-')}</p>
      ${tipo === 'camadas' ? `
      <h3>Gravar em prod</h3>
      <label class="movel-linha"><span>Carregador de camadas liberado</span>
        <span class="chave"><input type="checkbox" id="ag-camadas-prod" ${cam.gravarEmProd ? 'checked' : ''} /><span></span></span>
      </label>
      <p class="apagado">Ligado: a camada sobe sozinha no ${esc(d.workspaceTeste?.nome || 'workspace de teste')} pra você conferir,
        e o seu deploy copia pro workspace do cliente. Usa um container descartável do backend (docker compose run --rm).</p>` : ''}
      <div class="agente-acoes"><button class="btn primario" id="ag-salvar-config">Salvar configuração</button>
        <span class="salvo" id="ag-salvo" hidden>Salvo</span></div>
    </section>`;
}

function arquivo(tipo, a, aba) {
  const texto = aba === 'contexto' ? a.contexto : a.aprendizados;
  const dica = aba === 'contexto'
    ? 'O que o agente lê em toda tarefa: onde fica cada coisa, armadilhas, como testar.'
    : 'Lições dos seus ajustes. Lidas em toda tarefa deste tipo; a mais nova vale mais.';
  return `
    <section class="agente-secao">
      <p class="apagado">${dica}</p>
      <textarea class="agente-texto" id="ag-texto" spellcheck="false">${esc(texto)}</textarea>
      <div class="agente-acoes"><button class="btn primario" id="ag-salvar-texto" data-qual="${aba}">Salvar</button>
        <span class="salvo" id="ag-salvo" hidden>Salvo</span></div>
    </section>`;
}

/* ---------- eventos ---------- */

function ligar(el) {
  const $ = (s) => el.querySelector(s);
  const mostrarSalvo = () => {
    const s = $('#ag-salvo');
    if (!s) return;
    s.hidden = false;
    setTimeout(() => { s.hidden = true; }, 1500);
  };

  $('#ag-autonomo')?.addEventListener('change', async (e) => {
    dados.orquestrador = await salvarConfig('orquestrador', { autonomo: e.target.checked });
    desenhar(el);
  });
  $('#ag-max')?.addEventListener('change', async (e) => {
    const v = Math.min(10, Math.max(1, Number(e.target.value) || 2));
    dados.orquestrador = await salvarConfig('orquestrador', { maxAbertas: v });
  });
  $('#ag-camadas-prod')?.addEventListener('change', async (e) => {
    if (e.target.checked && !confirm('Liberar o carregador a gravar camadas em prod (teste e, com o seu deploy, cliente)?')) {
      e.target.checked = false;
      return;
    }
    dados.camadas = await salvarConfig('camadas', { gravarEmProd: e.target.checked });
  });

  $('#ag-salvar-config')?.addEventListener('click', async () => {
    const patch = {};
    el.querySelectorAll('[data-cfg]').forEach((s) => {
      const [etapa, campo] = s.dataset.cfg.split('.');
      if (campo) (patch[etapa] ||= {})[campo] = s.value;
      else patch[etapa] = s.value;
    });
    const campos = [...el.querySelectorAll('.campo-ficha')].map((linha) => {
      const ob = linha.querySelector('[data-cfg-campo="obrigatorio"]').value;
      return { campo: linha.dataset.campo, obrigatorio: ob === 'true' ? true : ob === 'false' ? false : 'bug',
               pergunta: linha.querySelector('[data-cfg-campo="pergunta"]').value };
    });
    if (campos.length) patch.campos = campos;
    try {
      dados.agentes[ui.agente].definicao = await salvar(`/api/agentes/${ui.agente}`, patch);
      mostrarSalvo();
    } catch (err) { alert(err.message); }
  });

  $('#ag-salvar-texto')?.addEventListener('click', async (e) => {
    const qual = e.target.dataset.qual;
    const texto = $('#ag-texto').value;
    try {
      await salvar(`/api/agentes/${ui.agente}/${qual}`, { texto });
      dados.agentes[ui.agente][qual] = texto;
      mostrarSalvo();
    } catch (err) { alert(err.message); }
  });

  el.querySelectorAll('[data-cancelar-atendimento]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Cancelar esse pedido que está sendo montado? A pessoa não é avisada.')) return;
    await fetch(`/api/atendimentos/${b.dataset.cancelarAtendimento}/cancelar`, { method: 'POST' });
    await buscar();
    desenhar(el);
  }));
}

// Cliques que mudam de tela (tratados no app.js, junto com o resto da navegação).
export function cliqueAgentes(e) {
  const ag = e.target.closest('[data-agente]');
  if (ag) {
    set({ agente: ag.dataset.agente || null, agenteAba: 'atividade' });
    return true;
  }
  const aba = e.target.closest('[data-agente-aba]');
  if (aba) {
    set({ agenteAba: aba.dataset.agenteAba });
    return true;
  }
  const abrir = e.target.closest('[data-abrir-tarefa]');
  if (abrir) {
    set({ visao: 'tudo', selecionada: abrir.dataset.abrirTarefa });
    return true;
  }
  return false;
}
