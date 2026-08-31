import * as api from '../api/client.js';
import { fmtCurrency, fmtDateShort, sanitize, todayISO } from '../utils.js';
import { toast } from '../components/toast.js';
import { openModal } from '../components/modal.js';
import { emptyState } from '../components/emptyState.js';
import { showError } from '../components/pageState.js';
import {
  flattenBudgetGroups,
  getAttentionCategories,
  statusLabel,
  statusTone,
} from '../lib/budgetInsights.js';

export const title = 'Dashboard';

export async function mount(container) {
  container.innerHTML = skeletonHtml();
  try {
    const [txResp, budget] = await Promise.all([
      api.transactions.list({ limit: 8 }),
      api.budgets.current(),
    ]);
    const txList = Array.isArray(txResp) ? txResp : (txResp?.transactions ?? txResp?.items ?? []);
    container.innerHTML = renderPage({ txList, budget });
    bindEvents(container);
  } catch (err) {
    showError(container, {
      title: 'Dashboard',
      message: err.message || 'Error al cargar el dashboard',
      onRetry: () => mount(container),
    });
  }
}

function skeletonHtml() {
  return `
    <div class="page-header">
      <div class="page-header-text">
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-subtitle"></div>
      </div>
    </div>
    <div class="ux-free-hero card mb-4">
      <div class="card-body"><div class="skeleton skeleton-hero-value"></div></div>
    </div>
    <div class="card mb-4"><div class="card-body"><div class="skeleton skeleton-banner"></div></div></div>
    <div class="card"><div class="skeleton skeleton-block"></div></div>`;
}

