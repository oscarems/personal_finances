import * as api from '../api/client.js';
import { fmtCurrency, sanitize } from '../utils.js';

export const title = 'Flujo de Caja';

const HORIZONS = [30, 60, 90];

export async function mount(container) {
  let horizon = 90;
  let currency = 'COP';

  container.innerHTML = skeleton();

  async function load() {
    container.innerHTML = skeleton();
    try {
      const [forecast, upcoming] = await Promise.all([
        api.cashFlow.forecast({ days: horizon, currency_code: currency }),
        api.cashFlow.upcoming({ days: 14 }),
      ]);
      container.innerHTML = renderPage(forecast, upcoming, horizon, currency);
      renderChart(container, forecast);
      bindEvents(container);
    } catch (err) {
      container.innerHTML = `<div class="alert alert-danger">Error: ${sanitize(err.message)}</div>`;
    }
  }

  function bindEvents(el) {
    el.querySelectorAll('[data-horizon]').forEach(btn => {
      btn.addEventListener('click', () => {
        horizon = parseInt(btn.dataset.horizon);
        load();
      });
    });
    el.querySelectorAll('[data-currency]').forEach(btn => {
      btn.addEventListener('click', () => {
        currency = btn.dataset.currency;
        load();
      });
    });
  }

  load();
}

function fmt(amount) {
  return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(amount);
}

function daysUntilNegative(dailyBalance) {
  for (let i = 0; i < dailyBalance.length; i++) {
    if (dailyBalance[i].balance < 0) return i + 1;
  }
  return null;
}

