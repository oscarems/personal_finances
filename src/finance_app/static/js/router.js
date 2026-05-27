const routes = new Map();
let currentPage = null;

export function register(path, loader) {
  routes.set(path, loader);
}

export function navigate(path, pushState = true) {
  if (pushState) history.pushState({}, '', path);
  loadRoute(path);
}

export function init() {
  window.addEventListener('popstate', () => loadRoute(location.pathname));

  document.addEventListener('click', e => {
    const link = e.target.closest('[data-link]');
    if (!link) return;
    const href = link.dataset.link || link.getAttribute('href');
    if (!href || href.startsWith('http') || href.startsWith('mailto')) return;
    e.preventDefault();
    navigate(href);
  });

  loadRoute(location.pathname);
}

async function loadRoute(path) {
  const main = document.getElementById('main');
  const topbarTitle = document.getElementById('topbarTitle');
  const topbarActions = document.getElementById('topbarActions');

  if (currentPage?.cleanup) {
    try { currentPage.cleanup(); } catch {}
  }
  currentPage = null;

  main.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';

  // Mark active nav item
  document.querySelectorAll('.nav-item').forEach(el => {
    const itemPath = el.dataset.path ?? '';
    const isActive = itemPath === path || (itemPath !== '/' && path.startsWith(itemPath));
    el.classList.toggle('active', isActive);
  });

  const loader = resolveRoute(path);
  if (!loader) {
    main.innerHTML = `<div class="empty-state">
      <div class="empty-state-icon">🔍</div>
      <h3>Página no encontrada</h3>
      <p>La ruta <code>${sanitize(path)}</code> no existe.</p>
    </div>`;
    return;
  }

  try {
    const mod = await loader();
    if (topbarTitle) topbarTitle.textContent = mod.title ?? '';
    if (topbarActions) topbarActions.innerHTML = '';
    await mod.mount(main);
    currentPage = mod;
  } catch (err) {
    console.error('[router] Error loading page:', path, err);
    main.innerHTML = `<div class="alert alert-danger" style="margin:24px">
      Error al cargar la página: ${sanitize(err.message)}
    </div>`;
  }
}

function resolveRoute(path) {
  if (routes.has(path)) return routes.get(path);
  // Prefix match (e.g. /advanced/gmail)
  for (const [key, loader] of routes) {
    if (key !== '/' && path.startsWith(key)) return loader;
  }
  return null;
}

function sanitize(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}
