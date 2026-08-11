import { sanitize } from '../utils.js';

/** Full-page (or section) spinner. */
export function loadingState({ message = '' } = {}) {
  return `
    <div class="page-loading">
      ${message ? `<p class="text-soft text-sm mb-3">${sanitize(message)}</p>` : ''}
      <div class="spinner" aria-hidden="true"></div>
    </div>`;
}

/**
 * Error panel with retry button.
 * @param {{ message?: string, retryId?: string, title?: string|null }} opts
 */
export function errorState({ message = 'Error al cargar', retryId = 'btnPageRetry', title = null } = {}) {
  const safeId = String(retryId).replace(/[^a-zA-Z0-9_-]/g, '') || 'btnPageRetry';
  return `
    <div class="page-state page-state--error">
      ${title ? `<div class="page-header"><div class="page-header-text"><h1>${sanitize(title)}</h1></div></div>` : ''}
      <div class="alert alert-danger" role="alert">${sanitize(message)}</div>
      <div class="page-state-actions">
        <button type="button" class="btn btn-secondary btn-sm" id="${safeId}">Reintentar</button>
      </div>
    </div>`;
}

/** Compact error for a section (e.g. table wrap) — same retry pattern. */
export function sectionErrorState({ message = 'Error al cargar', retryId = 'btnSectionRetry' } = {}) {
  const safeId = String(retryId).replace(/[^a-zA-Z0-9_-]/g, '') || 'btnSectionRetry';
  return `
    <div class="page-state page-state--section-error">
      <div class="alert alert-danger" role="alert">${sanitize(message)}</div>
      <div class="page-state-actions">
        <button type="button" class="btn btn-ghost btn-sm" id="${safeId}">Reintentar</button>
      </div>
    </div>`;
}

export function bindRetry(container, onRetry, retryId = 'btnPageRetry') {
  const safeId = String(retryId).replace(/[^a-zA-Z0-9_-]/g, '') || 'btnPageRetry';
  container.querySelector(`#${safeId}`)?.addEventListener('click', () => onRetry());
}

/** Replace container with error + wire retry in one call. */
export function showError(container, { message, onRetry, title = null, retryId = 'btnPageRetry' } = {}) {
  container.innerHTML = errorState({ message, retryId, title });
  if (onRetry) bindRetry(container, onRetry, retryId);
}