function renderPage(forecast, upcoming, horizon, currency) {
  if (!forecast) return `<div class="alert alert-warning">No hay datos de proyección disponibles.</div>`;

  const { starting_balance_cop, summary, daily_balance = [], events = [] } = forecast;
  const balance30  = daily_balance[29]?.balance ?? starting_balance_cop;
  const balance60  = daily_balance[59]?.balance ?? daily_balance[daily_balance.length - 1]?.balance ?? starting_balance_cop;
  const balance90  = daily_balance[89]?.balance ?? daily_balance[daily_balance.length - 1]?.balance ?? starting_balance_cop;
  const daysNeg    = daysUntilNegative(daily_balance);

  const negKpiClass = daysNeg ? 'kpi-card danger' : 'kpi-card positive';
  const negKpiVal   = daysNeg ? `En ${daysNeg} días` : 'Sin riesgo';
  const negKpiLabel = daysNeg ? '⚠ Balance negativo' : 'Balance negativo';

  const upcomingEvents = (upcoming?.events ?? []).slice(0, 15);

  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1 class="page-title">Flujo de Caja</h1>
        <p class="page-subtitle">Proyección de balance para los próximos ${horizon} días</p>
      </div>
      <div class="page-actions" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <div class="btn-group">
          ${HORIZONS.map(h => `<button class="btn ${h===horizon?'btn-primary':'btn-ghost'} btn-sm" data-horizon="${h}">${h}d</button>`).join('')}
        </div>
        <div class="btn-group">
          ${['COP','USD'].map(c => `<button class="btn ${c===currency?'btn-primary':'btn-ghost'} btn-sm" data-currency="${c}">${c}</button>`).join('')}
        </div>
      </div>
    </div>

    <div class="kpi-grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))">
      <div class="kpi-card">
        <div class="kpi-label">Balance Actual</div>
        <div class="kpi-value">${fmt(starting_balance_cop)}</div>
        <div class="kpi-sub">Cuentas de ahorro/corriente</div>
      </div>
      <div class="kpi-card ${balance30 < 0 ? 'danger' : ''}">
        <div class="kpi-label">En 30 días</div>
        <div class="kpi-value">${fmt(balance30)}</div>
      </div>
      <div class="kpi-card ${balance60 < 0 ? 'danger' : ''}">
        <div class="kpi-label">En 60 días</div>
        <div class="kpi-value">${fmt(balance60)}</div>
      </div>
      <div class="${negKpiClass}">
        <div class="kpi-label">${negKpiLabel}</div>
        <div class="kpi-value">${negKpiVal}</div>
      </div>
    </div>

    <div class="section-grid cols-3" style="margin-bottom:16px">
      <div class="card" style="padding:12px 16px;text-align:center">
        <div style="color:var(--color-success);font-size:11px;text-transform:uppercase;letter-spacing:.05em">Ingresos proyectados</div>
        <div style="font-size:18px;font-weight:600;font-family:monospace;margin-top:4px">${fmt(summary?.total_income ?? 0)}</div>
      </div>
      <div class="card" style="padding:12px 16px;text-align:center">
        <div style="color:var(--color-danger);font-size:11px;text-transform:uppercase;letter-spacing:.05em">Gastos proyectados</div>
        <div style="font-size:18px;font-weight:600;font-family:monospace;margin-top:4px">${fmt(Math.abs(summary?.total_expense ?? 0))}</div>
      </div>
      <div class="card" style="padding:12px 16px;text-align:center">
        <div style="color:var(--color-text-muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em">Flujo neto</div>
        <div style="font-size:18px;font-weight:600;font-family:monospace;margin-top:4px;color:${(summary?.net ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}">${fmt(summary?.net ?? 0)}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom:24px">
      <div class="card-header"><h3 class="card-title">Balance proyectado</h3></div>
      <div style="padding:16px">
        <canvas id="cashFlowChart" style="width:100%;height:280px"></canvas>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><h3 class="card-title">Próximos eventos (14 días)</h3></div>
      ${upcomingEvents.length === 0
        ? '<div style="padding:24px;text-align:center;color:var(--color-text-muted)">No hay eventos próximos</div>'
        : `<div style="overflow-x:auto"><table class="data-table">
            <thead><tr><th>Fecha</th><th>Descripción</th><th>Tipo</th><th style="text-align:right">Monto</th></tr></thead>
            <tbody>
              ${upcomingEvents.map(ev => {
                const isIncome = ev.type === 'income';
                const badge = ev.type === 'debt_payment' ? 'badge-warning' : isIncome ? 'badge-success' : 'badge-danger';
                const label = ev.type === 'debt_payment' ? 'Deuda' : isIncome ? 'Ingreso' : 'Gasto';
                return `<tr>
                  <td style="white-space:nowrap">${ev.date}</td>
                  <td>${sanitize(ev.label)}</td>
                  <td><span class="badge ${badge}">${label}</span></td>
                  <td style="text-align:right;font-family:monospace;color:${isIncome ? 'var(--color-success)' : 'var(--color-danger)'}">
                    ${isIncome ? '+' : '-'}${fmt(Math.abs(ev.amount_cop ?? ev.amount_signed ?? 0))}
                  </td>
                </tr>`;
              }).join('')}
            </tbody>
          </table></div>`
      }
    </div>
  `;
}

function renderChart(container, forecast) {
  if (!forecast?.daily_balance?.length) return;

  const canvas = container.querySelector('#cashFlowChart');
  if (!canvas) return;

  const labels = forecast.daily_balance.map(d => d.date.slice(5));
  const data   = forecast.daily_balance.map(d => d.balance);

  function doRender(Chart) {
    new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Balance COP',
          data,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.08)',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(ctx.raw),
            },
          },
        },
        scales: {
          x: {
            ticks: { color: '#94a3b8', maxTicksLimit: 10, font: { size: 11 } },
            grid: { color: 'rgba(148,163,184,0.08)' },
          },
          y: {
            ticks: {
              color: '#94a3b8',
              font: { size: 11 },
              callback: v => new Intl.NumberFormat('es-CO', { notation: 'compact', currency: 'COP', style: 'currency', maximumFractionDigits: 0 }).format(v),
            },
            grid: { color: 'rgba(148,163,184,0.08)' },
          },
        },
      },
    });
  }

  if (window.Chart) {
    doRender(window.Chart);
  } else {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js';
    script.onload = () => doRender(window.Chart);
    document.head.appendChild(script);
  }
}

function skeleton() {
  return `
    <div class="page-header">
      <div class="skeleton" style="height:26px;width:200px"></div>
    </div>
    <div class="kpi-grid">
      ${[0,1,2,3].map(() => `<div class="kpi-card"><div class="skeleton" style="height:60px"></div></div>`).join('')}
    </div>
    <div class="card"><div class="skeleton" style="height:300px;margin:16px"></div></div>
  `;
}
