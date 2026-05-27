function show(message, type, duration = 4500) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `
    <span>${message}</span>
    <button class="toast-close" aria-label="Cerrar">×</button>
  `;
  el.querySelector('.toast-close').addEventListener('click', () => remove(el));
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add('toast-visible'));
  setTimeout(() => remove(el), duration);
}

function remove(el) {
  el.classList.remove('toast-visible');
  el.addEventListener('transitionend', () => el.remove(), { once: true });
}

export const toast = {
  success: (msg, d) => show(msg, 'success', d),
  error:   (msg, d) => show(msg, 'error',   d ?? 6000),
  info:    (msg, d) => show(msg, 'info',    d),
  warning: (msg, d) => show(msg, 'warning', d),
};
