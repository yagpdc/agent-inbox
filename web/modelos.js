// Quem faz o quê. Triagem e plano são fixos (baratos); a execução você escolhe na aprovação.
// Tudo roda pelo `claude.cmd` (limite do plano Max), com --model e --effort.

export const MODELOS = [
  { id: 'claude-haiku-4-5', alias: 'haiku', nome: 'Haiku 4.5', temEsforco: false, dica: 'Mais barato. Bom pra tarefa sem código ou bem mecânica. Não aceita ajuste de esforço.' },
  { id: 'claude-sonnet-5', alias: 'sonnet', nome: 'Sonnet 5', temEsforco: true, dica: 'Equilíbrio. Serve pra maioria das mudanças de código.' },
  { id: 'claude-opus-5', alias: 'opus', nome: 'Opus 5', temEsforco: true, dica: 'Mais caro. Pra mudança sensível ou que mexe em várias partes.' },
];

export const ESFORCOS = [
  { id: 'low', nome: 'Baixo' },
  { id: 'medium', nome: 'Médio' },
  { id: 'high', nome: 'Alto' },
  { id: 'xhigh', nome: 'Muito alto' },
  { id: 'max', nome: 'Máximo' },
];

const modelo = (id) => MODELOS.find((m) => m.id === id);

export const FIXOS = {
  triagem: { modelo: MODELOS[0], esforco: null }, // é tarefa? categoria? saudação? (várias mensagens numa sessão só)
  plano: { modelo: MODELOS[2], esforco: 'high' }, // lê o código e escreve o plano (só leitura)
};

export const nomeModelo = (id) => modelo(id)?.nome || id;
export const nomeEsforco = (id) => ESFORCOS.find((e) => e.id === id)?.nome || id;
export const aceitaEsforco = (id) => !!modelo(id)?.temEsforco;

export function descricaoExecucao(m, e) {
  return aceitaEsforco(m) && e ? `${nomeModelo(m)} · esforço ${nomeEsforco(e).toLowerCase()}` : nomeModelo(m);
}

// Quem pensa é o plano (Opus). A execução segue o plano, então Sonnet dá conta:
// sem arquivo e risco baixo -> Haiku | risco baixo -> Sonnet, médio | resto -> Sonnet, alto.
export function recomendado(t) {
  const p = t.plano;
  if (!p) return { modelo: MODELOS[1].id, esforco: 'medium' };
  if (p.risco === 'baixo' && !p.arquivos.length) return { modelo: MODELOS[0].id, esforco: null };
  if (p.risco === 'baixo') return { modelo: MODELOS[1].id, esforco: 'medium' };
  return { modelo: MODELOS[1].id, esforco: 'high' };
}

// Escolha atual -> escolha válida (troca de modelo pode exigir esforço padrão).
export function normalizar(escolha, sugestao) {
  if (!aceitaEsforco(escolha.modelo)) return { modelo: escolha.modelo, esforco: null };
  const esforco = escolha.esforco || (sugestao.modelo === escolha.modelo && sugestao.esforco) || 'high';
  return { modelo: escolha.modelo, esforco };
}

// Seletores em pílulas. `prefixo` diferencia o aviso ("t") da tela de leitura ("doc").
export function seletores(prefixo, escolha, sugestao) {
  const pilulas = (lista, atual, sugerido, attr, desligado = false) =>
    lista.map((x) => `
      <button class="modelo" data-${prefixo}-${attr}="${x.id}" aria-pressed="${x.id === atual}" ${desligado ? 'disabled' : ''} ${x.dica ? `title="${x.dica}"` : ''}>
        ${x.nome}${x.id === sugerido ? '<small>sugerido</small>' : ''}
      </button>`).join('');

  const semEsforco = !aceitaEsforco(escolha.modelo);
  return `
    <div class="escolha">
      <span>Executar com</span>
      <div>${pilulas(MODELOS, escolha.modelo, sugestao.modelo, 'modelo')}</div>
    </div>
    <div class="escolha">
      <span>Esforço</span>
      <div>
        ${pilulas(ESFORCOS, escolha.esforco, sugestao.modelo === escolha.modelo ? sugestao.esforco : null, 'esforco', semEsforco)}
      </div>
    </div>`;
}
