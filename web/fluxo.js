// As decisões do fluxo, usadas pelos avisos e pela tela da tarefa.
// Cada etapa só começa com o seu OK: plano -> execução -> deploy.

import { ui, set } from './estado.js';
import { decidir } from './api.js';
import { falar } from './pet.js';

// Confirmação visível pras ações que disparam algo demorado.
const CONFIRMA = {
  planejar: (id) => `${id}: montando o plano.`,
  fazer: (id) => `${id}: vou planejar e executar. Te chamo quando der pra ver rodando.`,
  pesquisar: (id) => `${id}: pesquisando pra responder.`,
  aprovar: (id) => `${id}: execução iniciada.`,
  deploy: (id) => `${id}: deploy iniciado. Te aviso quando terminar.`,
  enviar: (id) => `${id}: resposta enviada no Chat.`,
  devolver: (id) => `${id}: ajuste pedido, o Claude está continuando.`,
  descartar: (id, corpo) => (corpo?.mensagem ? `${id}: descartada. Respondendo a pessoa.` : `${id}: descartada.`),
  'assumir-conversa': (id) => `${id}: conversa assumida. Daqui pra frente eu respondo e te chamo se algo for estranho.`,
  'soltar-conversa': (id) => `${id}: voltei a te repassar essa conversa.`,
  'ver-local': (id) => `${id}: subindo o servidor local, a aba abre em alguns segundos.`,
};

function tentar(id, acao, corpo) {
  return decidir(id, acao, corpo)
    .then((t) => {
      if (CONFIRMA[acao]) falar(CONFIRMA[acao](id, corpo));
      return t;
    })
    .catch((e) => {
      const semServidor = e instanceof TypeError; // fetch falhou: servidor fora do ar ou reiniciando
      falar(semServidor ? 'Não consegui falar com o servidor (pode estar reiniciando). Tente de novo em alguns segundos.' : e.message);
      throw e;
    });
}

export const acoes = {
  abrir(id) {
    set({ visao: ['inicio', 'config'].includes(ui.visao) ? 'minhas' : ui.visao, selecionada: id });
  },
  classificar: (id, valor) => tentar(id, 'classificar', { valor }),
  planejar: (id) => tentar(id, 'planejar'),
  fazer: (id) => tentar(id, 'fazer'),
  pesquisar: (id) => tentar(id, 'pesquisar'),
  enviar: (id, texto, arquivos = []) => tentar(id, 'enviar', { texto, arquivos }),
  assumir: (id) => tentar(id, 'assumir'),
  aprovar: (id, { modelo, esforco }) => tentar(id, 'aprovar', { modelo, esforco }),
  deploy: (id, corpo = {}) => tentar(id, 'deploy', corpo),
  descartar: (id, mensagem = '', arquivos = []) => tentar(id, 'descartar', { mensagem, arquivos }),
  falar: (id, texto, arquivos = []) => tentar(id, 'falar', { texto, arquivos }),
  tirarArquivo: (id, nome) => tentar(id, 'tirar-arquivo', { nome }),
  concluir: (id, corpo = {}) => tentar(id, 'concluir', corpo),
  parar: (id) => tentar(id, 'parar'),
  reabrir: (id) => tentar(id, 'reabrir'),
  devolver: (id, ajuste) => tentar(id, 'devolver', { ajuste }),
  finalizar: (id, corpo = {}) => tentar(id, 'finalizar', corpo),
  'assumir-conversa': (id) => tentar(id, 'assumir-conversa'),
  'soltar-conversa': (id) => tentar(id, 'soltar-conversa'),
  terminal: (id) => tentar(id, 'terminal'),
  'ver-local': (id) => tentar(id, 'ver-local'),
  responder: (id, respostas) => tentar(id, 'responder', { respostas }),

  // Devolve true se reprovou (dá pra cancelar o prompt). Reprovar = refazer o plano.
  reprovar(id) {
    const motivo = prompt('Motivo:');
    if (motivo === null) return false;
    tentar(id, 'reprovar', { motivo }).catch(() => {});
    return true;
  },
};