function renderPage({ txList, budget }) {
  const today = new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' });
  const todayCap = today.charAt(0).toUpperCase() + today.slice(1);
  const flatCats = flattenBudgetGroups(budget);
  const attention = getAttentionCategories(flatCats, { limit: 5 });
  const readyToAssign = budget?.ready_to_assign ?? null;
  const totals = budget?.totals ?? {};
  const expCats = flatCats.filter(c => c.category_type === 'expense');
  const savCats = flatCats.filter(c => c.category_type === 'savings');
  const totalAvailable = expCats.reduce((s, c) => s + (c.available ?? 0), 0);
  const totalSavings = savCats.reduce((s, c) => s + (c.available ?? 0), 0);

  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Dashboard</h1>
        <p>${todayCap}</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-primary btn-sm" id="btnQuickAdd">+ Transacción</button>
      </div>
    </div>

    ${freeMoneyHero(readyToAssign)}
    ${attentionCard(attention)}
    ${quickStatsRow({ totalAvailable, totalSavings, readyToAssign, inAccounts: totals.in_accounts })}
    ${recentTxCard(txList)}
  `;
}

function freeMoneyHero(readyToAssign) {
  if (readyToAssign === null) {
    return `
      <div class="ux-free-hero card mb-4">
        <div class="card-body">
          ${emptyState({ icon: '💰', title: 'Sin presupuesto del mes', hint: 'Inicializa el mes en Presupuesto para ver cuánto te queda libre.' })}
          <a class="btn btn-primary btn-sm mt-3" data-link="/budget">Ir a presupuesto</a>
        </div>
      </div>`;
  }

  const cls = readyToAssign >= 0 ? 'positive' : 'negative';
  const hint = readyToAssign >= 0
    ? readyToAssign === 0
      ? 'Cada peso tiene categoría — nada suelto en cuentas.'
      : 'Dinero en cuentas sin categoría todavía.'
    : 'Asignaste más de lo que tienes en cuentas — revisa el presupuesto.';

  return `
    <div class="ux-free-hero card mb-4">
      <div class="card-body ux-free-hero-body">
        <div class="ux-free-hero-main">
          <div class="kpi-label">Listo para asignar</div>
          <div class="kpi-value amount ${cls} ux-free-hero-value">${fmtCurrency(readyToAssign, 'COP')}</div>
          <p class="kpi-sub mt-2">${hint}</p>
        </div>
        <div class="ux-free-hero-actions">
          <a class="btn btn-primary btn-sm" data-link="/budget">Ver presupuesto</a>
          ${readyToAssign > 0 ? '<a class="btn btn-ghost btn-sm" data-link="/budget">Asignar ahora</a>' : ''}
        </div>
      </div>
    </div>`;
}

function attentionCard(attention) {
  if (!attention.length) {
    return `
      <div class="card mb-4 ux-attention-card ux-attention-card--ok">
        <div class="card-body ux-attention-ok">
          <span class="ux-attention-ok-icon" aria-hidden="true">✓</span>
          <div>
            <div class="ux-attention-ok-title">Presupuesto bajo control</div>
            <p class="text-soft text-sm mb-0">Ninguna categoría se pasó del 100% este mes.</p>
          </div>
        </div>
      </div>`;
  }

  const rows = attention.map(item => {
    const tone = statusTone(item.status);
    return `
      <a class="ux-attention-row" data-link="/budget" href="/budget">
        <span class="ux-attention-dot" style="background:${tone}"></span>
        <span class="ux-attention-name">${sanitize(item.name)}</span>
        <span class="ux-attention-meta text-soft">${statusLabel(item.status, item.pct_used, { isSavings: item.is_savings })}</span>
        <span class="amount ${item.available < 0 ? 'negative' : ''} ux-attention-amt">
          ${fmtCurrency(item.available, 'COP')}
        </span>
      </a>`;
  }).join('');

  return `
    <div class="card mb-4 ux-attention-card">
      <div class="card-header">
        <span class="card-title">Atención este mes</span>
        <a class="btn btn-ghost btn-sm" data-link="/budget">Presupuesto</a>
      </div>
      <div class="card-body ux-attention-list">${rows}</div>
    </div>`;
}

function quickStatsRow({ totalAvailable, totalSavings, inAccounts }) {
  return `
    <div class="stat-row mb-4">
      <div class="stat-chip">
        <span class="stat-chip-label">Disponible en gastos</span>
        <span class="stat-chip-value amount ${totalAvailable >= 0 ? 'text-success' : 'text-danger'}">
          ${fmtCurrency(totalAvailable, 'COP')}
        </span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip-label">Ahorros acumulados</span>
        <span class="stat-chip-value amount" style="color:var(--fin-accent)">${fmtCurrency(totalSavings, 'COP')}</span>
      </div>
      ${inAccounts != null ? `
      <div class="stat-chip">
        <span class="stat-chip-label">En cuentas (presupuesto)</span>
        <span class="stat-chip-value amount">${fmtCurrency(inAccounts, 'COP')}</span>
      </div>` : ''}
    </div>`;
}

function recentTxCard(txList) {
  const rows = txList.slice(0, 8).map(tx => {
    const isIncome = (tx.amount ?? 0) >= 0;
    const sign = isIncome ? '+' : '−';
    const cls  = isIncome ? 'positive' : 'negative';
    return `
      <div class="list-row flex justify-between items-center">
        <div class="dash-tx-meta">
          <div class="dash-tx-name">${sanitize(tx.payee_name || tx.memo || 'Sin descripción')}</div>
          <div class="text-soft text-xs">
            ${fmtDateShort(tx.date)} · ${sanitize(tx.category_name ?? 'Sin cat.')}
          </div>
        </div>
        <span class="amount ${cls} text-sm flex-shrink-0">
          ${sign}${fmtCurrency(Math.abs(tx.amount ?? 0), tx.currency?.code ?? 'COP')}
        </span>
      </div>`;
  }).join('');

  return `
    <div class="card mb-5">
      <div class="card-header">
        <span class="card-title">Transacciones recientes</span>
        <a class="btn btn-ghost btn-sm" data-link="/transactions">Ver todas</a>
      </div>
      <div class="card-body">
        ${rows || emptyState({ icon: '📋', title: 'Sin transacciones', hint: 'Cuando registres movimientos, aparecerán aquí.' })}
      </div>
    </div>`;
}

async function bindEvents(container) {
  let accounts = [];
  try {
    accounts = await api.accounts.list();
  } catch {
    accounts = [];
  }
  const openQuick = () => openQuickAdd(accounts, container);
  container.querySelector('#btnQuickAdd')?.addEventListener('click', openQuick);
}

function openQuickAdd(accounts, container) {
  const currencies = ['COP', 'USD'];

  openModal({
    title: 'Nueva Transacción',
    size: 'md',
    content: `
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label required">Fecha</label>
          <input type="date" id="qa-date" value="${todayISO()}">
        </div>
        <div class="form-group">
          <label class="form-label required">Tipo</label>
          <select id="qa-type">
            <option value="expense">Gasto</option>
            <option value="income">Ingreso</option>
          </select>
        </div>
      </div>
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label required">Monto</label>
          <input type="number" id="qa-amount" placeholder="0" min="0" step="0.01">
        </div>
        <div class="form-group">
          <label class="form-label">Moneda</label>
          <select id="qa-currency">
            ${currencies.map(c => `<option value="${c}">${c}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-group mb-4">
        <label class="form-label required">Cuenta</label>
        <select id="qa-account">
          <option value="">— seleccionar —</option>
          ${accounts.map(a => `<option value="${a.id}">${sanitize(a.name)}</option>`).join('')}
        </select>
      </div>
      <div class="form-group mb-4">
        <label class="form-label">Descripción / Beneficiario</label>
        <input type="text" id="qa-payee" placeholder="Ej: Supermercado">
      </div>
    `,
    submitLabel: 'Guardar',
    onSubmit: async (body) => {
      const date      = body.querySelector('#qa-date').value;
      const amount    = parseFloat(body.querySelector('#qa-amount').value);
      const currency  = body.querySelector('#qa-currency').value;
      const accountId = body.querySelector('#qa-account').value;
      const txType    = body.querySelector('#qa-type').value;
      const payee     = body.querySelector('#qa-payee').value.trim();

      if (!date || !amount || !accountId) throw new Error('Fecha, monto y cuenta son obligatorios');

      const currencyIdMap = { COP: 1, USD: 2 };
      await api.transactions.create({
        date, amount, currency_id: currencyIdMap[currency] ?? 1,
        account_id: parseInt(accountId),
        type: txType, payee_name: payee || undefined,
      });
      toast.success('Transacción guardada');
      await mount(container);
    },
  });
}
