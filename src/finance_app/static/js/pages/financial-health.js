import * as api from '../api/client.js';
import { fmtCurrency, fmtPercent, sanitize, currentMonth, fmtMonthLabel, prevMonth } from '../utils.js';

export const title = 'Salud Financiera';

let _month = currentMonth();
let _chart = null;

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  await load(container);
}

export function cleanup() { _chart?.destroy(); _chart = null; }

async function load(container) {
  try {
    const data = await api.reports.financialHealth({ month: _month });
    render(container, data);
  } catch (err) {
    container.innerHTML = `
      <div class="page-header"><div class="page-header-text"><h1>Salud Financiera</h1></div></div>
      <div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container, data) {
  const score      = data?.score ?? data?.health_score ?? null;
  const needs      = data?.needs_pct  ?? data?.needs ?? 0;
  const wants      = data?.wants_pct  ?? data?.wants ?? 0;
  const savings    = data?.savings_pct ?? data?.savings ?? 0;
  const totalInc   = data?.total_income ?? 0;

  const scoreColor = score == null ? 'var(--text-soft)' : score >= 80 ? 'var(--color-success)' : score >= 60 ? 'var(--color-warning)' : 'var(--color-danger)';

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Salud Financiera</h1>
        <p>Regla 50/30/20 · ${fmtMonthLabel(_month)}</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-ghost btn-sm" id="fhPrev">‹ Mes anterior</button>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 280px;gap:24px;margin-bottom:24px">
      <div class="section-grid cols-auto">
        ${ruleCard('Necesidades', needs, 50, data?.needs_amount ?? 0, 'Vivienda, alimentos, transporte, servicios', 'accent')}
        ${ruleCard('Deseos', wants, 30, data?.wants_amount ?? 0, 'Entretenimiento, restaurantes, hobbies', 'warning')}
        ${ruleCard('Ahorro / Deudas', savings, 20, data?.savings_amount ?? 0, 'Ahorros, inversiones, pago de deudas', 'success')}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Puntuación</span></div>
        <div class="card-body" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;min-height:180px">
          ${score != null ? `
            <div style="font-family:var(--font-display);font-size:3.5rem;font-weight:700;color:${scoreColor};line-height:1">${score}</div>
            <div style="font-size:0.875rem;color:var(--text-secondary)">/100</div>
            <div style="font-size:0.8rem;color:var(--text-soft);text-align:center;max-width:160px">
              ${score >= 80 ? '¡Excelente salud financiera!' : score >= 60 ? 'Buena gestión, hay margen de mejora' : 'Hay oportunidades de mejora'}
            </div>
          ` : '<div style="color:var(--text-soft)">Sin datos</div>'}
        </div>
      </div>
    </div>

    ${data?.categories?.length ? categoryBreakdown(data.categories) : ''}

    ${totalInc > 0 ? `
      <div class="card">
        <div class="card-header"><span class="card-title">Distribución Real vs. Recomendada (50/30/20)</span></div>
        <div class="card-body" style="height:260px;position:relative">
          <canvas id="fhChart"></canvas>
        </div>
      </div>` : ''}
  `;

  container.querySelector('#fhPrev')?.addEventListener('click', async () => {
    _month = prevMonth(_month);
    await load(container);
  });

  const ctx = container.querySelector('#fhChart');
  if (ctx && totalInc > 0) {
    _chart?.destroy();
    _chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Necesidades', 'Deseos', 'Ahorro'],
        datasets: [
          {
            label: 'Real (%)',
            data: [needs * 100, wants * 100, savings * 100],
            backgroundColor: ['rgba(8,145,178,0.7)', 'rgba(217,119,6,0.7)', 'rgba(5,150,105,0.7)'],
            borderRadius: 6,
          },
          {
            label: 'Recomendado (%)',
            data: [50, 30, 20],
            backgroundColor: ['rgba(8,145,178,0.2)', 'rgba(217,119,6,0.2)', 'rgba(5,150,105,0.2)'],
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { font: { size: 11 }, color: 'var(--text-secondary)' } } },
        scales: {
          y: { grid: { color: 'var(--border-muted)' }, ticks: { callback: v => v + '%', color: 'var(--text-soft)', font: { size: 10 } } },
          x: { grid: { display: false }, ticks: { color: 'var(--text-secondary)' } },
        },
      },
    });
  }
}

function ruleCard(label, actual, target, amount, description, colorKey) {
  const pctActual = (actual * 100);
  const diff = pctActual - target;
  const isGood = Math.abs(diff) <= 5;
  const color = colorKey === 'accent' ? 'var(--color-accent)' : colorKey === 'success' ? 'var(--color-success)' : 'var(--color-warning)';

  return `
    <div class="card">
      <div style="padding:16px 20px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span style="font-weight:600;font-size:0.9375rem">${label}</span>
          <span class="badge ${isGood ? 'badge-success' : Math.abs(diff) <= 10 ? 'badge-warning' : 'badge-danger'}">
            ${isGood ? '✓ OK' : diff > 0 ? `+${diff.toFixed(0)}%` : `${diff.toFixed(0)}%`}
          </span>
        </div>
        <div style="font-family:var(--font-mono);font-size:1.75rem;font-weight:700;color:${color};margin-bottom:4px">
          ${pctActual.toFixed(1)}%
        </div>
        <div style="font-size:0.75rem;color:var(--text-soft);margin-bottom:12px">Meta: ${target}% · ${fmtCurrency(amount, 'COP')}</div>
        <div style="font-size:0.75rem;color:var(--text-secondary)">${description}</div>
        <div class="progress-wrap" style="margin-top:12px">
          <div class="progress-fill ${isGood ? 'ok' : 'warning'}" style="width:${Math.min(100, pctActual)}%"></div>
        </div>
      </div>
    </div>`;
}

function categoryBreakdown(cats) {
  return `
    <div class="card" style="margin-bottom:24px">
      <div class="card-header"><span class="card-title">Desglose por Categoría</span></div>
      <div class="card-body">
        <table>
          <thead>
            <tr>
              <th>Categoría</th>
              <th>Tipo</th>
              <th class="td-right">Gasto</th>
              <th class="td-right">% Ingreso</th>
            </tr>
          </thead>
          <tbody>
            ${cats.map(c => `
              <tr>
                <td style="font-size:0.8125rem;font-weight:500">${sanitize(c.category_name ?? c.name ?? '—')}</td>
                <td><span class="badge badge-neutral" style="font-size:0.65rem">${sanitize(c.budget_category ?? c.type ?? '—')}</span></td>
                <td class="td-right td-mono" style="font-size:0.8125rem">${fmtCurrency(c.amount ?? c.spent ?? 0, 'COP')}</td>
                <td class="td-right" style="font-size:0.8rem;color:var(--text-secondary)">${((c.pct ?? c.percentage ?? 0) * 100).toFixed(1)}%</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>`;
}
