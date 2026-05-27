import * as api from '../api/client.js';
import { fmtCurrency, fmtNumber, sanitize, currentMonth, prevMonth, fmtMonthLabel } from '../utils.js';

export const title = 'Reportes';

let _month = currentMonth();
let _chart = null;
let _incomeChart = null;
let _currencyId = 1;
let _currencyCode = 'COP';
let _currencies = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  _currencies = await api.currencies.list().catch(() => [{ id: 1, code: 'COP' }, { id: 2, code: 'USD' }]);
  renderShell(container);
  await loadData(container);
}

export function cleanup() {
  _chart?.destroy();
  _chart = null;
  _incomeChart?.destroy();
  _incomeChart = null;
}

function renderShell(container) {
  const currencyOptions = _currencies.map(c =>
    `<option value="${c.id}" ${c.id === _currencyId ? 'selected' : ''}>${c.code}</option>`
  ).join('');

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text"><h1>Reportes</h1></div>
      <div class="page-header-actions" style="display:flex;align-items:center;gap:12px">
        <div style="display:flex;align-items:center;gap:6px">
          <label style="font-size:0.8rem;color:var(--text-secondary)">Moneda</label>
          <select id="rptCurrency" class="input-field" style="min-width:72px;padding:4px 8px;height:32px;font-size:0.8125rem">
            ${currencyOptions}
          </select>
        </div>
        <div class="month-nav">
          <button class="btn btn-ghost btn-sm" id="rptPrev">‹</button>
          <span class="month-nav-label" id="rptMonthLabel">${fmtMonthLabel(_month)}</span>
          <button class="btn btn-ghost btn-sm" id="rptNext">›</button>
        </div>
      </div>
    </div>
    <div class="kpi-grid" id="rpt-kpis"></div>
    <div class="section-grid cols-2" style="margin-bottom:24px">
      <div class="card">
        <div class="card-header"><span class="card-title">Gasto por Categoría</span></div>
        <div class="card-body" style="height:280px;position:relative">
          <canvas id="spendChart"></canvas>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Ingresos vs Gastos</span></div>
        <div class="card-body" style="height:280px;position:relative">
          <canvas id="incomeChart"></canvas>
        </div>
      </div>
    </div>
    <div class="card" id="rpt-detail-card">
      <div class="card-header"><span class="card-title">Detalle por Categoría</span></div>
      <div class="card-body" id="rpt-detail"></div>
    </div>
  `;

  container.querySelector('#rptPrev').addEventListener('click', async () => {
    _month = prevMonth(_month);
    container.querySelector('#rptMonthLabel').textContent = fmtMonthLabel(_month);
    await loadData(container);
  });
  container.querySelector('#rptNext').addEventListener('click', async () => {
    const [y, m] = _month.split('-').map(Number);
    const next = new Date(y, m);
    _month = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`;
    container.querySelector('#rptMonthLabel').textContent = fmtMonthLabel(_month);
    await loadData(container);
  });
  container.querySelector('#rptCurrency').addEventListener('change', async (e) => {
    const selected = _currencies.find(c => c.id === parseInt(e.target.value));
    if (selected) {
      _currencyId = selected.id;
      _currencyCode = selected.code;
    }
    await loadData(container);
  });
}

