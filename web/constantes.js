// Valores fixos do painel. Os dados vêm do servidor (/api/estado).

// Um por agente especialista (agentes/<tipo>/ no servidor).
export const CATEGORIAS = [
  { id: 'hub', nome: 'Hub' },
  { id: 'mapa', nome: 'Mapa', subs: [{ id: 'bug', nome: 'Bugs' }, { id: 'feature', nome: 'Features' }] },
  { id: 'camadas', nome: 'Camadas personalizadas' },
  { id: 'reativacao', nome: 'Reativação' },
  { id: 'site', nome: 'Site' },
  { id: 'duvida', nome: 'Dúvidas' },
];

export const STATUS = {
  identificada: 'Na fila pra começar',
  comigo: 'Com você',
  triagem: 'Planejando',
  pergunta: 'Aguardando sua resposta',
  resposta: 'Resposta pronta',
  aprovacao: 'Plano pronto',
  execucao: 'Em execução',
  revisao: 'Pronto pra deploy',
  feito: 'Concluída',
};
