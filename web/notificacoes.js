// Avisos de decisão: dá pra resolver direto neles, sem abrir a tarefa.
//   tarefa -> "Nova tarefa"       : liberar o plano?
//   plano  -> "Plano pronto"      : executar? (com modelo e esforço)
//   deploy -> "Pronto pra deploy" : subir?
// Com a aba em segundo plano também sai notificação do Windows e contador no título.

import { CATEGORIAS } from './constantes.js';
import { esc, pessoa, tarefa } from './estado.js';
import { avatar } from './lista.js';
import { pular } from './pet.js';
import { icone } from './icones.js';
import { recomendado, seletores, normalizar, descricaoExecucao } from './modelos.js';
import { renderPerguntas, respostas, completas, limpar, ligarPerguntas, FALTA_RESPONDER } from './perguntas.js';
import { campoResposta, campoDescarte, campoAnexos, anexosDe, limparAnexos, textoDaResposta, descartarRascunho, ligarRascunhos, rascunho } from './rascunhos.js';

const TITULO = 'Inbox Agent';
let naoVistas = 0;

function atualizarTitulo() {
  document.title = naoVistas ? `(${naoVistas}) ${TITULO}` : TITULO;
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) { naoVistas = 0; atualizarTitulo(); }
});

export const podeNotificarSistema = () => 'Notification' in window && Notification.permission === 'granted';

export async function pedirPermissao() {
  if (!('Notification' in window)) return false;
  return (await Notification.requestPermission()) === 'granted';
}

const OPCOES_CATEGORIA = CATEGORIAS.flatMap((c) =>
  c.subs ? c.subs.map((s) => [`${c.id}:${s.id}`, `${c.nome} · ${s.nome}`]) : [[c.id, c.nome]],
);

const SUB_SINGULAR = { bug: 'Bug', feature: 'Feature' };

function tags(t) {
  const c = CATEGORIAS.find((x) => x.id === t.categoria);
  const nomes = c ? [c.nome, SUB_SINGULAR[t.sub]].filter(Boolean) : ['Sem categoria'];
  return nomes.map((n) => `<span class="toast-tag">${esc(n)}</span>`).join('');
}

