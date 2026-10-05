// Painel de leitura de uma tarefa: pedido, plano em texto corrido e a decisão.

import { CATEGORIAS, STATUS } from './constantes.js';
import { ui, tarefas, set, esc, faz, pessoa, config, conversaAssumida } from './estado.js';
import { acoes } from './fluxo.js';
import { nomeCategoria, avatar } from './lista.js';
import { icone } from './icones.js';
import { recomendado, seletores, normalizar, descricaoExecucao } from './modelos.js';
import { renderPerguntas, respostas, completas, limpar, FALTA_RESPONDER } from './perguntas.js';
import { campoResposta, campoDescarte, campoAnexos, anexosDe, limparAnexos, textoDaResposta, descartarRascunho, rascunho } from './rascunhos.js';

const origens = {}; // tarefa -> mensagens exatas que a pessoa mandou (buscadas uma vez)

// O que a pessoa escreveu no Chat, do jeito que ela escreveu, antes de qualquer resumo.
function mensagemOriginal(t) {
  const lista = t.origem || origens[t.id];
  if (lista === undefined) {
    origens[t.id] = null;
    fetch(`/api/tarefas/${t.id}/mensagens`).then((r) => r.json())
      .then((d) => { origens[t.id] = d.mensagens || []; set({}); }).catch(() => {});
    return '';
  }
  if (!lista || !lista.length) return '';
  const hora = (q) => new Date(q).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  return `
    <section class="doc-secao">
      <h3>O que ${esc(pessoa(t.pessoa).nome.split(' ')[0])} mandou no Chat</h3>
      <div class="msgs-originais">${lista.map((m) => `
        <div class="msg-original"><time>${esc(hora(m.quando))}</time><p>${esc(m.texto)}</p></div>`).join('')}
      </div>
    </section>`;
}

const descartando = new Set(); // tarefas com o campo de mensagem do descarte aberto
const fechando = {};             // tarefa -> ação que está fechando (deploy, concluir, finalizar)
const comMensagem = new Set();   // tarefas com o campo "mensagem pra pessoa" aberto no modal

// Deploy do hub tem duas etapas: a mensagem pra pessoa só faz sentido no fim ("Subir pra main").
const fechaAqui = (t, acao) => !!t.espaco && (acao !== 'deploy' || t.plano?.repo !== 'hub-driva'
  || t.resultado?.deploy?.etapa === 'homolog');

const textoDoAjuste = (tid) => rascunho(`ajuste-${tid}`);

const FINALIZEI = ['finalizar', 'Finalizei'];

const BOTOES = {
  identificada: [['fazer', 'Pode fazer', 'primario'], ['planejar', 'Só o plano'], FINALIZEI, ['descartar', 'Não é tarefa', 'perigo']],
  comigo: [['finalizar', 'Finalizei', 'primario'], ['fazer', 'Pode fazer'], ['planejar', 'Só o plano'], ['descartar', 'Não é tarefa', 'perigo']],
  triagem: [FINALIZEI],
  pergunta: [['responder', 'Responder', 'primario'], FINALIZEI],
  resposta: [['enviar', 'Enviar no Chat', 'primario'], FINALIZEI, ['descartar', 'Descartar', 'perigo']],
  aprovacao: [['aprovar', 'Executar', 'primario'], FINALIZEI, ['reprovar', 'Reprovar e refazer', 'perigo']],
  execucao: [['abrir-sessao', 'Abrir sessão no terminal'], FINALIZEI, ['parar', 'Parar', 'perigo']],
  revisao: [['deploy', 'Fazer deploy', 'primario'], ['ver-local', 'Ver rodando local'], ['concluir', 'Concluir sem deploy'], FINALIZEI, ['ajustar', 'Pedir ajuste', 'perigo']],
  feito: [['reabrir', 'Reabrir']],
};

const BOTOES_DUVIDA = {
  identificada: [['assumir-conversa', 'Assumir a conversa', 'primario'], ['pesquisar', 'Pesquisar e me mostrar'], FINALIZEI, ['descartar', 'Não é tarefa', 'perigo']],
  comigo: [['finalizar', 'Finalizei', 'primario'], ['pesquisar', 'Pesquisar e responder'], ['descartar', 'Não é tarefa', 'perigo']],
};

