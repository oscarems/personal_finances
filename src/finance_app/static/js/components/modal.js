import { sanitize } from '../utils.js';

let stack = [];

export function openModal({ title, content, onSubmit, submitLabel = 'Guardar', size = 'md', onClose, keepOpen = false }) {
  const sizes = { sm: '420px', md: '560px', lg: '740px', xl: '960px' };
  const container = document.getElementById('modal-container');
  const wrap = document.createElement('div');

  wrap.innerHTML = `
    <div class="modal-overlay">
      <div class="modal" style="max-width:${sizes[size] ?? sizes.md}">
        <div class="modal-header">
          <h3 class="modal-title">${sanitize(title)}</h3>
          <button class="modal-close" aria-label="Cerrar">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div class="modal-body"></div>
        ${onSubmit ? `
          <div class="modal-footer">
            <button class="btn btn-secondary" data-cancel>Cancelar</button>
            <button class="btn btn-primary" data-submit>${sanitize(submitLabel)}</button>
          </div>
        ` : ''}
      </div>
    </div>
  `;

  const body = wrap.querySelector('.modal-body');
  if (typeof content === 'string') {
    body.innerHTML = content;
  } else if (content instanceof Node) {
    body.appendChild(content);
  }

  container.appendChild(wrap);

  function close() {
    wrap.remove();
    stack = stack.filter(m => m !== modal);
    onClose?.();
  }

  function showError(msg) {
    let errEl = body.querySelector('.modal-error');
    if (!errEl) {
      errEl = document.createElement('div');
      errEl.className = 'modal-error';
      body.prepend(errEl);
    }
    errEl.textContent = msg;
  }

  wrap.querySelector('.modal-close').addEventListener('click', close);
  wrap.querySelector('.modal-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) close();
  });
  wrap.querySelector('[data-cancel]')?.addEventListener('click', close);

  const submitBtn = wrap.querySelector('[data-submit]');
  submitBtn?.addEventListener('click', async () => {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando…';
    try {
      await onSubmit(body);
      if (!keepOpen) {
        close();
      } else {
        submitBtn.disabled = false;
        submitBtn.textContent = submitLabel;
      }
    } catch (err) {
      submitBtn.disabled = false;
      submitBtn.textContent = submitLabel;
      showError(err.message);
    }
  });

  const modal = { close, body, showError };
  stack.push(modal);
  return modal;
}

export function closeTopModal() {
  stack[stack.length - 1]?.close();
}