const TIPOS = {
  tarefa: {
    rotulo: 'Nova tarefa',
    texto: (t) => `“${t.pedido}”`,
    meta: () => '',
    botoes: [['fazer', 'Pode fazer', 't-sim'], ['planejar', 'Só o plano'], ['assumir', 'Deixa comigo'], ['abrir', 'Ver pedido'], ['descartar', 'Não é tarefa', 't-nao']],
    classificar: true,
  },
  plano: {
    rotulo: 'Plano pronto',
    texto: (t) => t.plano.resumo,
    meta: (t) => `Risco ${t.plano.risco} · cerca de ${t.plano.estimativa}`,
    botoes: [['aprovar', 'Executar', 't-sim'], ['abrir', 'Ver plano'], ['reprovar', 'Reprovar', 't-nao']],
    classificar: true,
    escolhas: true,
    exigeCategoria: 'aprovar',
  },
  duvida: {
    rotulo: 'Nova dúvida',
    texto: (t) => `“${t.pedido}”`,
    meta: (t) => (t.espaco ? `Posso assumir a conversa com ${pessoa(t.pessoa).nome.split(' ')[0]}?` : ''),
    botoes: [['assumir-conversa', 'Pode assumir', 't-sim'], ['repassar', 'Me repassa'], ['assumir', 'Deixa comigo'], ['abrir', 'Ver pedido'], ['descartar', 'Não é tarefa', 't-nao']],
    classificar: true,
  },
  resposta: {
    rotulo: 'Resposta pronta',
    texto: () => 'Revise e envie no Chat.',
    meta: () => '',
    botoes: [['enviar', 'Enviar no Chat', 't-sim'], ['abrir', 'Ver tarefa'], ['descartar', 'Descartar', 't-nao']],
    rascunho: true,
  },
  falhou: {
    rotulo: 'Travou',
    texto: (t) => t.esperando || 'Algo deu errado.',
    meta: () => '',
    botoes: [['abrir', 'Ver tarefa', 't-sim'], ['depois', 'Depois', 't-nao']],
  },
  complemento: {
    rotulo: 'Quem pediu acrescentou',
    texto: (t) => `${pessoa(t.pessoa).nome.split(' ')[0]} mandou mais detalhes depois de pronto. Veja na conversa da tarefa.`,
    meta: () => '',
    botoes: [['abrir', 'Ver tarefa', 't-sim'], ['depois', 'Depois', 't-nao']],
  },
  pergunta: {
    rotulo: 'Pergunta',
    texto: (t) => (t.pergunta?.suspeito ? 'Algo nessa conversa pede você. Já avisei que vou confirmar.' : null)
      || ({ plano: 'Dúvida antes de fechar o plano.', resposta: 'Preciso de você pra responder no Chat.' })[t.pergunta?.etapa]
      || 'Dúvida durante a execução.',
    meta: () => '',
    botoes: [['responder', 'Responder', 't-sim'], ['abrir', 'Ver tarefa']],
    perguntas: true,
  },
  deploy: {
    rotulo: 'Pronto pra deploy',
    rotuloDe: (t) => (t.resultado.pr ? `PR #${t.resultado.pr.numero} aberto`
      : ({ homolog: 'Na atlas-homolog', cliente: 'Camada no workspace de teste' })[t.resultado.deploy.etapa] || 'Pronto pra deploy'),
    texto: (t) => (t.ficha ? `Pediu: ${t.ficha.pedido}\n\nFeito: ${t.resultado.resumo || ''}\n\n` : '') + t.resultado.deploy.resumo,
    meta: (t) => `${descricaoExecucao(t.execucao.modelo, t.execucao.esforco)} terminou${t.resultado.commits?.length ? ` · ${t.resultado.commits.length} commit` : ''}`
      + (t.resultado.vaiJunto?.length ? ` · vai junto: ${t.resultado.vaiJunto.length} commit(s) da branch de origem` : ''),
    botoes: [['pr', 'Abrir PR', 't-sim'], ['deploy', 'Fazer deploy'], ['abrir', 'Ver resultado'], ['depois', 'Depois', 't-nao']],
    passos: true,
  },
};

function conteudo(tipo, t, escolha, descartando) {
  const cfg = TIPOS[tipo];
  const p = pessoa(t.pessoa);
  const semCategoria = !t.categoria;
  return `
    <div class="toast-topo">
      <span class="toast-rotulo">${cfg.rotuloDe ? cfg.rotuloDe(t) : cfg.rotulo}</span>
      ${tags(t)}
      <button class="toast-x" data-t="fechar" aria-label="fechar">${icone('fechar', 16)}</button>
    </div>

    <div class="toast-linha">
      ${avatar(t.pessoa)}
      <div class="toast-corpo">
        <span class="toast-quem">${esc(p.nome)}${t.prioridade === 'P0' ? ' · <b class="toast-urgente">Urgente</b>' : ''}</span>
        <b>${esc(t.titulo)}</b>
        <p>${esc(cfg.texto(t))}</p>
        ${cfg.texto(t).length > 140 ? '<button class="toast-mais" data-t="mais"></button>' : ''}
        ${cfg.meta(t) ? `<span class="toast-meta">${esc(cfg.meta(t))}</span>` : ''}
      </div>
    </div>

    ${cfg.passos && t.resultado.deploy.passos.length && t.resultado.deploy.tipo !== 'pr' ? `
      <ol class="toast-passos">${t.resultado.deploy.passos.map((x) => `<li><code>${esc(x)}</code></li>`).join('')}</ol>` : ''}

    ${cfg.classificar && semCategoria ? `
      <div class="toast-classificar">
        <span>Categoria</span>
        <div>${OPCOES_CATEGORIA.map(([v, n]) => `<button data-t="classificar" data-v="${v}">${n}</button>`).join('')}</div>
      </div>` : ''}

    ${cfg.perguntas ? `<div class="toast-perguntas">${renderPerguntas(t)}</div>` : ''}
    ${cfg.rascunho ? campoResposta(t, 'toast-rascunho') + campoAnexos(t.id, t.id) : ''}

    ${cfg.escolhas ? `<div class="toast-escolhas">${seletores('t', escolha, recomendado(t))}</div>` : ''}

    ${descartando ? `
      ${t.espaco ? campoDescarte(t, 'toast-rascunho', p.nome.split(' ')[0]) + campoAnexos(t.id, `descarte-${t.id}`) : ''}
      <div class="toast-acoes">
        <button class="t-nao" data-t="confirmar-descarte">Descartar</button>
        <button data-t="cancelar-descarte">Cancelar</button>
      </div>` : `
    <div class="toast-acoes">
      ${cfg.botoes.map(([acao, rotulo, classe = '']) => {
        if (acao === 'deploy' && t.resultado?.deploy?.etapa === 'homolog') rotulo = 'Subir pra main';
        if (acao === 'deploy' && t.resultado?.deploy?.tipo === 'entrega') rotulo = 'Enviar pra pessoa';
        if (acao === 'pr' && !t.resultado?.pr) return '';
        if (acao === 'deploy' && t.resultado?.deploy?.tipo === 'pr') rotulo = t.resultado.pr ? 'Fazer merge' : 'Abrir o PR de novo';
        if (acao === 'deploy' && t.resultado?.deploy?.tipo === 'camada') rotulo = t.resultado.deploy.etapa === 'cliente' ? 'Subir no cliente' : 'Subir no teste';
        if (acao === 'assumir-conversa' && !t.espaco) return '';
        const travado = cfg.exigeCategoria === acao && semCategoria;
        return `<button class="${classe}" data-t="${acao}" ${travado ? 'disabled title="Classifique primeiro"' : ''}>${rotulo}</button>`;
      }).join('')}
    </div>`}`;
}

