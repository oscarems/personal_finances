/**
 * Vista móvil read-only — sincroniza por WiFi con el servidor local.
 * Cache en localStorage cuando el PC está apagado (datos pueden estar desactualizados).
 */
import * as api from '../api/client.js';
import { fmtCurrency, sanitize } from '../utils.js';
import { statusLabel, statusTone } from '../lib/budgetInsights.js';

export const title = 'Consulta móvil';

const CACHE_KEY = 'pf_mobile_snapshot';

export async function mount(container) {
  document.documentElement.classList.add('mobile-consult');
  container.classList.add('mobile-page-root');
  container.innerHTML = loadingShell();
  await refresh(container, { silent: false });
}

export function cleanup() {
  document.documentElement.classList.remove('mobile-consult');
}

function loadingShell() {
  return `
    <div class="mobile-shell">
      <header class="mobile-header">
        <h1 class="mobile-title">Finanzas</h1>
        <button type="button" class="btn btn-ghost btn-sm" id="mobileRefresh" aria-label="Actualizar">↻</button>
      </header>
      <div class="mobile-body" id="mobileBody">
        <div class="mobile-loading">Cargando…</div>
      </div>
    </div>`;
}

function loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveCache(data) {
  localStorage.setItem(CACHE_KEY, JSON.stringify(data));
}

function formatSyncTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('es-CO', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

async function refresh(container, { silent }) {
  const body = container.querySelector('#mobileBody');
  if (!body) return;

  if (!silent) {
    body.innerHTML = '<div class="mobile-loading">Sincronizando…</div>';
  }

  let data = null;
  let stale = false;
  let errorMsg = null;

  try {
    data = await api.mobile.snapshot();
    saveCache(data);
    stale = false;
  } catch (err) {
    errorMsg = err.message || 'No se pudo conectar';
    data = loadCache();
    stale = true;
  }

  if (!data) {
    body.innerHTML = `
      <div class="mobile-empty card">
        <div class="card-body">
          <p class="mb-3"><strong>Sin datos en el celular</strong></p>
          <p class="text-soft text-sm">Conéctate a la misma WiFi que tu PC, enciende la app (<code>python run.py</code>) y pulsa Actualizar.</p>
          ${errorMsg ? `<p class="text-danger text-sm mt-2">${sanitize(errorMsg)}</p>` : ''}
          <button type="button" class="btn btn-primary btn-sm mt-3" id="mobileRetry">Reintentar</button>
        </div>
      </div>`;
    body.querySelector('#mobileRetry')?.addEventListener('click', () => refresh(container, { silent: false }));
    bindRefresh(container);
    return;
  }

  body.innerHTML = renderSnapshot(data, { stale, errorMsg });
  bindRefresh(container);
}

function renderSnapshot(data, { stale, errorMsg }) {
  const ready = data.ready_to_assign ?? 0;
  const readyCls = ready >= 0 ? 'positive' : 'negative';
  const attention = data.attention ?? [];
  const accounts = data.accounts_by_currency ?? {};
  const totals = data.totals ?? {};

  return `
    ${stale ? `
    <div class="mobile-stale-banner" role="status">
      <strong>Datos en caché</strong>
      <span>Última sync: ${formatSyncTime(data.generated_at)}</span>
      ${errorMsg ? `<span class="mobile-stale-err">${sanitize(errorMsg)}</span>` : ''}
    </div>` : `
    <div class="mobile-fresh-banner" role="status">
      Actualizado · ${formatSyncTime(data.generated_at)}
    </div>`}

    <section class="mobile-hero card mb-3">
      <div class="card-body">
        <div class="kpi-label">Listo para asignar</div>
        <div class="kpi-value amount ${readyCls} mobile-hero-value">${fmtCurrency(ready, data.currency || 'COP')}</div>
        <p class="text-soft text-sm mb-0">Mes ${sanitize(data.month || '')}</p>
      </div>
    </section>

    <section class="mobile-stats stat-row mb-3">
      <div class="stat-chip">
        <span class="stat-chip-label">Disponible gastos</span>
        <span class="stat-chip-value amount">${fmtCurrency(totals.available ?? 0, 'COP')}</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip-label">Ahorros</span>
        <span class="stat-chip-value amount" style="color:var(--fin-accent)">${fmtCurrency(totals.savings ?? 0, 'COP')}</span>
      </div>
    </section>

    <section class="card mb-3">
      <div class="card-header">
        <span class="card-title">Atención</span>
      </div>
      <div class="card-body">
        ${attention.length
          ? attention.map(item => {
              const tone = statusTone(item.status);
              return `
                <div class="ux-attention-row mobile-attention-row">
                  <span class="ux-attention-dot" style="background:${tone}"></span>
                  <span class="ux-attention-name">${sanitize(item.name)}</span>
                  <span class="ux-attention-meta text-soft">${statusLabel(item.status, item.pct_used, { isSavings: item.is_savings })}</span>
                </div>`;
            }).join('')
          : '<p class="text-soft text-sm mb-0">Todo bajo control este mes.</p>'}
      </div>
    </section>

    <section class="card mb-3">
      <div class="card-header"><span class="card-title">Saldos por moneda</span></div>
      <div class="card-body">
        ${Object.entries(accounts).map(([cur, bal]) => `
          <div class="list-row flex justify-between">
            <span>${cur}</span>
            <span class="amount">${fmtCurrency(bal, cur)}</span>
          </div>
        `).join('') || '<p class="text-soft text-sm">Sin cuentas</p>'}
      </div>
    </section>

    <p class="mobile-footnote text-soft text-xs">
      Solo lectura. Para registrar movimientos usa el PC o abre la app completa en el navegador.
    </p>`;
}

function bindRefresh(container) {
  container.querySelector('#mobileRefresh')?.addEventListener('click', () => refresh(container, { silent: false }));
}
