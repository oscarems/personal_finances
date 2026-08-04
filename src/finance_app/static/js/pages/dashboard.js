import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, fmtDateShort, sanitize, amountClass, progressBar, optional } from '../utils.js';
import { toast } from '../components/toast.js';
import { openModal } from '../components/modal.js';

export const title = 'Dashboard';

export async function mount(container) {
  container.innerHTML = skeletonHtml();
  try {
    const [accounts, txResp, budget, debts, fxData, patrimonioData, cashflow, savingsRate, netWorthData, goals, financialHealth] = await Promise.all([
      api.accounts.list(),
      api.transactions.list({ limit: 10 }),
      optional(api.budgets.current(), null, 'Presupuesto'),
      optional(api.debts.list(), [], 'Deudas'),
      api.exchangeRates.current(),
      optional(api.patrimonio.summary(), null, 'Patrimonio'),
      optional(api.reports.cashflowSummary(), null, 'Flujo de Caja'),
      optional(api.reports.savingsRate({ months: 3 }), null, 'Tasa de Ahorro'),
      optional(api.reports.netWorthTimeline(), [], 'Historial Patrimonio'),
      optional(api.goals.list(), [], 'Metas'),
      optional(api.reports.financialHealth(), null, 'Salud Financiera'),
    ]);
    const txList = Array.isArray(txResp) ? txResp : (txResp?.transactions ?? txResp?.items ?? []);
    const usdRate = fxData?.rate ?? fxData?.USD ?? null;
    if (usdRate === null) {
      // Exchange rate is primary data — show error and omit consolidated totals
      const partial = document.createElement('div');
      partial.innerHTML = `<div class="alert alert-danger mb-4">No se pudo obtener la tasa de cambio — los totales consolidados están ocultos.</div>`;
      container.innerHTML = renderPage(accounts, txList, budget, debts, null, null, cashflow, savingsRate, netWorthData, goals, financialHealth);
      container.insertBefore(partial.firstElementChild, container.firstElementChild);
    } else {
      container.innerHTML = renderPage(accounts, txList, budget, debts, usdRate, patrimonioData, cashflow, savingsRate, netWorthData, goals, financialHealth);
    }
    bindEvents(container, accounts, netWorthData);
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
    <div class="card" style="margin-bottom:20px">
      <div class="card-body"><div class="skeleton" style="height:40px;width:100%"></div></div>
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
      <div class="card"><div style="height:200px" class="skeleton"></div></div>
      <div class="card"><div style="height:200px" class="skeleton"></div></div>
    </div>`;
}

function renderPage(accounts, txList, budget, debts, usdRate, patrimonioData, cashflow, savingsRate, netWorthData, goals = [], financialHealth = null) {
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

  const expenseGroups = (budget?.groups ?? []).filter(g => !g.is_income);
  const expenseCats   = expenseGroups.flatMap(g => g.categories ?? []);

  const today = new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' });
  const todayCap = today.charAt(0).toUpperCase() + today.slice(1);

  // Consolidated (multi-currency) KPI cards require the exchange rate
  let consolidatedSection = '';
  if (usdRate !== null) {
    const patrimonioActivos = patrimonioData?.activos ?? [];
    const patrimonioActivosCOP = patrimonioActivos
      .filter(a => (a.currency?.code ?? 'COP') === 'COP')
      .reduce((s, a) => s + (a.valor_actual ?? 0), 0);
    const patrimonioActivosUSD = patrimonioActivos
      .filter(a => (a.currency?.code ?? 'COP') === 'USD')
      .reduce((s, a) => s + (a.valor_actual ?? 0), 0);

    const activosCOP  = totalSavingsCOP + totalSavingsUSD * usdRate + patrimonioActivosCOP + patrimonioActivosUSD * usdRate;
    const deudasCOP   = totalDebtsCOP   + totalDebtsUSD  * usdRate;
    const patrimonioNeto = activosCOP - deudasCOP;

    consolidatedSection = `
      <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr)">
        ${patrimonioBigCard(patrimonioNeto, activosCOP, deudasCOP, patrimonioActivosCOP + patrimonioActivosUSD * usdRate)}
        ${currencyCard('COP', totalSavingsCOP, totalDebtsCOP)}
        ${currencyCard('USD', totalSavingsUSD, totalDebtsUSD)}
      </div>
      ${cashflowSection(cashflow, usdRate)}`;
  } else {
    // No exchange rate: show per-currency cards without consolidated totals
    consolidatedSection = `
      <div class="kpi-grid" style="grid-template-columns:repeat(2,1fr)">
        ${currencyCard('COP', totalSavingsCOP, totalDebtsCOP)}
        ${currencyCard('USD', totalSavingsUSD, totalDebtsUSD)}
      </div>`;
  }

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

    ${consolidatedSection}

    <div class="section-grid cols-2" style="margin-bottom:20px">
      ${savingsRateCard(savingsRate)}
      ${netWorthChartCard(netWorthData)}
    </div>

    <div class="section-grid cols-2" style="margin-bottom:20px">
      ${accountsCard(accounts)}
      ${recentTxCard(txList)}
    </div>

    ${goals.filter(g => g.status !== 'achieved').length > 0 ? goalsWidget(goals.filter(g => g.status !== 'achieved')) : ''}
    ${budget && expenseCats.length > 0 ? budgetCard(expenseCats) : ''}
    ${debts.length > 0 ? debtsCard(debts) : ''}
  `;
}

