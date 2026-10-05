import { ui, set, aoMudar, tarefas, precisaDeMim, config, daLista, jornada } from './estado.js';
import { conectar, salvarConfig } from './api.js';
import { renderMenu, alternarGrupo } from './menu.js';
import { renderLista } from './lista.js';
import { renderLeitura, agir, classificar, escolher } from './leitura.js';
import { renderInicio } from './inicio.js';
import { renderConfiguracoes } from './configuracoes.js';
import { renderQuadro, quadroOcupado } from './quadro.js';
import { acoes } from './fluxo.js';
import { icone } from './icones.js';
import { montarPet, falar, PET_SVG } from './pet.js';
import { avisar } from './notificacoes.js';
import { ligarPerguntas } from './perguntas.js';
import { ligarRascunhos } from './rascunhos.js';
import { menuDoPet, mostrarResposta } from './assistente.js';
import { renderColuna, ligarConversa, novaFala } from './coluna.js';
import { renderAgentes, cliqueAgentes } from './agentes.js';
import { renderTarefas, cliqueTarefas } from './tarefas.js';

const $ = (s) => document.querySelector(s);

function render() {
  if (quadroOcupado()) return; // não redesenha no meio de um arrastar
  const semLista = ['inicio', 'config', 'quadro', 'agentes', 'tarefas'].includes(ui.visao);
  $('#app').classList.toggle('sem-lista', semLista);
  $('#leitura').classList.toggle('modo-quadro', ['quadro', 'tarefas'].includes(ui.visao) && !ui.selecionada);

  renderMenu($('#menu'));
  if (!semLista) renderLista($('#lista'));

  const leitura = $('#leitura');
  if (ui.visao === 'quadro' && !ui.selecionada) {
    renderQuadro(leitura);
  } else if (ui.visao === 'tarefas' && !ui.selecionada) {
    renderTarefas(leitura);
  } else if (ui.visao === 'agentes') {
    renderAgentes(leitura);
  } else if (ui.visao === 'config') {
    // Só redesenha ao entrar, pra não perder o foco enquanto você digita.
    if (!leitura.querySelector('.config')) renderConfiguracoes(leitura);
  } else if ((ui.visao === 'inicio' && !ui.selecionada) || !renderLeitura(leitura)) {
    if (ui.visao === 'inicio') renderInicio(leitura);
    else leitura.innerHTML = '<p class="nada centro">Nenhuma tarefa selecionada.</p>';
  }

  renderColuna($('#coluna'));

  $('#movel').checked = !!config().movel?.ativo;
  desenharJornada();
  desenharExecucao();

  const n = tarefas().filter(precisaDeMim).length;
  $('#trilho-conta').textContent = n || '';
  const rodando = tarefas().filter((t) => t.status === 'execucao').length;
  $('#coluna-situacao').textContent = n || rodando
    ? [n && `${n} esperando você`, rodando && `${rodando} rodando`].filter(Boolean).join(' · ')
    : 'tudo em dia';
  document.title = n ? `Inbox Agent · ${n}` : 'Inbox Agent';

}

aoMudar(render);

document.addEventListener('click', (e) => {
  const coluna = e.target.closest('[data-coluna]');
  if (coluna) { recolherColuna(coluna.dataset.coluna === 'fechar'); return; }

  const grupoMenu = e.target.closest('[data-menu-grupo]');
  if (grupoMenu) { alternarGrupo(grupoMenu.dataset.menuGrupo); return set({}); }

  const visao = e.target.closest('[data-visao]');
  if (visao) {
    // Nas listas, a primeira tarefa já abre; início, quadro e configurações abrem vazios.
    const v = visao.dataset.visao;
    ui.visao = v;
    const primeira = ['inicio', 'config', 'quadro', 'agentes', 'tarefas'].includes(v) ? null : daLista()[0]?.id ?? null;
    return set({ visao: v, selecionada: primeira, agente: null });
  }

  if (ui.visao === 'agentes' && cliqueAgentes(e)) return;
  if (ui.visao === 'tarefas' && !ui.selecionada && cliqueTarefas(e)) return;

  const mod = e.target.closest('[data-doc-modelo]');
  if (mod) return escolher(ui.selecionada, { modelo: mod.dataset.docModelo });
  const esf = e.target.closest('[data-doc-esforco]');
  if (esf) return escolher(ui.selecionada, { esforco: esf.dataset.docEsforco });

  const cls = e.target.closest('[data-classificar]');
  if (cls) return classificar(cls.dataset.classificar);

  const tarefa = e.target.closest('[data-id]');
  if (tarefa) return set({ selecionada: tarefa.dataset.id });

  const tirarArquivo = e.target.closest('[data-tirar-arquivo]');
  if (tirarArquivo) {
    e.preventDefault();
    if (confirm('Tirar este anexo da tarefa?')) acoes.tirarArquivo(ui.selecionada, tirarArquivo.dataset.tirarArquivo);
    return;
  }

  const rodandoItem = e.target.closest('#rodando-agora [data-id]');
  if (rodandoItem) return set({ selecionada: rodandoItem.dataset.id });

  const acao = e.target.closest('[data-acao]');
  if (acao) return agir(acao.dataset.acao);
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && ui.selecionada) set({ selecionada: null });
});

