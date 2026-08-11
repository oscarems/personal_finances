import * as api from '../api/client.js';
import { fmtCurrency, fmtDateShort, sanitize, todayISO, optional } from '../utils.js';
import { toast } from '../components/toast.js';
import { openModal } from '../components/modal.js';
import { emptyState } from '../components/emptyState.js';
import { showError } from '../components/pageState.js';

export const title = 'Dashboard';

export async function mount(container) {
  container.innerHTML = skeletonHtml();
  try {
    const [accounts, txResp, budget, fxData, cashflow, savingsRate, financialHealth] = await Promise.all([
      api.accounts.list(),
      api.transactions.list({ limit: 10 }),
      optional(api.budgets.current(), null, 'Presupuesto'),
      optional(api.exchangeRates.current(), null, 'Tasa de cambio'),
      optional(api.reports.cashflowSummary(), null, 'Flujo de Caja'),
      optional(api.reports.savingsRate({ months: 3 }), null, 'Tasa de Ahorro'),
      optional(api.reports.financialHealth(), null, 'Salud Financiera'),
    ]);
    const txList = Array.isArray(txResp) ? txResp : (txResp?.transactions ?? txResp?.items ?? []);
    const usdRate = fxData?.rate ?? fxData?.USD ?? null;

    container.innerHTML = renderPage({
      accounts,
      txList,
      budget,
      usdRate,
      cashflow,
      savingsRate,
      financialHealth,
    });
    bindEvents(container, accounts);
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
    <div class="card mb-5">
      <div class="card-body"><div class="skeleton skeleton-banner"></div></div>
    </div>
    <div class="dash-hero card mb-5">
      <div class="card-body">
        <div class="skeleton skeleton-label"></div>
        <div class="skeleton skeleton-hero-value"></div>
      </div>
    </div>
    <div class="section-grid cols-2 mb-5">
      <div class="card"><div class="skeleton skeleton-block"></div></div>
      <div class="card"><div class="skeleton skeleton-block"></div></div>
    </div>
    <div class="card"><div class="skeleton skeleton-block"></div></div>`;
}

function renderPage({ accounts, txList, budget, usdRate, cashflow, savingsRate, financialHealth }) {
  const today = new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' });
  const todayCap = today.charAt(0).toUpperCase() + today.slice(1);
  const readyToAssign = budget?.ready_to_assign ?? null;

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

    ${healthCard(financialHealth)}
    ${readyToAssignHero(readyToAssign, budget)}

    <div class="section-grid cols-2 mb-5">
      ${cashflowSection(cashflow, usdRate)}
      ${savingsRateCard(savingsRate)}
    </div>

    ${recentTxCard(txList)}
  `;
}

function readyToAssignHero(readyToAssign, budget) {
  if (readyToAssign === null || !budget) {
    return `
      <div class="dash-hero card mb-5">
        <div class="card-body">
          <div class="kpi-label">Listo para asignar</div>
          <p class="text-soft mt-2 mb-4">Aún no hay presupuesto del mes para calcular este valor.</p>
          <a class="btn btn-primary btn-sm" data-link="/budget">Ir a presupuesto</a>
        </div>
      </div>`;
  }

  const cls = readyToAssign >= 0 ? 'positive' : 'negative';
  const hint = readyToAssign >= 0
    ? 'Dinero en cuentas que todavía no está asignado a categorías.'
    : 'Hay más disponible en categorías que saldo en cuentas — revisa el presupuesto.';

  return `
    <div class="dash-hero card mb-5">
      <div class="card-body dash-hero-body">
        <div class="dash-hero-main">
          <div class="kpi-label">Listo para asignar</div>
          <div class="kpi-value amount ${cls} dash-hero-value">${fmtCurrency(readyToAssign, 'COP')}</div>
          <p class="kpi-sub mt-2">${hint}</p>
        </div>
        <div class="dash-hero-actions">
          <a class="btn btn-primary btn-sm" data-link="/budget">Asignar en presupuesto</a>
        </div>
      </div>
    </div>`;
}

function healthCard(fh) {
  if (!fh || !fh.scores) {
    return `
      <div class="card mb-5">
        <div class="card-header">
          <span class="card-title">Salud Financiera</span>
          <a class="btn btn-ghost btn-sm" data-link="/financial-health">Ver detalle</a>
        </div>
        <div class="card-body">${emptyState({ icon: '💗', title: 'Sin datos de salud', hint: 'No se pudo calcular la salud financiera este mes.' })}</div>
      </div>`;
  }

  const { overall, grade, estado } = fh.scores;
  const ESTADO_META = {
    bueno:   { badge: 'badge-success', label: 'Buena',   dot: 'var(--fin-success)' },
    regular: { badge: 'badge-warning', label: 'Regular', dot: 'var(--fin-amber)' },
    critico: { badge: 'badge-danger',  label: 'Crítica', dot: 'var(--fin-danger)' },
  };
  const meta = ESTADO_META[estado] ?? ESTADO_META.regular;
  const topInsight = (fh.insights ?? []).find(i => i.kind === 'bad') ?? (fh.insights ?? [])[0];

  return `
    <div class="card mb-5">
      <div class="card-body">
        <div class="dash-health">
          <div class="dash-health-left">
            <span class="dash-health-dot" style="background:${meta.dot}"></span>
            <div>
              <div class="dash-health-title">Salud financiera del mes</div>
              <div class="text-soft text-xs">${topInsight ? sanitize(topInsight.message) : 'Sin observaciones destacadas'}</div>
            </div>
          </div>
          <div class="dash-health-right">
            <span class="amount dash-health-score">${overall.toFixed(1)}<span class="text-soft text-sm">/100</span></span>
            <span class="badge ${meta.badge}">${meta.label} · ${grade}</span>
            <a class="btn btn-ghost btn-sm" data-link="/financial-health">Ver detalle</a>
          </div>
        </div>
      </div>
    </div>`;
}

function recentTxCard(txList) {
  const rows = txList.slice(0, 9).map(tx => {
    const isIncome = (tx.amount ?? 0) >= 0;
    const sign = isIncome ? '+' : '-';
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

function cashflowSection(cf, usdRate) {
  if (!cf) {
    return `
      <div class="card">
        <div class="card-header"><span class="card-title">Flujo del mes</span></div>
        <div class="card-body">${emptyState({ icon: '📉', title: 'Sin flujo de caja', hint: 'Aún no hay ingresos o gastos para este mes.' })}</div>
      </div>`;
  }

  const rate = usdRate ?? 0;
  const inCOP  = cf.income?.cop  ?? 0;
  const inUSD  = cf.income?.usd  ?? 0;
  const exNoSavCOP = cf.expenses_no_savings?.cop ?? (cf.expenses?.cop ?? 0);
  const exNoSavUSD = cf.expenses_no_savings?.usd ?? (cf.expenses?.usd ?? 0);
  const exCOP  = cf.expenses?.cop ?? 0;
  const exUSD  = cf.expenses?.usd ?? 0;
  const savCOP = exCOP - exNoSavCOP;
  const savUSD = exUSD - exNoSavUSD;
  const balCOP = inCOP - exCOP;
  const balUSD = inUSD - exUSD;

  const inTotal  = inCOP  + inUSD  * rate;
  const exTotal  = exNoSavCOP + exNoSavUSD * rate;
  const savTotal = savCOP + savUSD * rate;
  const balTotal = balCOP + balUSD * rate;

  const hasSavings = savCOP > 0 || savUSD > 0;
  const monthLabel = new Date().toLocaleDateString('es-CO', { month: 'long', year: 'numeric' });
  const balCls = balTotal >= 0 ? 'positive' : 'negative';
  const rateNote = usdRate != null
    ? `Total en COP · TRM ${fmtCurrency(usdRate, 'COP')}`
    : 'Sin TRM — totales en COP omiten USD';

  function row(label, cop, usd, total, cls = '', bold = false) {
    return `
      <tr class="${bold ? 'dash-cf-total' : ''}">
        <td>${label}</td>
        <td class="amount ${cls}">${fmtCurrency(cop, 'COP')}</td>
        <td class="amount ${cls}">${fmtCurrency(usd, 'USD')}</td>
        <td class="amount ${cls}">${fmtCurrency(total, 'COP')}</td>
      </tr>`;
  }

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Flujo del mes · ${monthLabel}</span>
        <span class="text-soft text-xs">${rateNote}</span>
      </div>
      <div class="card-body overflow-x-auto">
        <table class="fin-table dash-cf-table">
          <thead>
            <tr>
              <th></th>
              <th class="amount">COP</th>
              <th class="amount">USD</th>
              <th class="amount">Total</th>
            </tr>
          </thead>
          <tbody>
            ${row('Ingresos', inCOP, inUSD, inTotal, 'positive')}
            ${row('Gastos', exNoSavCOP, exNoSavUSD, exTotal, 'negative')}
            ${hasSavings ? row('Ahorros', savCOP, savUSD, savTotal) : ''}
            ${row('Balance', balCOP, balUSD, balTotal, balCls, true)}
          </tbody>
        </table>
      </div>
    </div>`;
}

function savingsRateCard(sr) {
  if (!sr || !sr.monthly || sr.monthly.length === 0) {
    return `
      <div class="card">
        <div class="card-header"><span class="card-title">Tasa de ahorro</span></div>
        <div class="card-body">${emptyState({ icon: '📊', title: 'Sin tasa de ahorro', hint: 'Necesitas ingresos registrados para calcularla.' })}</div>
      </div>`;
  }

  const months = sr.monthly.slice(-3);
  const avg = sr.average_savings_rate ?? 0;
  const avgCls = avg >= 20 ? 'positive' : avg >= 10 ? '' : 'negative';

  const rows = months.map(m => {
    const cls = m.savings_rate >= 20 ? 'positive' : m.savings_rate >= 10 ? '' : 'negative';
    const bar = Math.max(0, Math.min(100, m.savings_rate));
    const tone = m.savings_rate >= 20 ? 'success' : m.savings_rate >= 10 ? 'amber' : 'danger';
    return `
      <div class="dash-sr-row">
        <div class="flex justify-between mb-1">
          <span class="text-soft text-sm">${sanitize(m.month_name)}</span>
          <span class="amount ${cls} text-sm">${m.savings_rate.toFixed(1)}%</span>
        </div>
        <div class="dash-sr-track">
          <div class="dash-sr-fill dash-sr-fill--${tone}" style="width:${bar}%"></div>
        </div>
      </div>`;
  }).join('');

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Tasa de ahorro</span>
        <a class="btn btn-ghost btn-sm" data-link="/income">Ver detalle</a>
      </div>
      <div class="card-body">
        <div class="dash-sr-hero">
          <div class="kpi-label">Promedio trimestre</div>
          <div class="kpi-value amount ${avgCls} dash-sr-avg">${avg.toFixed(1)}%</div>
          <div class="text-soft text-xs mt-1">Meta recomendada: ≥ 20%</div>
        </div>
        ${rows}
      </div>
    </div>`;
}

function bindEvents(container, accounts) {
  container.querySelector('#btnQuickAdd')?.addEventListener('click', () => {
    openQuickAdd(accounts, container);
  });
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