function healthCard(fh) {
  if (!fh || !fh.scores) {
    return `
      <div class="card" style="margin-bottom:20px">
        <div class="card-header">
          <span class="card-title">Salud Financiera</span>
          <a class="btn btn-ghost btn-sm" data-link="/financial-health">Ver detalle</a>
        </div>
        <div class="card-body"><p class="empty-state">No se pudo calcular la salud financiera este mes</p></div>
      </div>`;
  }

  const { overall, grade, estado } = fh.scores;
  const ESTADO_META = {
    bueno:    { badge: 'badge-success', label: 'Buena',    dot: 'var(--fin-success)' },
    regular:  { badge: 'badge-warning', label: 'Regular',  dot: 'var(--fin-amber)' },
    critico:  { badge: 'badge-danger',  label: 'Crítica',  dot: 'var(--fin-danger)' },
  };
  const meta = ESTADO_META[estado] ?? ESTADO_META.regular;
  const topInsight = (fh.insights ?? []).find(i => i.kind === 'bad') ?? (fh.insights ?? [])[0];

  return `
    <div class="card" style="margin-bottom:20px">
      <div class="card-body">
        <div class="flex justify-between items-center" style="flex-wrap:wrap;gap:12px">
          <div class="flex items-center" style="gap:12px">
            <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${meta.dot};flex-shrink:0"></span>
            <div>
              <div style="font-size:0.8125rem;font-weight:600">Salud Financiera del Mes</div>
              <div class="text-soft" style="font-size:0.72rem">${topInsight ? sanitize(topInsight.message) : 'Sin observaciones destacadas'}</div>
            </div>
          </div>
          <div class="flex items-center" style="gap:10px">
            <span class="amount" style="font-size:1.4rem;font-weight:700">${overall.toFixed(1)}<span class="text-soft" style="font-size:0.8rem;font-weight:500">/100</span></span>
            <span class="badge ${meta.badge}">${meta.label} · ${grade}</span>
            <a class="btn btn-ghost btn-sm" data-link="/financial-health">Ver detalle</a>
          </div>
        </div>
      </div>
    </div>`;
}

