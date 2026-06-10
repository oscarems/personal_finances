import * as api from '../api/client.js';
import { fmtCurrency, sanitize } from '../utils.js';

export const title = 'Simulador de Deudas';

export async function mount(container) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text"><h1>Simulador de Estrategias</h1></div>
    </div>
    <div style="display:grid;grid-template-columns:320px 1fr;gap:24px;align-items:start">
      <!-- Panel izquierdo: parámetros -->
      <div class="card" style="padding:20px">
        <h3 style="font-size:0.9rem;font-weight:600;margin:0 0 16px" class="mb-4">Parámetros</h3>
        <div class="form-group">
          <label class="form-label">Abono extra mensual (COP)</label>
          <input type="number" id="sim-extra" value="0" step="50000" min="0">
        </div>
        <button class="btn btn-primary w-full mt-4" id="btnCompare">Comparar estrategias</button>
      </div>
      <!-- Panel derecho: resultados -->
      <div id="sim-results">
        <div class="empty-state">
          <p>Configura los parámetros y presiona Comparar.</p>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btnCompare').addEventListener('click', async () => {
    const extra = parseFloat(container.querySelector('#sim-extra').value) || 0;
    const resultsEl = container.querySelector('#sim-results');
    resultsEl.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';

    try {
      const data = await api.debts.strategyComparison({ extra_payment: extra });
      resultsEl.innerHTML = renderResults(data, extra);
    } catch (err) {
      resultsEl.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
    }
  });
}

function renderResults(data, extra) {
  const strategies = [
    {
      key: 'avalanche',
      label: 'Avalancha',
      sublabel: 'Mayor tasa primero',
      color: 'var(--color-success)',
    },
    {
      key: 'snowball',
      label: 'Bola de Nieve',
      sublabel: 'Menor saldo primero',
      color: 'var(--color-primary)',
    },
    {
      key: 'minimum_only',
      label: 'Solo Mínimo',
      sublabel: 'Sin estrategia extra',
      color: 'var(--color-danger)',
    },
  ];

  const defaultCurrency = 'COP';

  const cards = strategies.map(({ key, label, sublabel, color }) => {
    const s = data[key];
    if (!s) return '';
    const months        = s.months ?? '—';
    const totalInterest = s.total_interest ?? 0;
    const interestSaved = s.interest_saved_vs_minimum ?? 0;
    const monthsSaved   = s.months_saved_vs_minimum ?? 0;
    const payoffDate    = s.payoff_date ?? '—';

    return `
      <div class="card" style="padding:20px;border-top:3px solid ${color}">
        <div style="font-weight:600" class="mb-1">${label}</div>
        <div class="text-soft mb-3" style="font-size:0.75rem">${sublabel}</div>

        <div class="kpi-label">Tiempo total</div>
        <div class="kpi-value amount" style="font-size:1.5rem">${months} meses</div>

        <div class="kpi-label mt-2">Interés total</div>
        <div class="kpi-value negative amount">${fmtCurrency(totalInterest, defaultCurrency)}</div>

        <div class="kpi-label mt-2">Ahorro vs. mínimo</div>
        <div class="kpi-value text-success amount">${fmtCurrency(interestSaved, defaultCurrency)}</div>

        ${monthsSaved > 0 ? `
        <div class="kpi-label mt-2">Meses ahorrados</div>
        <div class="kpi-value text-success">${monthsSaved} meses</div>
        ` : ''}

        <div class="text-soft mt-2" style="font-size:0.8rem">
          Pago estimado: ${payoffDate}
        </div>

        ${(s.debt_payoff_order?.length > 0) ? `
        <div class="mt-3" style="padding-top:12px;border-top:1px solid var(--border-muted)">
          <div class="text-soft mb-2" style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;font-weight:600">Orden de pago</div>
          ${s.debt_payoff_order.map((d, i) => `
            <div class="mb-1" style="font-size:0.8rem;color:var(--text-secondary)">${i + 1}. ${sanitize(d.name ?? String(d.id))}</div>
          `).join('')}
        </div>` : ''}
      </div>
    `;
  }).join('');

  const extraNote = extra > 0
    ? `<div class="alert alert-info mb-4">Comparando con un abono extra mensual de <strong class="amount">${fmtCurrency(extra, 'COP')}</strong>.</div>`
    : '';

  return `
    ${extraNote}
    <div class="grid-3">
      ${cards}
    </div>
  `;
}