const urlLocal = (t) => Object.values(config().devLocal || {}).find((i) => i?.tarefa === t.id)?.url;

const naHomolog = (t) => t.resultado?.deploy?.etapa === 'homolog';
const comPr = (t) => t.resultado?.deploy?.tipo === 'pr';
const botoes = (t) => ((t.tipo === 'duvida' && BOTOES_DUVIDA[t.status]) || BOTOES[t.status] || [])
  .filter(([a]) => !(naHomolog(t) && a === 'ver-local'))
  .filter(([a]) => !(a === 'assumir-conversa' && (!t.espaco || conversaAssumida(t))))
  .map((b) => (naHomolog(t) && b[0] === 'deploy' ? ['deploy', 'Subir pra main', b[2]] : b))
  .map((b) => (t.resultado?.deploy?.tipo === 'entrega' && b[0] === 'deploy' ? ['deploy', 'Enviar pra pessoa', b[2]] : b))
  .filter(([a]) => !(t.resultado?.deploy?.tipo === 'entrega' && a === 'ver-local'))
  .filter(([a]) => !(comPr(t) && a === 'ver-local'))
  .map((b) => (comPr(t) && b[0] === 'deploy' ? ['deploy', t.resultado.pr ? 'Fazer merge' : 'Abrir o PR de novo', b[2]] : b));

function classificador(t, aberto) {
  if (t.categoria && !aberto) return '';
  const opcoes = CATEGORIAS.flatMap((c) =>
    c.subs ? c.subs.map((s) => [`${c.id}:${s.id}`, `${c.nome} · ${s.nome}`]) : [[c.id, c.nome]],
  );
  return `
    <div class="classificar">
      <p>Categoria</p>
      <div class="opcoes">
        ${opcoes.map(([v, n]) => `<button class="opcao" data-classificar="${v}" aria-pressed="${[t.categoria, t.sub].filter(Boolean).join(':') === v}">${n}</button>`).join('')}
      </div>
    </div>`;
}

function plano(t) {
  if (!t.plano) {
    return `
      <section class="doc-secao">
        <h3>Plano</h3>
        <p class="apagado">Sem plano ainda.</p>
      </section>`;
  }
  const p = t.plano;
  return `
    <section class="doc-secao">
      <h3>Plano</h3>
      <p>${esc(p.resumo)}</p>
      ${p.passos.length ? `<h4>Como vou fazer</h4><ol>${p.passos.map((x) => `<li>${esc(x)}</li>`).join('')}</ol>` : ''}
      ${p.avisos.length ? `<h4>Pontos de atenção</h4>${p.avisos.map((a) => `<p class="atencao">${icone('aviso', 16)}<span>${esc(a)}</span></p>`).join('')}` : ''}
      ${p.arquivos.length ? `<h4>Arquivos que mudam</h4><ul class="arquivos">${p.arquivos.map((a) => `<li><code>${esc(a)}</code></li>`).join('')}</ul>` : ''}
      <p class="rodape-plano">Risco ${esc(p.risco)} · cerca de ${esc(p.estimativa)}</p>
    </section>`;
}

function execucao(t) {
  if (!t.execucao) return '';
  const e = t.execucao;
  return `
    <section class="doc-secao">
      <h3>Execução</h3>
      <p>${esc(e.passo)}. Começou há ${faz(e.desde)}.</p>
      <div class="progresso"><i style="width:${Math.round(e.progresso * 100)}%"></i></div>
      <p class="apagado">${e.modelo ? `${esc(descricaoExecucao(e.modelo, e.esforco))} · ` : ''}sessão <code>${esc(e.sessao || 'iniciando')}</code>
        ${urlLocal(t) ? ` · <a class="link" href="${urlLocal(t)}" target="inbox-local-${new URL(urlLocal(t)).port}">Ver em ${urlLocal(t).replace('http://', '')}</a>` : ''}</p>
    </section>`;
}

