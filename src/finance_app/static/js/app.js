import { init as initRouter, register, navigate } from './router.js';

// ── Route definitions ─────────────────────────────────────
register('/',                    () => import('./pages/dashboard.js'));
register('/accounts',            () => import('./pages/accounts.js'));
register('/budget',              () => import('./pages/budget.js'));
register('/transactions',        () => import('./pages/transactions.js'));
register('/debts',               () => import('./pages/debts.js'));
register('/goals',               () => import('./pages/goals.js'));
register('/reports',             () => import('./pages/reports.js'));
register('/recurring',           () => import('./pages/recurring.js'));
register('/financial-health',    () => import('./pages/financial-health.js'));
register('/mortgage',            () => import('./pages/mortgage.js'));
register('/investment-simulator',() => import('./pages/investment.js'));
register('/emergency-fund',      () => import('./pages/emergency-fund.js'));
register('/patrimonio',          () => import('./pages/patrimonio.js'));
register('/advanced/gmail',          () => import('./pages/gmail-import.js'));
register('/advanced/merchant-rules', () => import('./pages/merchant-rules.js'));
register('/setup',                   () => import('./pages/setup.js'));

// ── Sidebar navigation items ──────────────────────────────
const NAV_GROUPS = [
  { label: 'Principal', items: [
    { path: '/',             label: 'Dashboard',       icon: icoHome },
    { path: '/accounts',     label: 'Cuentas',         icon: icoCreditCard },
    { path: '/budget',       label: 'Presupuesto',     icon: icoPie },
    { path: '/transactions', label: 'Transacciones',   icon: icoList },
  ]},
  { label: 'Análisis', items: [
    { path: '/reports',          label: 'Reportes',        icon: icoBarChart },
    { path: '/financial-health', label: 'Salud Financiera',icon: icoHeart },
    { path: '/patrimonio',       label: 'Patrimonio',      icon: icoTrending },
  ]},
  { label: 'Deudas', items: [
    { path: '/debts',    label: 'Deudas',    icon: icoBank },
    { path: '/mortgage', label: 'Hipoteca',  icon: icoHouseKey },
  ]},
  { label: 'Metas', items: [
    { path: '/goals',                label: 'Metas',             icon: icoTarget },
    { path: '/emergency-fund',       label: 'Fondo Emergencia',  icon: icoShield },
    { path: '/investment-simulator', label: 'Simulador',         icon: icoTrendingUp },
  ]},
  { label: 'Automatización', items: [
    { path: '/recurring',                label: 'Recurrentes',       icon: icoRepeat },
    { path: '/advanced/gmail',           label: 'Importar Gmail',    icon: icoInbox },
    { path: '/advanced/merchant-rules',  label: 'Reglas Comercios',  icon: icoStore },
  ]},
  { label: 'Herramientas', items: [
    { path: '/setup', label: 'Configuración', icon: icoSettings },
  ]},
];

function renderSidebar() {
  const nav = document.getElementById('sidebarNav');
  nav.innerHTML = NAV_GROUPS.map(g => `
    <div class="nav-group">
      <div class="nav-group-label">${g.label}</div>
      ${g.items.map(item => `
        <a class="nav-item" data-path="${item.path}" data-link="${item.path}" href="${item.path}">
          <span class="nav-item-icon">${item.icon()}</span>
          <span class="nav-item-label">${item.label}</span>
        </a>
      `).join('')}
    </div>
  `).join('');
}

function initSidebarCollapse() {
  const sidebar = document.getElementById('sidebar');
  const btn = document.getElementById('sidebarCollapseBtn');
  if (localStorage.getItem('sb-collapsed') === '1') sidebar.classList.add('collapsed');
  btn?.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('sb-collapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
  });
}

function initMobileMenu() {
  const btn     = document.getElementById('mobileMenuBtn');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  btn?.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('visible');
  });
  overlay?.addEventListener('click', () => {
    sidebar.classList.remove('open');
    overlay.classList.remove('visible');
  });
  // Close sidebar on nav click (mobile)
  document.getElementById('sidebarNav')?.addEventListener('click', e => {
    if (e.target.closest('.nav-item') && window.innerWidth < 769) {
      sidebar.classList.remove('open');
      overlay.classList.remove('visible');
    }
  });
}

// ── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  renderSidebar();
  initSidebarCollapse();
  initMobileMenu();
  initRouter();
});

// ── Inline SVG icons ──────────────────────────────────────
function svg(paths) {
  return `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
}

function icoHome()       { return svg('<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'); }
function icoCreditCard() { return svg('<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>'); }
function icoPie()        { return svg('<path d="M21.21 15.89A10 10 0 118 2.83M22 12A10 10 0 0012 2v10z"/>'); }
function icoList()       { return svg('<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>'); }
function icoBarChart()   { return svg('<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>'); }
function icoHeart()      { return svg('<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>'); }
function icoTrending()   { return svg('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>'); }
function icoBank()       { return svg('<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>'); }
function icoHouseKey()   { return svg('<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>'); }
function icoTarget()     { return svg('<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>'); }
function icoShield()     { return svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'); }
function icoTrendingUp() { return svg('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>'); }
function icoRepeat()     { return svg('<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/>'); }
function icoInbox()      { return svg('<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/>'); }
function icoSettings()   { return svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>'); }
function icoStore()      { return svg('<path d="M3 9l1-6h16l1 6"/><path d="M3 9a3 3 0 006 0 3 3 0 006 0 3 3 0 006 0"/><path d="M5 9v12h14V9"/>'); }