function patrimonioBigCard(neto, activos, deudas, patrimonioActivosCOP) {
  const cls = neto >= 0 ? 'positive' : 'negative';
  return `
    <div class="kpi-card">
      <div class="kpi-label">Patrimonio Neto</div>
      <div class="kpi-value ${cls}">${fmtCurrency(neto, 'COP')}</div>
      <div class="kpi-sub kpi-sub-stack mt-2">
        <span class="text-success">Activos: ${fmtCurrency(activos, 'COP')}</span>
        ${patrimonioActivosCOP > 0 ? `<span class="text-success" style="opacity:0.7;font-size:0.72rem;padding-left:6px">incl. patrimonio: ${fmtCurrency(patrimonioActivosCOP, 'COP')}</span>` : ''}
        <span class="text-danger">Deudas: ${fmtCurrency(deudas, 'COP')}</span>
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
      <div class="kpi-sub kpi-sub-stack mt-2">
        <span class="text-success">Cuentas: ${fmtCurrency(totalCuentas, currency)}</span>
        <span class="text-danger">Deudas: &nbsp;${fmtCurrency(totalDeudas, currency)}</span>
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
    <div class="flex justify-between items-center" style="padding:9px 0;border-bottom:1px solid var(--fin-border)">
      <div>
        <div style="font-size:0.8125rem;font-weight:500">${sanitize(a.name)}</div>
        <div class="text-soft" style="font-size:0.72rem">${sanitize(a.country ?? a.type ?? '')}</div>
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
        ${rows || '<div class="empty-state"><p>Sin cuentas</p></div>'}
      </div>
    </div>`;
}

