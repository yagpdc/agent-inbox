// Texto da resposta que você está editando antes de enviar no Chat (por tarefa).
// Guardado fora do HTML pra não se perder quando a tela redesenha.

import { esc } from './estado.js';

const rascunhos = {};

export const textoDaResposta = (t) => rascunhos[t.id] ?? t.resposta?.texto ?? '';
export const descartarRascunho = (chave) => { delete rascunhos[chave]; };
export const rascunho = (chave) => rascunhos[chave] ?? '';

export const campoResposta = (t, classe) =>
  `<textarea class="${classe}" data-rascunho="${t.id}" rows="6">${esc(textoDaResposta(t))}</textarea>`;

// Ao descartar: mensagem opcional pra pessoa (o assistente escreve a versão final e manda).
export const campoDescarte = (t, classe, nome) =>
  `<textarea class="${classe}" data-rascunho="descarte-${t.id}" rows="2" placeholder="Mensagem pra ${esc(nome)} (opcional). Ex.: diga que não vou fazer agora porque tem prioridades na frente">${esc(rascunho(`descarte-${t.id}`))}</textarea>`;

// ---------- anexos: imagem ou arquivo junto de qualquer mensagem que vai pra alguém ----------
// Cada campo tem uma chave (a mesma do rascunho). O arquivo sobe na hora pra pasta de
// anexos da tarefa; a mensagem só leva os nomes quando você envia.

const anexos = {};  // chave -> [{ nome, original }]

export const anexosDe = (chave) => (anexos[chave] || []).map((a) => a.nome);
export const limparAnexos = (chave) => { delete anexos[chave]; };

const chips = (chave) => (anexos[chave] || []).map((a, i) => `
  <span class="anexo-chip">${esc(a.original)}<button type="button" data-tirar-anexo="${i}" aria-label="tirar">×</button></span>`).join('');

export const campoAnexos = (tid, chave) => `
  <div class="anexar" data-anexar="${esc(chave)}" data-tarefa="${esc(tid)}">
    <span class="anexar-lista">${chips(chave)}</span>
    <label class="anexar-botao">Anexar imagem ou arquivo<input type="file" multiple hidden /></label>
  </div>`;

async function subir(tid, chave, arquivo, caixa) {
  const r = await fetch(`/api/tarefas/${tid}/arquivo`, {
    method: 'POST',
    headers: { 'X-Nome': encodeURIComponent(arquivo.name || 'imagem.png') },
    body: arquivo,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return alert(d.erro || 'Não consegui anexar.');
  (anexos[chave] ||= []).push({ nome: d.nome, original: arquivo.name || 'imagem colada' });
  if (caixa) caixa.querySelector('.anexar-lista').innerHTML = chips(chave);
}

export function ligarRascunhos(raiz) {
  raiz.addEventListener('input', (e) => {
    const campo = e.target.closest('[data-rascunho]');
    if (campo) rascunhos[campo.dataset.rascunho] = campo.value;
  });
  raiz.addEventListener('change', (e) => {
    const caixa = e.target.closest('[data-anexar]');
    if (!caixa || e.target.type !== 'file') return;
    [...e.target.files].forEach((f) => subir(caixa.dataset.tarefa, caixa.dataset.anexar, f, caixa));
    e.target.value = '';
  });
  raiz.addEventListener('click', (e) => {
    const tirar = e.target.closest('[data-tirar-anexo]');
    if (!tirar) return;
    const caixa = tirar.closest('[data-anexar]');
    const [saiu] = anexos[caixa.dataset.anexar]?.splice(Number(tirar.dataset.tirarAnexo), 1) || [];
    caixa.querySelector('.anexar-lista').innerHTML = chips(caixa.dataset.anexar);
    if (saiu) {  // apaga do servidor também, pra não sobrar arquivo perdido
      fetch(`/api/tarefas/${caixa.dataset.tarefa}/tirar-arquivo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: saiu.nome }),
      }).catch(() => {});
    }
  });
  // Colar imagem (Ctrl+V) direto no campo de texto.
  raiz.addEventListener('paste', (e) => {
    const campo = e.target.closest('[data-rascunho], #conversa-campo');
    if (!campo) return;
    const arquivos = [...(e.clipboardData?.files || [])];
    if (!arquivos.length) return;
    const chave = campo.dataset.rascunho || campo.dataset.chaveAnexo;
    const caixa = raiz.querySelector(`[data-anexar="${chave}"]`);
    if (!caixa) return;
    e.preventDefault();
    arquivos.forEach((f) => subir(caixa.dataset.tarefa, chave, f, caixa));
  });
}
