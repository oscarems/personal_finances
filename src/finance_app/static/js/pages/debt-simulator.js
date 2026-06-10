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
        <h3 style="font-size:0.9rem;font-weight:600;margin:0 0 16px">Parámetros</h3>
        <div class="form-group">
          <label class="form-label">Abono extra mensual (COP)</label>
          <input type="number" id="sim-extra" value="0" step="50000" min="0">
        </div>
        <button class="btn btn-primary" id="btnCompare" style="width:100%;margin-top:16px">Comparar estrategias</button>
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
        <div style="font-weight:600;margin-bottom:4px">${label}</div>
        <div style="font-size:0.75rem;color:var(--text-soft);margin-bottom:12px">${sublabel}</div>

        <div class="kpi-label">Tiempo total</div>
        <div class="kpi-value" style="font-size:1.5rem;font-family:var(--font-mono)">${months} meses</div>

        <div class="kpi-label" style="margin-top:8px">Interés total</div>
        <div class="kpi-value negative">${fmtCurrency(totalInterest, defaultCurrency)}</div>

        <div class="kpi-label" style="margin-top:8px">Ahorro vs. mínimo</div>
        <div class="kpi-value positive">${fmtCurrency(interestSaved, defaultCurrency)}</div>

        ${monthsSaved > 0 ? `
        <div class="kpi-label" style="margin-top:8px">Meses ahorrados</div>
        <div class="kpi-value" style="color:var(--color-success)">${monthsSaved} meses</div>
        ` : ''}

        <div style="font-size:0.8rem;color:var(--text-soft);margin-top:8px">
          Pago estimado: ${payoffDate}
        </div>

        ${(s.debt_payoff_order?.length > 0) ? `
        <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border-muted)">
          <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);margin-bottom:6px;font-weight:600">Orden de pago</div>
          ${s.debt_payoff_order.map((d, i) => `
            <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:2px">${i + 1}. ${sanitize(d.name ?? String(d.id))}</div>
          `).join('')}
        </div>` : ''}
      </div>
    `;
  }).join('');

  const extraNote = extra > 0
    ? `<div class="alert alert-info" style="margin-bottom:16px">Comparando con un abono extra mensual de <strong>${fmtCurrency(extra, 'COP')}</strong>.</div>`
    : '';

  return `
    ${extraNote}
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
      ${cards}
    </div>
  `;
}
