export function emptyState({ icon = '📋', title, hint = '', actionLabel = '', actionId = '' } = {}) {
  return `
    <div class="empty-state">
      <div class="empty-state__icon">${icon}</div>
      <h3 class="empty-state__title">${title}</h3>
      ${hint ? `<p class="empty-state__hint">${hint}</p>` : ''}
      ${actionLabel ? `<button class="btn btn-primary" id="${actionId}">${actionLabel}</button>` : ''}
    </div>`;
}