$('#busca').addEventListener('input', (e) => set({ busca: e.target.value }));
$('#pessoa').addEventListener('change', (e) => set({ pessoa: e.target.value }));
$('#ic-busca').innerHTML = icone('busca', 16);
$('#movel').addEventListener('change', async (e) => {
  const ligar = e.target.checked;
  config().movel = await salvarConfig('movel', { ativo: ligar });
  falar(ligar ? 'Modo celular ligado: mando as decisões no Chat.' : 'Modo celular desligado.');
  set({});
});
$('#marca-pet').innerHTML = PET_SVG;

// Coluna da direita (Decisões + Conversa) recolhe pra direita e vira uma faixa com o número de decisões.
function recolherColuna(fechar) {
  $('#app').classList.toggle('coluna-fechada', fechar);
  try { localStorage.setItem('coluna.fechada', fechar ? '1' : ''); } catch { /* sem storage */ }
}
$('#coluna-fechar').innerHTML = icone('seta', 16);
$('#trilho-seta').innerHTML = icone('seta', 16);
try { recolherColuna(localStorage.getItem('coluna.fechada') === '1'); } catch { /* sem storage */ }

montarPet($('#coluna-pet'), { aoClicar: menuDoPet });
ligarConversa($('#coluna'));

conectar({
  aviso: (tipo, t) => avisar(tipo, t, acoes),
  fala: falar,
  conexao: (ok) => $('#app').classList.toggle('offline', !ok),
  vigia: mostrarVigia,
  devLocal: (d) => { config().devLocal = d; set({}); },
  falaTarefa: novaFala,
  petResposta: mostrarResposta,
  // Aba com nome fixo: o navegador reaproveita a mesma em vez de abrir outra.
  abrirAba: ({ url, nome }) => {
    if (!window.open(url, nome)) falar(`Abra ${url.replace('http://', '')} pelo link da tarefa (o navegador bloqueou a aba automática).`);
  },
});

ligarPerguntas($('#leitura'), () => set({}));
ligarRascunhos($('#leitura'));

// Horas trabalhadas: o servidor manda a cada minuto; entre uma e outra o painel
// só avança o relógio localmente, pra não ficar parado na tela.
let jornadaRecebida = { em: Date.now(), segundos: 0 };
function desenharJornada() {
  const j = jornada();
  if (!j) return;
  if (j !== jornadaRecebida.ref) jornadaRecebida = { ref: j, em: Date.now(), segundos: j.segundos };
  const segundos = jornadaRecebida.segundos + (Date.now() - jornadaRecebida.em) / 1000;
  const meta = (j.metaHoras || 8) * 3600;
  const h = Math.floor(segundos / 3600);
  const m = Math.floor((segundos % 3600) / 60);
  $('#jornada-tempo').textContent = `${h}h ${String(m).padStart(2, '0')}`;
  $('#jornada-barra').style.width = `${Math.min(100, (segundos / meta) * 100)}%`;
  $('#jornada').classList.toggle('completa', segundos >= meta);
  const falta = Math.max(0, meta - segundos);
  $('#jornada-meta').textContent = falta
    ? `de ${j.metaHoras || 8}h · faltam ${Math.floor(falta / 3600)}h ${String(Math.floor((falta % 3600) / 60)).padStart(2, '0')}`
    : `meta de ${j.metaHoras || 8}h batida`;
}
setInterval(desenharJornada, 30000);

// Agentes trabalhando / pausados. Pausado: só o orquestrador segue, criando tarefas.
function desenharExecucao() {
  const ligada = config().execucao?.ligada !== false;
  const presas = tarefas().filter((t) => (t.esperando || '').startsWith('Pausado')).length;
  const rodando = tarefas().filter((t) => ['triagem', 'execucao'].includes(t.status)).length;
  $('#execucao').classList.toggle('pausada', !ligada);
  $('#execucao').title = ligada
    ? (rodando ? `Executores ligados: ${rodando} em andamento` : 'Executores ligados')
    : (presas ? `Executores pausados: ${presas} esperando na fila` : 'Executores pausados: só o orquestrador conversando');
  $('#execucao-acao').textContent = ligada ? 'Pausar' : 'Ligar';
}
$('#execucao').addEventListener('click', async () => {
  const ligar = config().execucao?.ligada === false;
  config().execucao = await salvarConfig('execucao', { ligada: ligar });
  falar(ligar ? 'Agentes ligados: pegando o que ficou na fila.' : 'Agentes pausados. O orquestrador continua conversando e criando tarefas.');
  set({});
});

function mostrarVigia({ ok, erro }) {
  const el = $('.menu-rodape');
  el.dataset.estado = ok ? 'ok' : erro ? 'erro' : 'parado';
  el.title = erro || (ok ? 'Lendo o Chat' : 'Sem login do Google');
}

render();
aoMudar(() => { const v = config().vigia; if (v && !$('.menu-rodape').dataset.estado) mostrarVigia({ ok: !v.erro && !!v.ultimaLeitura, erro: v.erro }); });
