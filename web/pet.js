// O bichinho do Claude no canto da tela. Pisca, pula quando chega coisa nova
// e fala com você por balões (que são as notificações).

const COR = '#d97757';

// Pixel art 14x10: corpo, bracinhos, olhos e 4 perninhas.
const SVG = `
<svg viewBox="0 0 14 10" shape-rendering="crispEdges" aria-hidden="true">
  <rect x="2" y="0" width="10" height="7" fill="${COR}"/>
  <rect x="0" y="3" width="2" height="2" fill="${COR}"/>
  <rect x="12" y="3" width="2" height="2" fill="${COR}"/>
  <g class="olhos" fill="#1d2233">
    <rect x="4" y="2" width="1" height="2"/>
    <rect x="9" y="2" width="1" height="2"/>
  </g>
  <g fill="${COR}">
    <rect x="3" y="7" width="1" height="3"/>
    <rect x="5" y="7" width="1" height="3"/>
    <rect x="8" y="7" width="1" height="3"/>
    <rect x="10" y="7" width="1" height="3"/>
  </g>
</svg>`;

export const PET_SVG = SVG;

let el;
let aoClicarPet = () => {};

export function montarPet(raiz, { aoClicar }) {
  aoClicarPet = aoClicar;
  raiz.innerHTML = `<button class="pet" title="Oi! Clica em mim">${SVG}</button>`;
  el = raiz.querySelector('.pet');
  el.addEventListener('click', () => aoClicarPet(el));
}

export function pular() {
  el.classList.remove('pulando');
  void el.offsetWidth; // reinicia a animação
  el.classList.add('pulando');
}

// Fala sem vir de uma tarefa (ex.: resumo ao clicar no pet).
export function falar(texto) {
  const b = document.createElement('div');
  b.className = 'toast fala';
  b.textContent = texto;
  document.querySelector('#pet-baloes').prepend(b);  // o que o pet diz fica com o pet
  pular();
  setTimeout(() => { b.classList.add('saindo'); setTimeout(() => b.remove(), 250); }, 6000);
}
