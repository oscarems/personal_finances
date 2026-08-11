import { sanitize } from '../utils.js';

/**
 * Canonical empty state. All strings are escaped for safe innerHTML use.
 * Prefer an SVG/emoji icon as decoration only; title carries meaning.
 */
export function emptyState({ icon = '📋', title = 'Sin datos', hint = '', actionLabel = '', actionId = '' } = {}) {
  const safeActionId = actionId ? String(actionId).replace(/[^a-zA-Z0-9_-]/g, '') : '';
  return `
    <div class="empty-state">
      <div class="empty-state__icon" aria-hidden="true">${sanitize(icon)}</div>
      <h3 class="empty-state__title">${sanitize(title)}</h3>
      ${hint ? `<p class="empty-state__hint">${sanitize(hint)}</p>` : ''}
      ${actionLabel && safeActionId
        ? `<button type="button" class="btn btn-primary" id="${safeActionId}">${sanitize(actionLabel)}</button>`
        : ''}
    </div>`;
}