// Só um aviso aberto por vez; os outros ficam numa linha e abrem com um clique.
function expandir(alvo) {
  document.querySelectorAll('#toasts .toast:not(.fala)').forEach((x) => x.classList.toggle('compacto', x !== alvo));
}

const CONFIRMACOES = {
  planejar: () => 'Plano liberado.',
  fazer: () => 'Vou planejar e executar. Te chamo pra você ver rodando.',
  pesquisar: () => 'Pesquisando pra responder.',
  enviar: () => 'Enviado no Chat.',
  responder: () => 'Respostas enviadas. Continuando.',
  assumir: () => 'Fica com você. Salvei a tarefa.',
  aprovar: (e) => `Executando com ${descricaoExecucao(e.modelo, e.esforco)}.`,
  deploy: () => 'Deploy autorizado.',
  descartar: () => 'Descartado.',
  reprovar: () => 'Refazendo o plano.',
  depois: () => 'Fica pra depois.',
  'assumir-conversa': () => 'Conversa assumida. Te chamo se algo for estranho.',
  repassar: () => 'Combinado: eu pesquiso e te mostro antes de responder.',
};

/**
 * tipo: 'tarefa' | 'plano' | 'pergunta' | 'resposta' | 'deploy'  (tarefa vira 'duvida' quando é dúvida)
 * acoes: { planejar(id), assumir(id), responder(id, respostas), aprovar(id, escolha), reprovar(id) -> bool, deploy(id),
 *          descartar(id), abrir(id), classificar(id, valor) }
 */
