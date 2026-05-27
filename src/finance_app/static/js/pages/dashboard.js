import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, fmtDateShort, sanitize, amountClass, progressBar } from '../utils.js';
import { toast } from '../components/toast.js';
import { openModal } from '../components/modal.js';

export const title = 'Dashboard';

export async function mount(container) {
  container.innerHTML = skeletonHtml();
  try {
    const [accounts, txResp, budget, debts, fxData, patrimonioData] = await Promise.all([
      api.accounts.list(),
      api.transactions.list({ limit: 10 }),
      api.budgets.current().catch(() => null),
      api.debts.list().catch(() => []),
      api.exchangeRates.current().catch(() => ({ rate: 4200 })),
      api.patrimonio.summary().catch(() => null),
    ]);
    const txList = Array.isArray(txResp) ? txResp : (txResp?.transactions ?? txResp?.items ?? []);
    const usdRate = fxData?.rate ?? 4200;
    container.innerHTML = renderPage(accounts, txList, budget, debts, usdRate, patrimonioData);
    bindEvents(container, accounts);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">Error al cargar el dashboard: ${sanitize(err.message)}</div>`;
  }
}

function skeletonHtml() {
  return `
    <div class="page-header">
      <div class="page-header-text">
        <div class="skeleton" style="height:26px;width:180px;margin-bottom:8px"></div>
        <div class="skeleton" style="height:14px;width:260px"></div>
      </div>
    </div>
    <div class="kpi-grid">
      ${[0,1,2,3].map(() => `
        <div class="kpi-card">
          <div class="skeleton" style="height:12px;width:80px;margin-bottom:12px"></div>
          <div class="skeleton" style="height:28px;width:140px;margin-bottom:8px"></div>
          <div class="skeleton" style="height:10px;width:100px"></div>
        </div>
      `).join('')}
    </div>
    <div class="section-grid cols-2">
      <div class="card"><div style="height:200px" class="skeleton" style="margin:0;border-radius:0"></div></div>
      <div class="card"><div style="height:200px" class="skeleton" style="margin:0;border-radius:0"></div></div>
    </div>`;
}

