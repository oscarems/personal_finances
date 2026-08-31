import * as api from '../api/client.js';
import { sanitize } from '../utils.js';

let _open = false;
let _items = [];
let _refreshTimer = null;

export function initNotifications() {
  const host = document.getElementById('notifHost');
  if (!host) return;

  host.innerHTML = `
    <div class="notif-bell-wrap">
      <button class="notif-bell-btn" id="notifBellBtn" title="Notificaciones" aria-label="Notificaciones">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 01-3.46 0"/>
        </svg>
        <span class="notif-badge" id="notifBadge" hidden>0</span>
      </button>
      <div class="notif-panel" id="notifPanel" hidden>
        <div class="notif-panel-header">
          <strong>Notificaciones</strong>
          <div class="notif-panel-actions">
            <button class="btn btn-ghost btn-xs" id="notifRefresh" title="Actualizar">↻</button>
            <button class="btn btn-ghost btn-xs" id="notifClose" title="Cerrar" aria-label="Cerrar">×</button>
          </div>
        </div>
        <div class="notif-panel-body" id="notifPanelBody">
          <div class="text-soft text-sm p-3">Cargando…</div>
        </div>
      </div>
    </div>
  `;

  const btn = host.querySelector('#notifBellBtn');
  const panel = host.querySelector('#notifPanel');

  function closePanel() {
    _open = false;
    panel.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
  }

  function openPanel() {
    _open = true;
    panel.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    refreshNotifications();
  }

  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-haspopup', 'true');

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (_open) closePanel();
    else openPanel();
  });

  host.querySelector('#notifRefresh').addEventListener('click', (e) => {
    e.stopPropagation();
    refreshNotifications();
  });

  host.querySelector('#notifClose').addEventListener('click', (e) => {
    e.stopPropagation();
    closePanel();
  });

  document.addEventListener('click', (e) => {
    if (!_open) return;
    if (!host.contains(e.target)) closePanel();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _open) closePanel();
  });

  refreshNotifications();
  if (_refreshTimer) clearInterval(_refreshTimer);
  _refreshTimer = setInterval(refreshNotifications, 5 * 60 * 1000);
}

async function refreshNotifications() {
  const badge = document.getElementById('notifBadge');
  const body = document.getElementById('notifPanelBody');
  try {
    const [budget, smart] = await Promise.all([
      api.alerts.budget().catch(() => ({ alerts: [] })),
      api.alerts.smart().catch(() => ({ notifications: [] })),
    ]);

    const budgetItems = (budget.alerts ?? []).map(a => ({
      source: 'budget',
      severity: mapBudgetSeverity(a.state),
      title: a.category_name || a.state_label || 'Presupuesto',
      message: a.message || a.state_label || '',
    }));

    const smartItems = (smart.notifications ?? []).map(n => ({
      source: 'smart',
      severity: n.severity || 'info',
      title: n.title || 'Aviso',
      message: n.message || '',
    }));

    _items = [...budgetItems, ...smartItems].slice(0, 40);
    const count = _items.length;

    if (badge) {
      badge.hidden = count === 0;
      badge.textContent = count > 99 ? '99+' : String(count);
    }

    if (body && _open) {
      renderPanelBody(body);
    } else if (body && body.dataset.loaded !== '1') {
      // keep lightweight until opened
      body.innerHTML = `<div class="text-soft text-sm p-3">${count ? `${count} avisos` : 'Sin notificaciones'}</div>`;
    }
  } catch {
    if (badge) badge.hidden = true;
  }
}

function renderPanelBody(body) {
  body.dataset.loaded = '1';
  if (!_items.length) {
    body.innerHTML = `<div class="text-soft text-sm p-3">Todo en orden — sin avisos.</div>`;
    return;
  }
  body.innerHTML = _items.map(item => `
    <div class="notif-item notif-item--${sanitize(item.severity)}">
      <div class="notif-item-title">${sanitize(item.title)}</div>
      <div class="notif-item-msg">${item.message}</div>
      <div class="notif-item-source">${item.source === 'budget' ? 'Presupuesto' : 'Inteligente'}</div>
    </div>
  `).join('');
}

function mapBudgetSeverity(state) {
  const s = (state || '').toUpperCase();
  if (s === 'CRITICAL' || s === 'OVER') return 'danger';
  if (s === 'WARNING' || s === 'WATCH') return 'warning';
  return 'info';
}