function recentTxCard(txList) {
  const rows = txList.slice(0, 9).map(tx => {
    const isIncome = (tx.amount ?? 0) >= 0;
    const sign = isIncome ? '+' : '-';
    const cls  = isIncome ? 'positive' : 'negative';
    return `
      <div class="flex justify-between items-center" style="padding:9px 0;border-bottom:1px solid var(--fin-border)">
        <div style="min-width:0;flex:1;margin-right:8px">
          <div style="font-size:0.8125rem;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            ${sanitize(tx.payee_name || tx.memo || 'Sin descripción')}
          </div>
          <div class="text-soft" style="font-size:0.72rem">
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
        ${rows || '<div class="empty-state"><p>Sin transacciones</p></div>'}
      </div>
    </div>`;
}

function budgetCard(cats) {
  const rows = cats
    .filter(c => (c.assigned ?? 0) > 0)
    .slice(0, 8)
    .map(c => `
      <div style="margin-bottom:10px">
        <div class="flex justify-between" style="font-size:0.8rem;margin-bottom:4px">
          <span style="font-weight:500">${sanitize(c.category_name)}</span>
          <span class="amount text-soft">
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
        ${rows || '<div class="empty-state"><p>Sin presupuesto configurado</p></div>'}
      </div>
    </div>`;
}

function debtsCard(debts) {
  const rows = debts.slice(0, 5).map(d => `
    <div class="flex justify-between items-center" style="padding:9px 0;border-bottom:1px solid var(--fin-border)">
      <div>
        <div style="font-size:0.8125rem;font-weight:500">${sanitize(d.name)}</div>
        <div class="text-soft" style="font-size:0.72rem">
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

function cashflowSection(cf, usdRate = 4200) {
  if (!cf) return '';

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

  const inTotal  = inCOP  + inUSD  * usdRate;
  const exTotal  = exNoSavCOP + exNoSavUSD * usdRate;
  const savTotal = savCOP + savUSD * usdRate;
  const balTotal = balCOP + balUSD * usdRate;

  const hasSavings = savCOP > 0 || savUSD > 0;
  const monthLabel = new Date().toLocaleDateString('es-CO', { month: 'long', year: 'numeric' });

  function cell(value, currency, cls = '', bold = false) {
    const style = `font-family:var(--font-mono);font-size:0.8rem;text-align:right;${bold ? 'font-weight:700;' : ''}`;
    return `<td class="${cls}" style="${style}">${fmtCurrency(value, currency)}</td>`;
  }

  function row(label, cop, usd, total, cls = '', bold = false) {
    const labelStyle = `font-size:0.8125rem;padding:9px 0;color:${bold ? 'var(--fin-ink)' : 'var(--fin-ink-2)'};${bold ? 'font-weight:600;' : ''}`;
    return `
      <tr style="border-bottom:1px solid var(--fin-border)">
        <td style="${labelStyle}">${label}</td>
        ${cell(cop,   'COP', cls, bold)}
        ${cell(usd,   'USD', cls, bold)}
        ${cell(total, 'COP', cls, bold)}
      </tr>`;
  }

  function dividerRow() {
    return `<tr><td colspan="4" style="padding:0"><div style="border-top:2px solid var(--fin-border);margin:2px 0"></div></td></tr>`;
  }

  const balCls = balTotal >= 0 ? 'positive' : 'negative';

  return `
    <div class="card" style="margin-bottom:0">
      <div class="card-header">
        <span class="card-title">Flujo del mes · ${monthLabel}</span>
        <span class="text-soft" style="font-size:0.72rem">Total en COP · TRM ${fmtCurrency(usdRate, 'COP')}</span>
      </div>
      <div class="card-body" style="padding-top:4px;overflow-x:auto">
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr>
              <th class="text-soft" style="text-align:left;font-size:0.7rem;font-weight:500;padding-bottom:6px"></th>
              <th class="text-soft" style="text-align:right;font-size:0.7rem;font-weight:500;padding-bottom:6px">COP</th>
              <th class="text-soft" style="text-align:right;font-size:0.7rem;font-weight:500;padding-bottom:6px">USD</th>
              <th class="text-soft" style="text-align:right;font-size:0.7rem;font-weight:500;padding-bottom:6px">Total (COP)</th>
            </tr>
          </thead>
          <tbody>
            ${row('↑ Ingresos',  inCOP,      inUSD,      inTotal,  'positive')}
            ${row('↓ Gastos',    exNoSavCOP, exNoSavUSD, exTotal,  'negative')}
            ${hasSavings ? row('💰 Ahorros', savCOP, savUSD, savTotal, '') : ''}
            ${dividerRow()}
            ${row('Balance',     balCOP,     balUSD,     balTotal, balCls, true)}
          </tbody>
        </table>
      </div>
    </div>`;
}

function savingsRateCard(sr) {
  if (!sr || !sr.monthly || sr.monthly.length === 0) {
    return `
      <div class="card">
        <div class="card-header"><span class="card-title">Tasa de Ahorro</span></div>
        <div class="card-body"><p class="empty-state">Sin datos de ingresos aún</p></div>
      </div>`;
  }

  const months = sr.monthly.slice(-3);
  const avg = sr.average_savings_rate ?? 0;
  const avgCls = avg >= 20 ? 'positive' : avg >= 10 ? '' : 'negative';

  const rows = months.map(m => {
    const cls = m.savings_rate >= 20 ? 'positive' : m.savings_rate >= 10 ? '' : 'negative';
    const bar = Math.max(0, Math.min(100, m.savings_rate));
    return `
      <div style="margin-bottom:12px">
        <div class="flex justify-between mb-1">
          <span class="text-soft" style="font-size:0.78rem">${m.month_name}</span>
          <span class="amount ${cls}" style="font-size:0.78rem">${m.savings_rate.toFixed(1)}%</span>
        </div>
        <div style="height:5px;background:var(--fin-border);border-radius:3px">
          <div style="height:100%;width:${bar}%;background:${m.savings_rate >= 20 ? 'var(--fin-success)' : m.savings_rate >= 10 ? 'var(--fin-amber)' : 'var(--fin-danger)'};border-radius:3px;transition:width .4s"></div>
        </div>
      </div>`;
  }).join('');

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Tasa de Ahorro</span>
        <a class="btn btn-ghost btn-sm" data-link="/income">Ver detalle</a>
      </div>
      <div class="card-body">
        <div style="text-align:center;margin-bottom:16px">
          <div class="kpi-label">Promedio trimestre</div>
          <div class="kpi-value ${avgCls}" style="font-size:2rem">${avg.toFixed(1)}%</div>
          <div class="text-soft mt-1" style="font-size:0.72rem">Meta recomendada: ≥ 20%</div>
        </div>
        ${rows}
      </div>
    </div>`;
}

function netWorthChartCard(data) {
  if (!data || data.length === 0) {
    return `
      <div class="card">
        <div class="card-header"><span class="card-title">Patrimonio Neto</span></div>
        <div class="card-body"><p class="empty-state">El historial se construye mes a mes al abrir el dashboard</p></div>
      </div>`;
  }

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Patrimonio Neto · Evolución</span>
      </div>
      <div class="card-body" style="padding-top:8px">
        <canvas id="netWorthChart" style="max-height:200px"></canvas>
      </div>
    </div>`;
}

function renderNetWorthChart(container, data) {
  if (!data || data.length === 0) return;
  const ctx = container.querySelector('#netWorthChart');
  if (!ctx || !window.Chart) return;

  const theme = window.getChartTheme ? window.getChartTheme() : {};
  const palette = window.CHART_PALETTE ?? ['#316342','#BA1A1A','#735142','#3B5B66','#6B4226','#4C6B3F','#8A5A44','#7A6A53'];
  const labels = data.map(d => d.month);
  const nets   = data.map(d => d.net_cop);

  new window.Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Patrimonio Neto (COP)',
        data: nets,
        borderColor: palette[1],
        backgroundColor: palette[1].replace(/^#/, 'rgba(').replace(/(.{2})(.{2})(.{2})$/, (_, r, g, b) =>
          `${parseInt(r,16)},${parseInt(g,16)},${parseInt(b,16)},0.08)`),
        borderWidth: 2,
        pointRadius: data.length === 1 ? 5 : 3,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.y;
              return ' ' + new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(v);
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: theme.tickColor ?? '#717971', maxTicksLimit: 6 }, grid: { color: theme.gridColor ?? 'rgba(28,27,23,0.08)' } },
        y: {
          ticks: {
            color: theme.tickColor ?? '#717971',
            callback: v => {
              if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(1) + 'B';
              if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + 'M';
              if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(0) + 'K';
              return v;
            },
          },
          grid: { color: theme.gridColor ?? 'rgba(28,27,23,0.08)' },
        },
      },
    },
  });
}

function goalsWidget(goals) {
  const top = goals.slice(0, 4);
  const rows = top.map(g => {
    const current  = g.current_amount ?? 0;
    const target   = g.target_amount ?? 0;
    const currency = g.currency_code ?? 'COP';
    const pct      = target > 0 ? Math.min(100, (current / target) * 100) : 0;
    const reqMonth = g.required_per_month ?? g.monthly_required ?? 0;
    const barColor = pct >= 70 ? 'var(--fin-success)' : pct >= 35 ? 'var(--fin-amber)' : 'var(--fin-danger)';
    return `
      <div style="margin-bottom:14px">
        <div class="flex justify-between items-center mb-1">
          <span style="font-size:0.8125rem;font-weight:500">🎯 ${sanitize(g.name)}</span>
          <span class="amount text-soft" style="font-size:0.75rem">${pct.toFixed(0)}%</span>
        </div>
        <div style="height:5px;background:var(--fin-border);border-radius:3px;margin-bottom:4px">
          <div style="height:100%;width:${pct}%;background:${barColor};border-radius:3px;transition:width .4s"></div>
        </div>
        <div class="flex justify-between text-soft" style="font-size:0.72rem">
          <span>${fmtCurrency(current, currency)} de ${fmtCurrency(target, currency)}</span>
          ${reqMonth > 0 ? `<span>${fmtCurrency(reqMonth, currency)}/mes</span>` : ''}
        </div>
      </div>`;
  }).join('');

  return `
    <div class="card" style="margin-bottom:20px">
      <div class="card-header">
        <span class="card-title">Metas de Ahorro</span>
        <a class="btn btn-ghost btn-sm" data-link="/goals">Ver todas</a>
      </div>
      <div class="card-body">${rows}</div>
    </div>`;
}

function bindEvents(container, accounts, netWorthData) {
  container.querySelector('#btnQuickAdd')?.addEventListener('click', () => {
    openQuickAdd(accounts);
  });
  renderNetWorthChart(container, netWorthData);
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