function renderPage(accounts, txList, budget, debts, usdRate, patrimonioData) {
  const DEBT_TYPES = ['credit_card','credit_loan','mortgage'];
  const savings   = accounts.filter(a => !DEBT_TYPES.includes(a.type));
  const debtAccts = accounts.filter(a =>  DEBT_TYPES.includes(a.type));

  const savingsCOP = savings.filter(a => (a.currency?.code ?? 'COP') === 'COP');
  const savingsUSD = savings.filter(a => (a.currency?.code ?? 'COP') === 'USD');
  const debtsCOP   = debtAccts.filter(a => (a.currency?.code ?? 'COP') === 'COP');
  const debtsUSD   = debtAccts.filter(a => (a.currency?.code ?? 'COP') === 'USD');

  const totalSavingsCOP = savingsCOP.reduce((s, a) => s + (a.balance ?? 0), 0);
  const totalSavingsUSD = savingsUSD.reduce((s, a) => s + (a.balance ?? 0), 0);
  const totalDebtsCOP   = debtsCOP.reduce((s, a) => s + Math.abs(a.balance ?? 0), 0);
  const totalDebtsUSD   = debtsUSD.reduce((s, a) => s + Math.abs(a.balance ?? 0), 0);

  // Activos de patrimonio (inmuebles, vehículos, etc.) separados por moneda
  const patrimonioActivos = patrimonioData?.activos ?? [];
  const patrimonioActivosCOP = patrimonioActivos
    .filter(a => (a.currency?.code ?? 'COP') === 'COP')
    .reduce((s, a) => s + (a.valor_actual ?? 0), 0);
  const patrimonioActivosUSD = patrimonioActivos
    .filter(a => (a.currency?.code ?? 'COP') === 'USD')
    .reduce((s, a) => s + (a.valor_actual ?? 0), 0);

  // Patrimonio neto en COP (convirtiendo USD a COP)
  const activosCOP  = totalSavingsCOP + totalSavingsUSD * usdRate + patrimonioActivosCOP + patrimonioActivosUSD * usdRate;
  const deudasCOP   = totalDebtsCOP   + totalDebtsUSD  * usdRate;
  const patrimonioNeto = activosCOP - deudasCOP;

  const expenseGroups = (budget?.groups ?? []).filter(g => !g.is_income);
  const expenseCats   = expenseGroups.flatMap(g => g.categories ?? []);
  const totalAssigned = expenseCats.reduce((s, c) => s + (c.assigned ?? 0), 0);
  const totalSpent    = expenseCats.reduce((s, c) => s + Math.abs(c.activity ?? 0), 0);

  const today = new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' });
  const todayCap = today.charAt(0).toUpperCase() + today.slice(1);

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

    <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr)">
      ${patrimonioBigCard(patrimonioNeto, activosCOP, deudasCOP, patrimonioActivosCOP + patrimonioActivosUSD * usdRate)}
      ${currencyCard('COP', totalSavingsCOP, totalDebtsCOP)}
      ${currencyCard('USD', totalSavingsUSD, totalDebtsUSD)}
    </div>

    <div class="kpi-grid" style="grid-template-columns:repeat(2,1fr);margin-top:0">
      ${kpiCard('Gastado este mes', totalSpent, 'COP', '', `de ${fmtCurrency(totalAssigned, 'COP')} asignado en categorías de gasto`)}
      ${kpiCard('Por gastar este mes', Math.max(0, totalAssigned - totalSpent), 'COP', totalAssigned - totalSpent >= 0 ? 'positive' : 'negative', 'asignado − gastado en categorías de gasto')}
    </div>

    <div class="section-grid cols-2" style="margin-bottom:20px">
      ${accountsCard(accounts)}
      ${recentTxCard(txList)}
    </div>

    ${budget && expenseCats.length > 0 ? budgetCard(expenseCats) : ''}
    ${debts.length > 0 ? debtsCard(debts) : ''}
  `;
}

function patrimonioBigCard(neto, activos, deudas, patrimonioActivosCOP) {
  const cls = neto >= 0 ? 'positive' : 'negative';
  return `
    <div class="kpi-card" style="grid-column:span 1">
      <div class="kpi-label">Patrimonio Neto</div>
      <div class="kpi-value ${cls}">${fmtCurrency(neto, 'COP')}</div>
      <div class="kpi-sub" style="margin-top:8px;display:flex;flex-direction:column;gap:3px">
        <span style="color:var(--color-success)">Activos: ${fmtCurrency(activos, 'COP')}</span>
        ${patrimonioActivosCOP > 0 ? `<span style="color:var(--color-success);opacity:0.7;font-size:0.72rem;padding-left:6px">incl. patrimonio: ${fmtCurrency(patrimonioActivosCOP, 'COP')}</span>` : ''}
        <span style="color:var(--color-danger)">Deudas: ${fmtCurrency(deudas, 'COP')}</span>
        <span style="font-size:0.67rem;opacity:0.6">todo en COP</span>
      </div>
    </div>`;
}

function currencyCard(currency, totalCuentas, totalDeudas) {
  const neto = totalCuentas - totalDeudas;
  const cls  = neto >= 0 ? 'positive' : 'negative';
  const flag = currency === 'COP' ? '🇨🇴' : '🇺🇸';
  return `
    <div class="kpi-card">
      <div class="kpi-label">${flag} ${currency}</div>
      <div class="kpi-value ${cls}">${fmtCurrency(neto, currency)}</div>
      <div class="kpi-sub" style="margin-top:8px;display:flex;flex-direction:column;gap:3px">
        <span style="color:var(--color-success)">Cuentas: ${fmtCurrency(totalCuentas, currency)}</span>
        <span style="color:var(--color-danger)">Deudas: &nbsp;${fmtCurrency(totalDeudas, currency)}</span>
      </div>
    </div>`;
}

function kpiCard(label, value, currency, cls = '', sub = '') {
  return `
    <div class="kpi-card">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value ${cls}">${fmtCurrency(value, currency)}</div>
      ${sub ? `<div class="kpi-sub">${sub}</div>` : ''}
    </div>`;
}

function accountsCard(accounts) {
  const rows = accounts.slice(0, 7).map(a => `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--border-muted)">
      <div>
        <div style="font-size:0.8125rem;font-weight:500">${sanitize(a.name)}</div>
        <div style="font-size:0.72rem;color:var(--text-soft)">${sanitize(a.country ?? a.type ?? '')}</div>
      </div>
      <span class="amount ${amountClass(a.balance)}" style="font-size:0.8125rem">
        ${fmtCurrency(a.balance ?? 0, a.currency?.code ?? 'COP')}
      </span>
    </div>`).join('');

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Cuentas</span>
        <a class="btn btn-ghost btn-sm" data-link="/accounts">Ver todas</a>
      </div>
      <div class="card-body">
        ${rows || '<div class="empty-state" style="padding:20px"><p>Sin cuentas</p></div>'}
      </div>
    </div>`;
}

