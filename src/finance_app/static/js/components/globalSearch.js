import * as api from '../api/client.js';
import { sanitize, debounce } from '../utils.js';
import { navigate } from '../router.js';

export function initGlobalSearch() {
  const host = document.getElementById('globalSearchHost');
  if (!host) return;

  host.innerHTML = `
    <div class="global-search-wrap">
      <input type="search" id="globalSearchInput" class="global-search-input" placeholder="Buscar…" autocomplete="off">
      <div class="global-search-results" id="globalSearchResults" hidden></div>
    </div>
  `;

  const input = host.querySelector('#globalSearchInput');
  const results = host.querySelector('#globalSearchResults');

  const runSearch = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) {
      results.hidden = true;
      results.innerHTML = '';
      return;
    }
    try {
      const data = await api.search.query(q, 8);
      const items = data.results ?? [];
      if (!items.length) {
        results.innerHTML = `<div class="global-search-empty">Sin resultados</div>`;
        results.hidden = false;
        return;
      }
      results.innerHTML = items.map(item => `
        <button type="button" class="global-search-item" data-path="${sanitize(item.path || '/')}">
          <span class="global-search-type">${sanitize(typeLabel(item.type))}</span>
          <span class="global-search-label">${sanitize(item.label)}</span>
          <span class="global-search-sub">${sanitize(item.subtitle || '')}</span>
        </button>
      `).join('');
      results.hidden = false;
      results.querySelectorAll('[data-path]').forEach(btn => {
        btn.addEventListener('click', () => {
          results.hidden = true;
          input.value = '';
          navigate(btn.dataset.path);
        });
      });
    } catch {
      results.hidden = true;
    }
  }, 250);

  input.addEventListener('input', runSearch);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      results.hidden = true;
      input.blur();
    }
  });
  document.addEventListener('click', (e) => {
    if (!host.contains(e.target)) results.hidden = true;
  });
}

function typeLabel(type) {
  return ({ account: 'Cuenta', category: 'Categoría', debt: 'Deuda', transaction: 'Tx' })[type] || type;
}