export function avisar(tipo, t, acoes) {
  if (tipo === 'tarefa' && t.tipo === 'duvida') tipo = 'duvida';
  if (!TIPOS[tipo]) return; // aviso de uma versão diferente do servidor
  const el = document.createElement('div');
  el.className = 'toast';
  el.dataset.tarefa = t.id;
  el.setAttribute('role', 'status');
  let escolha = recomendado(t);
  let descartando = false;
  const desenhar = () => { el.innerHTML = conteudo(tipo, t, escolha, descartando); };
  desenhar();

  if (tipo === 'pergunta') ligarPerguntas(el, desenhar);
  ligarRascunhos(el);

  const fechar = () => { el.classList.add('saindo'); setTimeout(() => el.remove(), 250); };
  const confirmar = (acao) => {
    el.classList.add('feito');
    el.innerHTML = `<div class="toast-ok">${icone('feitas', 18)}<span>${esc(CONFIRMACOES[acao](escolha))}</span></div>`;
    setTimeout(fechar, 2400);
  };

  el.addEventListener('click', (e) => {
    if (el.classList.contains('compacto') && !e.target.closest('[data-t="fechar"]')) return expandir(el);

    const m = e.target.closest('[data-t-modelo]');
    if (m) { escolha = normalizar({ modelo: m.dataset.tModelo }, recomendado(t)); return desenhar(); }
    const f = e.target.closest('[data-t-esforco]');
    if (f) { escolha = { ...escolha, esforco: f.dataset.tEsforco }; return desenhar(); }

    const b = e.target.closest('[data-t]');
    if (!b || b.disabled) return;
    const acao = b.dataset.t;

    if (acao === 'fechar') return fechar();
    if (acao === 'mais') return el.classList.toggle('expandido'); // mostra o texto inteiro
    if (acao === 'abrir') { acoes.abrir(t.id); return fechar(); }
    if (acao === 'pr') { window.open(t.resultado.pr.url, '_blank', 'noreferrer'); return; }
    if (acao === 'classificar') {
      acoes.classificar(t.id, b.dataset.v);
      const [categoria, sub] = b.dataset.v.split(':');
      t = { ...t, categoria, sub };
      return desenhar();
    }
    if (acao === 'reprovar') { if (acoes.reprovar(t.id)) confirmar(acao); return; }
    if (acao === 'responder') {
      if (!completas(t)) return alert(FALTA_RESPONDER);
      return acoes.responder(t.id, respostas(t)).then(() => { limpar(t.id); confirmar(acao); }).catch(() => {});
    }
    if (acao === 'enviar') {
      const texto = textoDaResposta(t).trim();
      if (!texto) return alert('A resposta está vazia.');
      return acoes.enviar(t.id, texto, anexosDe(t.id)).then(() => {
        descartarRascunho(t.id); limparAnexos(t.id); confirmar(acao);
      }).catch(() => {});
    }
    // "Não é tarefa" / "Descartar": abre a mensagem opcional antes de confirmar.
    if (acao === 'descartar') { descartando = true; desenhar(); return el.querySelector('[data-rascunho^="descarte-"]')?.focus(); }
    if (acao === 'cancelar-descarte') { descartando = false; return desenhar(); }
    if (acao === 'confirmar-descarte') {
      const mensagem = rascunho(`descarte-${t.id}`).trim();
      return acoes.descartar(t.id, mensagem, anexosDe(`descarte-${t.id}`)).then(() => {
        descartarRascunho(`descarte-${t.id}`); limparAnexos(`descarte-${t.id}`); confirmar('descartar');
      }).catch(() => {});
    }
    if (acao === 'depois') return confirmar(acao);
    if (acao === 'repassar') {
      // Fluxo de sempre: pesquisa (se ainda não começou) e te mostra o rascunho.
      const status = tarefa(t.id)?.status || t.status;
      const feito = ['identificada', 'comigo'].includes(status) ? acoes.pesquisar(t.id) : null;
      return Promise.resolve(feito).then(() => confirmar(acao)).catch(() => {});
    }
    const feito = acao === 'aprovar' ? acoes.aprovar(t.id, escolha) : acoes[acao](t.id);
    Promise.resolve(feito).then(() => confirmar(acao)).catch(() => {});
  });

  // Não some sozinho: é uma decisão pendente. Só sai quando você age ou fecha.
  const pilha = document.querySelector('#toasts');
  pilha.querySelector(`.toast[data-tarefa="${t.id}"]`)?.remove(); // um aviso por tarefa
  pilha.prepend(el);
  // No máximo 3 na tela; os mais antigos continuam em "Precisa de mim".
  [...pilha.querySelectorAll('.toast:not(.fala)')].slice(3).forEach((x) => x.remove());
  expandir(el);
  pular();

  if (document.hidden) {
    naoVistas += 1;
    atualizarTitulo();
    if (podeNotificarSistema()) {
      const n = new Notification(`${TIPOS[tipo].rotulo}: ${t.titulo}`, {
        body: `${pessoa(t.pessoa).nome} · ${TIPOS[tipo].texto(t)}`,
        tag: `${t.id}-${tipo}`,
      });
      n.onclick = () => { window.focus(); n.close(); };
    }
  }
}