function recentTxCard(txList) {
  const rows = txList.slice(0, 9).map(tx => {
    const isIncome = (tx.amount ?? 0) >= 0;
    const sign = isIncome ? '+' : '-';
    const cls  = isIncome ? 'positive' : 'negative';
    return `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--border-muted)">
        <div style="min-width:0;flex:1;margin-right:8px">
          <div style="font-size:0.8125rem;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            ${sanitize(tx.payee_name || tx.memo || 'Sin descripción')}
          </div>
          <div style="font-size:0.72rem;color:var(--text-soft)">
            ${fmtDateShort(tx.date)} · ${sanitize(tx.category_name ?? 'Sin cat.')}
          </div>
        </div>
        <span class="amount ${cls}" style="font-size:0.8125rem;flex-shrink:0">
          ${sign}${fmtCurrency(Math.abs(tx.amount ?? 0), tx.currency?.code ?? 'COP')}
        </span>
      </div>`;
  }).join('');

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Transacciones Recientes</span>
        <a class="btn btn-ghost btn-sm" data-link="/transactions">Ver todas</a>
      </div>
      <div class="card-body">
        ${rows || '<div class="empty-state" style="padding:20px"><p>Sin transacciones</p></div>'}
      </div>
    </div>`;
}

function budgetCard(cats) {
  const rows = cats
    .filter(c => (c.assigned ?? 0) > 0)
    .slice(0, 8)
    .map(c => `
      <div style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px">
          <span style="font-weight:500">${sanitize(c.category_name)}</span>
          <span style="font-family:var(--font-mono);color:var(--text-secondary)">
            ${fmtCurrency(Math.abs(c.activity ?? 0), 'COP')} / ${fmtCurrency(c.assigned ?? 0, 'COP')}
          </span>
        </div>
        ${progressBar(Math.abs(c.activity ?? 0), c.assigned ?? 0)}
      </div>`).join('');

  return `
    <div class="card" style="margin-bottom:20px">
      <div class="card-header">
        <span class="card-title">Presupuesto del Mes</span>
        <a class="btn btn-ghost btn-sm" data-link="/budget">Ver completo</a>
      </div>
      <div class="card-body">
        ${rows || '<div class="empty-state" style="padding:20px"><p>Sin presupuesto configurado</p></div>'}
      </div>
    </div>`;
}

function debtsCard(debts) {
  const rows = debts.slice(0, 5).map(d => `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--border-muted)">
      <div>
        <div style="font-size:0.8125rem;font-weight:500">${sanitize(d.name)}</div>
        <div style="font-size:0.72rem;color:var(--text-soft)">
          ${d.interest_rate != null ? d.interest_rate.toFixed(1) + '% EA' : d.debt_type ?? '—'}
        </div>
      </div>
      <span class="amount negative" style="font-size:0.8125rem">
        ${fmtCurrency(d.current_balance ?? d.balance ?? 0, d.currency_code ?? 'COP')}
      </span>
    </div>`).join('');

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Resumen de Deudas</span>
        <a class="btn btn-ghost btn-sm" data-link="/debts">Ver deudas</a>
      </div>
      <div class="card-body">${rows}</div>
    </div>`;
}

function bindEvents(container, accounts) {
  container.querySelector('#btnQuickAdd')?.addEventListener('click', () => {
    openQuickAdd(accounts);
  });
}

function openQuickAdd(accounts) {
  const currencies = ['COP', 'USD'];

  openModal({
    title: 'Nueva Transacción',
    size: 'md',
    content: `
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label required">Fecha</label>
          <input type="date" id="qa-date" value="${new Date().toISOString().split('T')[0]}">
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
      <div class="form-group" style="margin-bottom:16px">
        <label class="form-label required">Cuenta</label>
        <select id="qa-account">
          <option value="">— seleccionar —</option>
          ${accounts.map(a => `<option value="${a.id}">${sanitize(a.name)}</option>`).join('')}
        </select>
      </div>
      <div class="form-group" style="margin-bottom:16px">
        <label class="form-label">Descripción / Beneficiario</label>
        <input type="text" id="qa-payee" placeholder="Ej: Supermercado">
      </div>
    `,
    submitLabel: 'Guardar',
    onSubmit: async (body) => {
      const date     = body.querySelector('#qa-date').value;
      const amount   = parseFloat(body.querySelector('#qa-amount').value);
      const currency = body.querySelector('#qa-currency').value;
      const accountId= body.querySelector('#qa-account').value;
      const txType   = body.querySelector('#qa-type').value;
      const payee    = body.querySelector('#qa-payee').value.trim();

      if (!date || !amount || !accountId) throw new Error('Fecha, monto y cuenta son obligatorios');

      const currencyIdMap = { COP: 1, USD: 2 };
      await api.transactions.create({
        date, amount, currency_id: currencyIdMap[currency] ?? 1,
        account_id: parseInt(accountId),
        type: txType, payee_name: payee || undefined,
      });
      toast.success('Transacción guardada');
    },
  });
}