const MARCOS = { na_fila: 'Na fila', executando: 'Começamos', pronto: 'Terminamos', concluido: 'Concluído', no_ar: 'No ar' };

// A ficha que quem pediu confirmou com o orquestrador, e o que ela já ouviu do andamento.
function ficha(t) {
  if (!t.ficha) return '';
  const f = t.ficha;
  const campos = Object.entries(f.campos || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  const ditos = Object.entries(t.marcos || {}).filter(([, m]) => m.texto)
    .sort(([, a], [, b]) => (a.em || '').localeCompare(b.em || ''));
  return `
    <section class="doc-secao">
      <h3>Ficha confirmada por ${esc(pessoa(t.pessoa).nome.split(' ')[0])}</h3>
      <p>${esc(f.pedido)}</p>
      <dl class="ficha">
        ${f.workspace?.nome ? `<dt>Workspace</dt><dd>${esc(f.workspace.nome)}</dd>` : ''}
        <dt>Pronto quando</dt><dd>${esc(f.criterio || '-')}</dd>
        ${campos}
      </dl>
      ${ditos.length ? `<h4>O que ${esc(pessoa(t.pessoa).nome.split(' ')[0])} já ouviu</h4>
        <ul class="marcos">${ditos.map(([k, m]) => `<li><b>${esc(MARCOS[k] || (m.pergunta ? 'Pergunta' : k))}</b>
          <span>${esc(m.texto)}</span>${m.enviado === false ? '<i class="apagado"> (esperando você sair da conversa)</i>' : ''}</li>`).join('')}</ul>` : ''}
    </section>`;
}

function resultado(t) {
  if (!t.resultado) return '';
  const r = t.resultado;
  return `
    <section class="doc-secao">
      <h3>Resultado</h3>
      ${r.pr ? `<p class="pr-linha"><a class="btn" href="${esc(r.pr.url)}" target="_blank" rel="noreferrer">Abrir PR #${r.pr.numero} ${icone('externo', 14)}</a>
        <span class="apagado">contra ${esc(r.pr.base)}${r.pr.mergeado ? ' · mergeado' : r.pr.fechado ? ' · fechado sem merge' : ''}</span></p>` : ''}
      <p>${esc(r.resumo)}</p>
      ${r.deploy?.tipo === 'entrega' ? `<h4>Arquivos pra enviar</h4>
        <ul class="arquivos">${r.deploy.passos.map((n) =>
          `<li><a class="link" href="/entregas/${encodeURIComponent(t.id)}/${encodeURIComponent(n)}" target="_blank">${esc(n)}</a></li>`).join('')}</ul>` : ''}
      ${r.ondeTestar ? `<h4>Onde testar</h4><p>${esc(r.ondeTestar)}</p>` : ''}
      ${r.vaiJunto?.length ? `<h4>Vai junto (a branch de origem tinha a mais que a main)</h4>
        <ul class="arquivos">${r.vaiJunto.map((c) => `<li><code>${esc(c)}</code></li>`).join('')}</ul>` : ''}
      ${r.camadasTeste?.length ? `<h4>No workspace de teste</h4>
        <ul class="arquivos">${r.camadasTeste.map((c) => `<li>${esc(c.nome)} · ${c.feicoes} feições</li>`).join('')}</ul>` : ''}
      ${r.camadasCliente?.length ? `<h4>No workspace do cliente</h4>
        <ul class="arquivos">${r.camadasCliente.map((c) => `<li>${esc(c.nome)} · ${c.feicoes} feições</li>`).join('')}</ul>` : ''}
      ${r.alcance ? `<h4>Por onde o usuário chega</h4><p class="apagado">${esc(r.alcance)}</p>` : ''}
      ${t.execucao?.revisao?.length ? `<h4>A revisão automática tinha apontado</h4>
        <ul class="arquivos">${t.execucao.revisao.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}
      ${r.commits?.length ? `<ul class="arquivos">${r.commits.map((c) => `<li><code>${esc(c)}</code></li>`).join('')}</ul>` : ''}
      ${r.deploy ? `<h4>Deploy</h4><p>${esc(r.deploy.resumo)}</p>` : ''}
      ${r.deploy?.passos.length ? `<pre class="cmd">${r.deploy.passos.map(esc).join('\n')}</pre>` : ''}
    </section>`;
}

let reclassificando = false;
const ajustando = new Set(); // tarefas com a caixa de "Pedir ajuste" aberta
const escolhas = {}; // { [id]: { modelo, esforco } } até aprovar

export function renderLeitura(el) {
  const t = tarefas().find((x) => x.id === ui.selecionada);
  if (!t) return false;

  const p = pessoa(t.pessoa);
  el.innerHTML = `
    <div class="doc-barra">
      <button class="migalha" data-acao="reclassificar" title="Mudar categoria">${esc(nomeCategoria(t))}</button>
      <span class="doc-id">${t.id}</span>
      <button class="icone-btn" data-acao="fechar" title="Fechar">${icone('fechar')}</button>
    </div>

    <article class="doc">
      <h1>${esc(t.titulo)}</h1>
      <div class="doc-meta">
        ${avatar(t.pessoa)}
        <span><b>${esc(p.nome)}</b> · há ${faz(t.criadaEm)}${t.prioridade === 'P0' ? ' · <b class="urgente">Urgente</b>' : ''}</span>
        <a class="link" href="${t.chatUrl}" target="_blank" rel="noreferrer">Abrir no Google Chat ${icone('externo', 14)}</a>
      </div>

      ${classificador(t, reclassificando)}

      <p class="situacao"><i class="ponto s-${t.status}"></i><b>${STATUS[t.status]}</b>${t.esperando ? ` · ${esc(t.esperando)}` : ''}</p>
      ${conversaAssumida(t) ? `
        <p class="assumida">O assistente está tocando a conversa com ${esc(p.nome.split(' ')[0])}: pesquisa, responde e te chama se algo for estranho.
          <button class="link" data-acao="soltar-conversa">Voltar a me repassar</button></p>` : ''}

      ${mensagemOriginal(t)}
      ${ficha(t)}
      <section class="doc-secao">
        <h3>${t.ficha ? 'Pedido nas palavras dela' : 'Pedido'}</h3>
        <blockquote>${esc(t.pedido)}</blockquote>
        ${(t.anexos || []).length ? `<div class="anexos">${t.anexos.map((n) => {
          const url = `/anexos/${encodeURIComponent(t.id)}/${encodeURIComponent(n)}`;
          const tirar = n.startsWith('voce-')
            ? `<button class="anexo-tirar" data-tirar-arquivo="${esc(n)}" title="Tirar este anexo">×</button>` : '';
          return /\.(png|jpe?g|gif|webp)$/i.test(n)
            ? `<span class="anexo-item"><a href="${url}" target="_blank" rel="noreferrer"><img src="${url}" alt="" /></a>${tirar}</span>`
            : `<span class="anexo-item"><a class="link" href="${url}" target="_blank" rel="noreferrer">${esc(n)}</a>${tirar}</span>`;
        }).join('')}</div>` : ''}
      </section>

      ${t.status === 'pergunta' ? `
        <section class="doc-secao">
          <h3>Perguntas ${t.pergunta?.etapa === 'plano' ? 'sobre o plano' : 'durante a execução'}</h3>
          <div class="perguntas-doc">${renderPerguntas(t)}</div>
        </section>` : ''}
      ${t.status === 'resposta' ? `
        <section class="doc-secao">
          <h3>Resposta</h3>
          ${campoResposta(t, 'resposta-doc')}
          ${campoAnexos(t.id, t.id)}
          ${t.resposta?.fontes?.length ? `<h4>Fontes</h4><ul class="arquivos">${t.resposta.fontes.map((f) => `<li><code>${esc(f)}</code></li>`).join('')}</ul>` : ''}
        </section>` : ''}
      ${t.resposta?.enviada ? `
        <section class="doc-secao">
          <h3>Resposta enviada</h3>
          <blockquote>${esc(t.resposta.texto)}</blockquote>
        </section>` : ''}
      ${t.status === 'revisao' && ajustando.has(t.id) ? `
        <section class="doc-secao">
          <h3>O que ajustar</h3>
          <textarea class="resposta-doc" data-rascunho="ajuste-${t.id}" rows="5" placeholder="Ex.: o dropdown ficou alto demais; deixe com a mesma altura dos outros pills e sem sombra">${esc(textoDoAjuste(t.id))}</textarea>
          <div class="acoes-inline">
            <button class="btn primario" data-acao="enviar-ajuste">Enviar ajuste</button>
            <button class="btn" data-acao="cancelar-ajuste">Cancelar</button>
          </div>
        </section>` : ''}
      ${fechando[t.id] ? modalFechar(t) : ''}
      ${descartando.has(t.id) ? `
        <section class="doc-secao">
          <h3>Descartar</h3>
          ${t.espaco ? campoDescarte(t, 'resposta-doc', pessoa(t.pessoa).nome.split(' ')[0]) + campoAnexos(t.id, `descarte-${t.id}`) : ''}
          <div class="acoes-inline">
            <button class="btn perigo" data-acao="confirmar-descarte">Descartar</button>
            <button class="btn" data-acao="cancelar-descarte">Cancelar</button>
          </div>
        </section>` : ''}
      ${execucao(t)}
      ${t.tipo === 'duvida' ? '' : plano(t)}
      ${resultado(t)}
    </article>

    <div class="doc-acoes">
      ${t.status === 'aprovacao' ? `
        <div class="doc-escolhas">${seletores('doc', escolhas[t.id] || recomendado(t), recomendado(t))}</div>` : ''}
      ${botoes(t).map(([a, r, c = '']) => {
        const travado = a === 'aprovar' && !t.categoria;
        return `<button class="btn ${c}" data-acao="${a}" ${travado ? 'disabled title="Classifique primeiro"' : ''}>${r}</button>`;
      }).join('')}
    </div>`;
  return true;
}

// Confirmar o fim da tarefa num modal: Cancelar ou Confirmar. Mensagem pra pessoa é opcional e fica escondida.
function modalFechar(t) {
  const qual = fechando[t.id];
  const nome = esc(pessoa(t.pessoa).nome.split(' ')[0]);
  const titulo = naHomolog(t) && qual === 'deploy' ? 'Subir pra main?'
    : t.resultado?.deploy?.tipo === 'entrega' && qual === 'deploy' ? `Enviar os arquivos pra ${nome}?`
      : comPr(t) && qual === 'deploy' ? `Fazer merge do PR #${t.resultado.pr?.numero || ''}?`
        : { deploy: 'Fazer deploy?', concluir: 'Concluir sem deploy?', finalizar: 'Marcar como finalizada?' }[qual];
  const mensagem = comMensagem.has(t.id);
  return `
    <div class="modal-fundo" data-acao="cancelar-fechar">
      <div class="modal" data-acao="modal" role="dialog" aria-modal="true">
        <h3>${titulo}</h3>
        <p class="apagado">${esc(t.id)} · ${esc(t.titulo)}</p>
        ${t.espaco ? `
          <label class="modal-chave">
            <span>Mandar mensagem pra ${nome}${qual === 'deploy' ? ' <small class="apagado">quando o deploy acabar</small>' : ''}</span>
            <span class="chave"><input type="checkbox" id="fechar-avisar" data-acao="fechar-mensagem" ${mensagem ? 'checked' : ''} /><span></span></span>
          </label>
          ${mensagem ? `
            <div class="modal-secao">
              <textarea class="resposta-doc" data-rascunho="fechar-${t.id}" rows="3"
                placeholder="O que dizer (opcional). Em branco, ele explica o que foi feito e como usar.">${esc(rascunho(`fechar-${t.id}`))}</textarea>
              ${campoAnexos(t.id, `fechar-${t.id}`)}
            </div>` : ''}` : ''}
        <div class="modal-acoes">
          <button class="btn" data-acao="cancelar-fechar">Cancelar</button>
          <button class="btn primario" data-acao="confirmar-fechar">Confirmar</button>
        </div>
      </div>
    </div>`;
}

export function classificar(valor, id = ui.selecionada) {
  reclassificando = false;
  acoes.classificar(id, valor);
}

export function escolher(id, patch) {
  const t = tarefas().find((x) => x.id === id);
  const atual = escolhas[id] || recomendado(t);
  escolhas[id] = patch.modelo ? normalizar({ modelo: patch.modelo }, recomendado(t)) : { ...atual, ...patch };
  set({});
}

export function agir(acao) {
  const id = ui.selecionada;
  const t = tarefas().find((x) => x.id === id);

  if (acao === 'fechar') return set({ selecionada: null });
  if (acao === 'reclassificar') { reclassificando = !reclassificando; return set({}); }
  if (acao === 'aprovar') return acoes.aprovar(id, escolhas[id] || recomendado(t));
  if (acao === 'ajustar') { ajustando.add(id); set({}); return document.querySelector('[data-rascunho^="ajuste-"]')?.focus(); }
  // Deploy final, concluir e finalizar: antes, pergunta o que dizer pra quem pediu.
  if (['deploy', 'concluir', 'finalizar'].includes(acao) && fechaAqui(t, acao)) {
    fechando[id] = acao; set({});
    return document.querySelector('.modal [data-acao="confirmar-fechar"]')?.focus();
  }
  if (acao === 'modal') return; // clique dentro do modal (fora dos botões) não fecha
  if (acao === 'fechar-mensagem') { // marcar "avisar" abre o campo da mensagem; desmarcar esconde
    comMensagem.has(id) ? comMensagem.delete(id) : comMensagem.add(id);
    set({});
    return document.querySelector('[data-rascunho^="fechar-"]')?.focus();
  }
  if (acao === 'cancelar-fechar') { delete fechando[id]; comMensagem.delete(id); return set({}); }
  if (acao === 'confirmar-fechar') {
    const qual = fechando[id];
    const corpo = { avisar: document.querySelector('#fechar-avisar')?.checked ?? false,
                    fechamento: rascunho(`fechar-${id}`).trim(), arquivos: anexosDe(`fechar-${id}`) };
    return acoes[qual](id, corpo).then(() => {
      delete fechando[id]; comMensagem.delete(id); descartarRascunho(`fechar-${id}`); limparAnexos(`fechar-${id}`); set({});
    }).catch(() => {});
  }
  if (acao === 'descartar') { descartando.add(id); set({}); return document.querySelector('[data-rascunho^="descarte-"]')?.focus(); }
  if (acao === 'cancelar-descarte') { descartando.delete(id); return set({}); }
  if (acao === 'confirmar-descarte') {
    const mensagem = rascunho(`descarte-${id}`).trim();
    return acoes.descartar(id, mensagem, anexosDe(`descarte-${id}`)).then(() => {
      descartando.delete(id); descartarRascunho(`descarte-${id}`); limparAnexos(`descarte-${id}`);
    }).catch(() => {});
  }
  if (acao === 'cancelar-ajuste') { ajustando.delete(id); return set({}); }
  if (acao === 'enviar-ajuste') {
    const ajuste = textoDoAjuste(id).trim();
    if (!ajuste) return alert('Escreva o que quer ajustar.');
    return acoes.devolver(id, ajuste).then(() => { ajustando.delete(id); descartarRascunho(`ajuste-${id}`); }).catch(() => {});
  }
  if (acao === 'enviar') {
    const texto = textoDaResposta(t).trim();
    if (!texto) return alert('A resposta está vazia.');
    acoes.enviar(id, texto, anexosDe(id));
    limparAnexos(id);
    return descartarRascunho(id);
  }
  if (acao === 'responder') {
    if (!completas(t)) return alert(FALTA_RESPONDER);
    acoes.responder(id, respostas(t));
    return limpar(id);
  }
  if (acao === 'abrir-sessao') return acoes.terminal(id);
  if (acoes[acao]) acoes[acao](id);
}
