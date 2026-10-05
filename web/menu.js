import { CATEGORIAS } from './constantes.js';
import { ui, contar, agentesNomes, esc } from './estado.js';
import { icone } from './icones.js';

// Agrupadores da sidebar: fechados por padrão; o que você abrir fica lembrado.
const guardado = () => { try { return JSON.parse(localStorage.getItem('menu.abertos')) || []; } catch { return []; } };
const abertos = new Set(guardado());

export function alternarGrupo(id) {
  abertos.has(id) ? abertos.delete(id) : abertos.add(id);
  try { localStorage.setItem('menu.abertos', JSON.stringify([...abertos])); } catch { /* sem storage */ }
}

function item(visao, rotulo, ico, { destaque = false, recuo = false, mostrarContagem = true, vermelho = false } = {}) {
  const n = contar(visao);
  const ativo = ui.visao === visao;
  return `
    <button class="menu-item ${recuo ? 'recuo' : ''}" data-visao="${visao}" aria-current="${ativo}">
      ${ico ? icone(ico) : '<span class="ic-vazio"></span>'}
      <span>${rotulo}</span>
      ${mostrarContagem && n ? `<span class="contagem ${destaque ? 'forte' : ''} ${vermelho ? 'vermelha' : ''}">${n}</span>` : ''}
    </button>`;
}

// Um agrupador: cabeçalho que abre e fecha. Fechado, mostra o número que não pode passar despercebido.
function grupo(id, rotulo, visoes, conteudo, { alerta = 0 } = {}) {
  const aberto = abertos.has(id) || visoes.includes(ui.visao);
  return `
    <div class="menu-grupo ${aberto ? 'aberto' : ''}">
      <button class="menu-grupo-topo" data-menu-grupo="${id}" aria-expanded="${aberto}">
        <span class="menu-grupo-seta">${icone('seta', 14)}</span>
        <span>${rotulo}</span>
        ${!aberto && alerta ? `<span class="contagem forte">${alerta}</span>` : ''}
      </button>
      ${aberto ? `<div class="menu-grupo-itens">${conteudo}</div>` : ''}
    </div>`;
}

export function renderMenu(el) {
  const nomes = agentesNomes();
  const visoesAgentes = [];
  const categorias = CATEGORIAS.map((c) => {
    visoesAgentes.push(`cat:${c.id}`, ...(c.subs || []).map((s) => `cat:${c.id}:${s.id}`));
    const rotulo = nomes[c.id]?.apelido ? `${c.nome} <small class="menu-apelido">${esc(nomes[c.id].apelido)}</small>` : c.nome;
    const pai = item(`cat:${c.id}`, rotulo, c.id === 'duvida' ? 'interrogacao' : c.id);
    const filhos = (c.subs || []).map((s) => item(`cat:${c.id}:${s.id}`, s.nome, null, { recuo: true })).join('');
    return pai + filhos;
  }).join('') + (contar('sem-categoria') ? item('sem-categoria', 'Sem categoria', 'interrogacao', { destaque: true }) : '');
  if (contar('sem-categoria')) visoesAgentes.push('sem-categoria');

  el.innerHTML = `
    ${item('inicio', 'Início', 'inicio', { mostrarContagem: false })}
    ${item('tarefas', 'Tarefas', 'tarefas', { vermelho: true })}
    ${item('agentes', 'Agentes', 'agentes', { mostrarContagem: false })}

    ${grupo('status', 'Status', ['minhas', 'tudo', 'execucao', 'feitas', 'quadro'], `
      ${item('minhas', 'Precisa de mim', 'minhas', { destaque: true })}
      ${item('execucao', 'Em execução', 'execucao')}
      ${item('tudo', 'Todas', 'tudo')}
      ${item('feitas', 'Concluídas', 'feitas', { mostrarContagem: false })}
      ${item('quadro', 'Quadro antigo', 'quadro', { mostrarContagem: false })}`, { alerta: contar('minhas') })}

    ${grupo('agentes', 'Por agente', visoesAgentes, categorias, { alerta: contar('sem-categoria') })}

    <div class="menu-secao"></div>
    ${item('config', 'Configurações', 'config', { mostrarContagem: false })}`;
}
