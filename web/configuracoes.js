// Tela de configurações.

import { config, esc } from './estado.js';
import { salvarConfig } from './api.js';
import { pedirPermissao, podeNotificarSistema } from './notificacoes.js';

const chave = (id, ligada) => `
  <label class="chave">
    <input type="checkbox" id="${id}" ${ligada ? 'checked' : ''} />
    <span></span>
  </label>`;

const texto = (id, rotulo, valor) => `
  <label class="campo">
    <span>${rotulo}</span>
    <textarea id="${id}" rows="3">${esc(valor || '')}</textarea>
  </label>`;

export function renderConfiguracoes(el) {
  const s = config().respostaDm || {};
  el.innerHTML = `
    <div class="config">
      <h1 class="manchete">Configurações</h1>

      <section class="config-bloco">
        <div class="config-titulo">
          <h3>Responder DMs por mim</h3>
          ${chave('cfg-ativa', s.ativa)}
        </div>

        <div class="config-campos" ${s.ativa ? '' : 'data-off'}>
          <label class="campo">
            <span>Ficar quieto depois que eu respondo, por</span>
            <span class="minutos"><input type="number" id="cfg-inativa" min="1" max="1440" value="${s.inativaMin ?? 10}" /> minutos</span>
          </label>
          <p class="apagado">O orquestrador conversa em toda DM: monta o pedido com a pessoa, confirma com ela e
            manda pro agente certo; dúvida ele pesquisa e responde. Conversa que você responde fica sua até ficar parada.
            Desligado, ninguém fala por você e as conversas viram decisões suas.</p>
          ${texto('cfg-texto-pendente', 'Quando confere e o pedido ainda não está pronto', s.textoPendente)}
          ${texto('cfg-texto-confirmar', 'Quando precisa confirmar algo com você', s.textoConfirmar)}
        </div>
      </section>

      <section class="config-bloco">
        <div class="config-titulo">
          <h3>Modo celular: mandar as decisões e a conversa pro Google Chat</h3>
          ${chave('cfg-movel', config().movel?.ativo)}
        </div>
        <p class="apagado">Ligue quando sair do computador. Cada tarefa vira uma thread no espaço
          "Inbox Agent - Mobile": você responde com o número da opção, escreve livre pra orientar, ou
          manda <code>deploy</code> pra subir.</p>
      </section>

      <section class="config-bloco">
        <div class="config-titulo">
          <h3>Avisos do Windows quando a aba está em segundo plano</h3>
          <button class="btn" id="cfg-sino"></button>
        </div>
      </section>

      <section class="config-bloco">
        <h3>Modelos</h3>
        <p class="apagado">Cada agente tem os seus (o plano com Opus, a execução com Sonnet). Veja e mude na tela
          <button class="link" data-visao="agentes">Agentes</button>. O orquestrador conversa com Sonnet.</p>
      </section>

      <p class="salvo" id="cfg-salvo" hidden>Salvo</p>
    </div>`;

  const sino = el.querySelector('#cfg-sino');
  const mostrarSino = () => { sino.textContent = podeNotificarSistema() ? 'Ligados' : 'Ligar'; };
  mostrarSino();
  sino.addEventListener('click', async () => { await pedirPermissao(); mostrarSino(); });

  const salvo = el.querySelector('#cfg-salvo');
  let timer;
  const gravar = async (patch) => {
    config().respostaDm = await salvarConfig('respostaDm', patch);
    salvo.hidden = false;
    clearTimeout(timer);
    timer = setTimeout(() => { salvo.hidden = true; }, 1500);
  };
  const $ = (s) => el.querySelector(s);

  $('#cfg-ativa').addEventListener('change', (e) => {
    $('.config-campos').toggleAttribute('data-off', !e.target.checked);
    gravar({ ativa: e.target.checked });
  });
  $('#cfg-inativa').addEventListener('change', (e) => {
    const v = Math.min(1440, Math.max(1, Number(e.target.value) || 10));
    e.target.value = v;
    gravar({ inativaMin: v });
  });
  [['#cfg-texto-pendente', 'textoPendente'], ['#cfg-texto-confirmar', 'textoConfirmar']].forEach(([sel, campo]) => {
    $(sel).addEventListener('change', (e) => {
      const valor = e.target.value.trim();
      if (valor) gravar({ [campo]: valor });
    });
  });
  $('#cfg-movel').addEventListener('change', async (e) => {
    config().movel = await salvarConfig('movel', { ativo: e.target.checked });
    salvo.hidden = false;
    clearTimeout(timer);
    timer = setTimeout(() => { salvo.hidden = true; }, 1500);
  });
}