async function loadData(container) {
  const kpisEl  = container.querySelector('#rpt-kpis');
  const detailEl= container.querySelector('#rpt-detail');
  if (kpisEl) kpisEl.innerHTML = '<div class="skeleton" style="height:80px;grid-column:1/-1"></div>';
  if (detailEl) detailEl.innerHTML = '<div class="page-loading" style="min-height:100px"><div class="spinner"></div></div>';

  try {
    const [spending, income] = await Promise.all([
      api.reports.spending({ month: _month, currency_id: _currencyId }).catch(() => null),
      api.reports.income({ month: _month, currency_id: _currencyId }).catch(() => null),
    ]);

    const cats      = spending?.categories ?? spending?.by_category ?? [];
    const totalExp  = spending?.total ?? cats.reduce((s, c) => s + (c.spent ?? c.amount ?? 0), 0);
    const totalInc  = income?.total_income ?? income?.income ?? 0;
    const netFlow   = totalInc - totalExp;
    const saveRate  = totalInc > 0 ? (netFlow / totalInc) * 100 : 0;
    const fmt       = v => fmtCurrency(v, _currencyCode);

    if (kpisEl) {
      kpisEl.innerHTML = `
        <div class="kpi-card">
          <div class="kpi-label">Ingresos</div>
          <div class="kpi-value positive">${fmt(totalInc)}</div>
          <div class="kpi-sub">${_currencyCode} · ${fmtMonthLabel(_month)}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Gastos</div>
          <div class="kpi-value negative">${fmt(totalExp)}</div>
          <div class="kpi-sub">${_currencyCode} · ${fmtMonthLabel(_month)}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Flujo Neto</div>
          <div class="kpi-value ${netFlow >= 0 ? 'positive' : 'negative'}">${fmt(netFlow)}</div>
          <div class="kpi-sub">${_currencyCode} · ${fmtMonthLabel(_month)}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Tasa de Ahorro</div>
          <div class="kpi-value ${saveRate >= 20 ? 'positive' : saveRate >= 10 ? 'warning' : 'negative'}">${saveRate.toFixed(1)}%</div>
          <div class="kpi-sub">ingreso − gasto / ingreso</div>
        </div>
      `;
    }

    // Spending donut chart
    _chart?.destroy();
    const spendCtx = container.querySelector('#spendChart');
    if (spendCtx && cats.length) {
      const sorted = [...cats].sort((a, b) => (b.spent ?? b.amount ?? 0) - (a.spent ?? a.amount ?? 0)).slice(0, 10);
      const COLORS = ['#D97706','#059669','#0891B2','#7C3AED','#DB2777','#EA580C','#65A30D','#0284C7','#9333EA','#E11D48'];
      _chart = new Chart(spendCtx, {
        type: 'doughnut',
        data: {
          labels: sorted.map(c => c.category_name ?? c.name),
          datasets: [{ data: sorted.map(c => c.spent ?? c.amount ?? 0), backgroundColor: COLORS, borderWidth: 2, borderColor: 'var(--bg-surface)' }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { position: 'right', labels: { font: { size: 11 }, color: 'var(--text-secondary)', padding: 12 } },
            tooltip: { callbacks: { label: (ctx) => ` ${fmt(ctx.raw)}` } },
          },
        },
      });
    }

    // Income vs Expenses bar chart
    _incomeChart?.destroy();
    const incomeCtx = container.querySelector('#incomeChart');
    if (incomeCtx) {
      _incomeChart = new Chart(incomeCtx, {
        type: 'bar',
        data: {
          labels: ['Ingresos', 'Gastos'],
          datasets: [{
            data: [totalInc, totalExp],
            backgroundColor: ['rgba(5,150,105,0.7)', 'rgba(220,38,38,0.7)'],
            borderRadius: 6,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: 'var(--border-muted)' }, ticks: { callback: v => fmt(v), font: { size: 10 }, color: 'var(--text-soft)' } },
            x: { grid: { display: false }, ticks: { color: 'var(--text-secondary)' } },
          },
        },
      });
    }

    if (detailEl) {
      const sorted = [...cats].sort((a, b) => (b.spent ?? b.amount ?? 0) - (a.spent ?? a.amount ?? 0));
      detailEl.innerHTML = sorted.length ? `
        <table>
          <thead>
            <tr>
              <th>Categoría</th>
              <th class="td-right">Gastado (${_currencyCode})</th>
              <th class="td-right">% del Total</th>
              <th style="width:25%">Distribución</th>
            </tr>
          </thead>
          <tbody>
            ${sorted.map(c => {
              const amt = c.spent ?? c.amount ?? 0;
              const pct = totalExp > 0 ? (amt / totalExp) * 100 : 0;
              return `
                <tr>
                  <td style="font-size:0.8125rem;font-weight:500">${sanitize(c.category_name ?? c.name ?? '—')}</td>
                  <td class="td-right td-mono" style="font-size:0.8125rem">${fmt(amt)}</td>
                  <td class="td-right" style="font-size:0.8125rem;color:var(--text-secondary)">${pct.toFixed(1)}%</td>
                  <td>
                    <div class="progress-wrap" style="min-width:80px">
                      <div class="progress-fill ok" style="width:${pct}%"></div>
                    </div>
                  </td>
                </tr>`;
            }).join('')}
          </tbody>
        </table>
      ` : '<div class="empty-state"><p>Sin datos de gasto para este mes</p></div>';
    }
  } catch (err) {
    if (kpisEl) kpisEl.innerHTML = `<div class="alert alert-danger" style="grid-column:1/-1">${sanitize(err.message)}</div>`;
  }
}
