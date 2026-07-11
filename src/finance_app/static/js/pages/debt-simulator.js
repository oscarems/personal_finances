import * as api from '../api/client.js';
import { fmtCurrency, sanitize } from '../utils.js';

let _balanceChart = null;
let _interestChart = null;
let _activeTab = 'extra'; // 'extra' | 'strategies'
let _debts = [];
let _lastSimData = null;
let _lastStratData = null;
let _debounceTimer = null;

export const title = 'Simulador de Deudas';

export function cleanup() {
  _destroyCharts();
  _activeTab = 'extra';
  _debts = [];
  _lastSimData = null;
  _lastStratData = null;
  if (_debounceTimer) clearTimeout(_debounceTimer);
}

function _destroyCharts() {
  if (_balanceChart) { _balanceChart.destroy(); _balanceChart = null; }
  if (_interestChart) { _interestChart.destroy(); _interestChart = null; }
}

const TYPE_LABEL = { mortgage: 'Hipoteca', credit_loan: 'Préstamo', credit_card: 'Tarjeta' };
const TYPE_COLOR = { mortgage: 'var(--fin-accent)', credit_loan: 'var(--fin-warning,#f59e0b)', credit_card: 'var(--fin-danger)' };
const PRESETS_COP = [50_000, 100_000, 200_000, 500_000];
const PRESETS_USD = [50, 100, 250, 500];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';

  try {
    const all = await api.debts.list();
    // Tarjetas de crédito quedan fuera: saldo revolvente no encaja en el modelo de pago a plazo.
    _debts = all.filter(d => d.is_active !== false && d.debt_type !== 'credit_card');
  } catch (_) {}

  const debtOptions = _debts.map(d => {
    const label = TYPE_LABEL[d.debt_type] || d.debt_type;
    return `<option value="${d.id}">[${label}] ${sanitize(d.name)}${d.institution ? ' — ' + sanitize(d.institution) : ''}</option>`;
  }).join('');

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Simulador de Deudas</h1>
        <p class="text-soft">Compara cuánto ahorras en tiempo e intereses añadiendo un abono extra mensual.</p>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:300px 1fr;gap:24px;align-items:start">

      <!-- Sidebar de parámetros -->
      <div style="position:sticky;top:20px;display:flex;flex-direction:column;gap:16px">
        <div class="card" style="padding:20px">
          <h3 style="font-size:0.875rem;font-weight:600;margin:0 0 16px">Parámetros</h3>
          <div class="form-group">
            <label class="form-label">Deuda</label>
            <select id="sim-debt">
              <option value="">Todas las deudas</option>
              ${debtOptions}
            </select>
          </div>

          <!-- Tab toggle -->
          <div style="display:flex;border:1px solid var(--fin-border);border-radius:8px;overflow:hidden;margin-bottom:16px">
            <button id="tab-extra" class="tab-btn tab-active" style="flex:1;padding:8px 4px;font-size:0.78rem;font-weight:600;border:none;cursor:pointer;background:var(--fin-accent);color:#000;transition:all .15s">Abono extra</button>
            <button id="tab-strategies" class="tab-btn" style="flex:1;padding:8px 4px;font-size:0.78rem;font-weight:600;border:none;cursor:pointer;background:transparent;color:var(--fin-ink-2);transition:all .15s">Comparar estrategias</button>
          </div>

          <!-- Panel: abono extra -->
          <div id="panel-extra">
            <div class="form-group" style="margin-bottom:8px">
              <label class="form-label">Abono extra mensual a capital</label>
              <input type="number" id="sim-extra" value="0" step="50000" min="0" placeholder="0" style="font-size:1rem">
            </div>
            <input type="range" id="sim-slider" min="0" max="2000000" step="50000" value="0"
              style="width:100%;margin-bottom:10px;accent-color:var(--fin-accent)">
            <div id="sim-presets" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:4px"></div>
          </div>

          <!-- Panel: estrategias -->
          <div id="panel-strategies" style="display:none">
            <div class="form-group" style="margin-bottom:8px">
              <label class="form-label">Abono extra adicional (opcional)</label>
              <input type="number" id="strat-extra" value="0" step="50000" min="0" placeholder="0">
            </div>
            <p class="text-soft" style="font-size:0.75rem;margin:0">Compara avalancha, bola de nieve y solo mínimo usando el mismo abono extra.</p>
          </div>
        </div>

        <!-- Resumen deudas activas -->
        <div class="card" style="padding:16px" id="debt-summary-card">
          ${_renderDebtSummaryCards()}
        </div>
      </div>

      <!-- Área de resultados -->
      <div id="sim-results">
        <div class="empty-state" style="padding:60px 20px;text-align:center">
          <div style="font-size:2.5rem;margin-bottom:12px">📊</div>
          <p style="font-weight:600;margin-bottom:4px">Cargando simulación…</p>
        </div>
      </div>
    </div>
  `;

  _setupControls(container);
  _updatePresets(container);
  // Auto-simulate on load
  await _runSimulation(container);
}

function _renderDebtSummaryCards() {
  if (!_debts.length) return '<p class="text-soft" style="font-size:0.8rem;margin:0">No hay deudas activas.</p>';
  return `
    <h4 style="font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--fin-ink-3);margin:0 0 12px">Deudas activas</h4>
    ${_debts.map(d => {
      const color = TYPE_COLOR[d.debt_type] || 'var(--fin-ink-3)';
      const bal = d.current_balance || 0;
      const currency = d.currency_code || 'COP';
      return `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--fin-border-subtle,rgba(255,255,255,0.05))">
          <div>
            <div style="font-size:0.82rem;font-weight:500">${sanitize(d.name)}</div>
            <div style="font-size:0.72rem;color:${color};font-weight:600;text-transform:uppercase">${TYPE_LABEL[d.debt_type] || d.debt_type}</div>
          </div>
          <div style="font-size:0.82rem;font-variant-numeric:tabular-nums;color:var(--fin-danger);font-weight:600">${fmtCurrency(bal, currency)}</div>
        </div>`;
    }).join('')}`;
}

function _setupControls(container) {
  const debtSel  = container.querySelector('#sim-debt');
  const extraInp = container.querySelector('#sim-extra');
  const slider   = container.querySelector('#sim-slider');
  const stratExtra = container.querySelector('#strat-extra');
  const tabExtra = container.querySelector('#tab-extra');
  const tabStrat = container.querySelector('#tab-strategies');

  // Sync slider ↔ input
  slider.addEventListener('input', () => {
    extraInp.value = slider.value;
    _scheduleSimulation(container);
  });
  extraInp.addEventListener('input', () => {
    const v = Math.min(parseFloat(extraInp.value) || 0, parseInt(slider.max));
    slider.value = v;
    _scheduleSimulation(container);
  });

  debtSel.addEventListener('change', () => {
    _updatePresets(container);
    _scheduleSimulation(container);
  });
  stratExtra.addEventListener('input', () => _scheduleSimulation(container));

  // Tabs
  tabExtra.addEventListener('click', () => _switchTab(container, 'extra'));
  tabStrat.addEventListener('click', () => _switchTab(container, 'strategies'));

  // Preset buttons
  container.querySelector('#sim-presets').addEventListener('click', e => {
    const btn = e.target.closest('[data-preset]');
    if (!btn) return;
    const val = parseInt(btn.dataset.preset);
    extraInp.value = val;
    slider.value = Math.min(val, parseInt(slider.max));
    _scheduleSimulation(container);
  });
}

function _switchTab(container, tab) {
  _activeTab = tab;
  const tabExtra = container.querySelector('#tab-extra');
  const tabStrat = container.querySelector('#tab-strategies');
  const panelExtra = container.querySelector('#panel-extra');
  const panelStrat = container.querySelector('#panel-strategies');

  if (tab === 'extra') {
    tabExtra.style.cssText += ';background:var(--fin-accent);color:#000';
    tabStrat.style.cssText += ';background:transparent;color:var(--fin-ink-2)';
    panelExtra.style.display = 'block';
    panelStrat.style.display = 'none';
  } else {
    tabStrat.style.cssText += ';background:var(--fin-accent);color:#000';
    tabExtra.style.cssText += ';background:transparent;color:var(--fin-ink-2)';
    panelStrat.style.display = 'block';
    panelExtra.style.display = 'none';
  }
  _scheduleSimulation(container);
}

function _updatePresets(container) {
  const debtId = container.querySelector('#sim-debt').value;
  const debt = debtId ? _debts.find(d => d.id === parseInt(debtId)) : null;
  const currency = debt?.currency_code || 'COP';
  const presets = currency === 'USD' ? PRESETS_USD : PRESETS_COP;
  const maxVal = presets[presets.length - 1] * 4;
  container.querySelector('#sim-slider').max = maxVal;

  container.querySelector('#sim-presets').innerHTML = presets.map(p =>
    `<button data-preset="${p}" style="flex:1;min-width:fit-content;padding:5px 8px;font-size:0.72rem;font-weight:600;border:1px solid var(--fin-border);border-radius:6px;cursor:pointer;background:var(--fin-bg-2);color:var(--fin-ink-1);transition:background .12s" onmouseover="this.style.background='var(--fin-bg-3)'" onmouseout="this.style.background='var(--fin-bg-2)'">+${_compactNum(p, currency)}</button>`
  ).join('');
}

function _compactNum(n, currency) {
  if (currency === 'USD') return `$${n.toLocaleString()}`;
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n/1_000).toFixed(0)}K`;
  return n.toString();
}

function _scheduleSimulation(container) {
  if (_debounceTimer) clearTimeout(_debounceTimer);
  _debounceTimer = setTimeout(() => _runSimulation(container), 400);
}

async function _runSimulation(container) {
  const extra   = parseFloat(container.querySelector('#sim-extra')?.value) || 0;
  const stratExtra = parseFloat(container.querySelector('#strat-extra')?.value) || 0;
  const debtId  = container.querySelector('#sim-debt').value;
  const resultsEl = container.querySelector('#sim-results');

  resultsEl.innerHTML = '<div style="padding:40px;text-align:center"><div class="spinner"></div></div>';
  _destroyCharts();

  try {
    if (_activeTab === 'extra') {
      const params = { extra_payment: extra, strategy: 'avalanche' };
      if (debtId) params.debt_id = parseInt(debtId);
      const selectedDebt = debtId ? _debts.find(d => d.id === parseInt(debtId)) : null;
      _lastSimData = await api.debts.simulate(params);
      resultsEl.innerHTML = renderExtraResults(_lastSimData, extra, selectedDebt);
      if (_lastSimData.warnings?.length) {
        resultsEl.insertAdjacentHTML('afterbegin', _lastSimData.warnings.map(w =>
          `<div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.35);border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:0.82rem;color:var(--fin-warning,#f59e0b)">⚠ ${w}</div>`
        ).join(''));
      }
      const currency = selectedDebt?.currency_code || 'COP';
      renderBalanceChart(_lastSimData, extra, currency);
      renderInterestChart(_lastSimData, currency);
      _setupAmortizationToggle(resultsEl);
    } else {
      const params = { extra_payment: stratExtra };
      if (debtId) params.debt_id = parseInt(debtId);
      _lastStratData = await api.debts.strategyComparison(params);
      const selectedDebt = debtId ? _debts.find(d => d.id === parseInt(debtId)) : null;
      resultsEl.innerHTML = renderStrategyResults(_lastStratData, stratExtra, selectedDebt);
    }
  } catch (err) {
    resultsEl.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

// ─── Formatters ─────────────────────────────────────────────────────────────

function monthsLabel(months) {
  if (!months || months <= 0) return '—';
  const y = Math.floor(months / 12), m = months % 12;
  if (y === 0) return `${months} mes${months !== 1 ? 'es' : ''}`;
  if (m === 0) return `${y} año${y !== 1 ? 's' : ''}`;
  return `${y} año${y !== 1 ? 's' : ''} y ${m} mes${m !== 1 ? 'es' : ''}`;
}

function monthsFrom(isoDate) {
  if (!isoDate) return 0;
  const today = new Date();
  const t = new Date(isoDate);
  return Math.max(0, (t.getFullYear() - today.getFullYear()) * 12 + (t.getMonth() - today.getMonth()));
}

// ─── Extra payment tab ───────────────────────────────────────────────────────

function renderExtraResults(data, extra, selectedDebt) {
  const currency = selectedDebt?.currency_code || 'COP';
  const isMortgage = selectedDebt?.debt_type === 'mortgage';
  const hasExtra = extra > 0;

  const mBase  = monthsFrom(data.payoff_date);
  const mExtra = monthsFrom(data.payoff_date_extra);
  const monthsSaved   = data.months_saved || 0;
  const interestSaved = data.interest_saved || 0;

  let header = '';
  if (selectedDebt) {
    const label = TYPE_LABEL[selectedDebt.debt_type] || selectedDebt.debt_type;
    const color = TYPE_COLOR[selectedDebt.debt_type] || 'var(--fin-ink-3)';
    header = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
        <span style="background:${color};color:#000;padding:3px 12px;border-radius:20px;font-size:0.7rem;font-weight:700;text-transform:uppercase">${label}</span>
        <span style="font-weight:600">${sanitize(selectedDebt.name)}</span>
        ${selectedDebt.institution ? `<span class="text-soft" style="font-size:0.85rem">— ${sanitize(selectedDebt.institution)}</span>` : ''}
      </div>`;
  }

  const mortgageNote = isMortgage ? `
    <div style="background:rgba(99,179,237,0.08);border:1px solid rgba(99,179,237,0.25);border-radius:8px;padding:10px 14px;margin-bottom:20px;font-size:0.82rem">
      <strong style="color:var(--fin-accent)">Hipoteca:</strong> los abonos extras van 100% a capital, reduciendo la base sobre la que se calculan los intereses.
    </div>` : '';

  const col = (title, bgColor, borderColor, months, interest, payoff, isExtra) => `
    <div style="padding:24px;background:${bgColor};border-radius:12px;border:1px solid ${borderColor};flex:1;min-width:0">
      <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;color:${isExtra ? 'var(--fin-success)' : 'var(--fin-ink-3)'};margin-bottom:18px">${title}</div>
      <div style="font-size:0.75rem;color:var(--fin-ink-3);margin-bottom:4px">Tiempo para liquidar</div>
      <div style="font-size:2rem;font-weight:800;line-height:1.1;margin-bottom:20px;font-variant-numeric:tabular-nums">${monthsLabel(months)}</div>
      <div style="font-size:0.75rem;color:var(--fin-ink-3);margin-bottom:4px">Total en intereses</div>
      <div style="font-size:1.25rem;font-weight:700;color:${isExtra ? 'var(--fin-success)' : 'var(--fin-danger)'};font-variant-numeric:tabular-nums;margin-bottom:16px">${fmtCurrency(interest, currency)}</div>
      <div style="font-size:0.75rem;color:var(--fin-ink-3)">Libre el: <strong>${payoff ?? '—'}</strong></div>
    </div>`;

  const baseCol  = col('Sin abono extra', 'var(--fin-bg-2)', 'var(--fin-border)', mBase, data.total_interest, data.payoff_date, false);
  const extraCol = hasExtra
    ? col(`+ ${fmtCurrency(extra, currency)} extra/mes`, 'rgba(34,197,94,0.05)', 'rgba(34,197,94,0.2)', mExtra, data.total_interest_extra, data.payoff_date_extra, true)
    : `<div style="padding:24px;background:var(--fin-bg-2);border-radius:12px;border:1px dashed var(--fin-border);flex:1;display:flex;align-items:center;justify-content:center;text-align:center">
        <div class="text-soft" style="font-size:0.85rem">Mueve el slider para ver<br>el impacto de un abono extra</div>
       </div>`;

  const savings = (hasExtra && (monthsSaved > 0 || interestSaved > 0)) ? `
    <div style="display:grid;grid-template-columns:1fr 1fr;margin-top:16px;padding:20px;background:rgba(34,197,94,0.08);border-radius:12px;border:1px solid rgba(34,197,94,0.2)">
      <div style="text-align:center;${monthsSaved > 0 && interestSaved > 0 ? 'border-right:1px solid rgba(34,197,94,0.2)' : ''}">
        <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--fin-ink-3);margin-bottom:6px">Tiempo ahorrado</div>
        <div style="font-size:2.2rem;font-weight:800;color:var(--fin-success);line-height:1">${monthsLabel(monthsSaved)}</div>
      </div>
      <div style="text-align:center">
        <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--fin-ink-3);margin-bottom:6px">Intereses ahorrados</div>
        <div style="font-size:2.2rem;font-weight:800;color:var(--fin-success);line-height:1;font-variant-numeric:tabular-nums">${fmtCurrency(interestSaved, currency)}</div>
      </div>
    </div>` : '';

  // Amortization table (first 12 months)
  const amortTable = _renderAmortizationTable(data, extra, currency);

  return `
    ${header}${mortgageNote}
    <div class="card" style="padding:24px;margin-bottom:16px">
      <h3 style="font-size:0.875rem;font-weight:600;margin:0 0 20px">
        ${hasExtra ? `¿Qué pasa si abono ${fmtCurrency(extra, currency)} extra cada mes?` : 'Proyección con la cuota actual'}
      </h3>
      <div style="display:flex;gap:16px">${baseCol}${extraCol}</div>
      ${savings}
    </div>
    <div class="card" style="padding:24px;margin-bottom:16px">
      <h3 style="font-size:0.875rem;font-weight:600;margin:0 0 4px">Evolución del saldo</h3>
      <p class="text-soft" style="font-size:0.78rem;margin:0 0 20px">Saldo pendiente mes a mes</p>
      <div style="position:relative;height:280px"><canvas id="sim-balance-chart"></canvas></div>
    </div>
    <div class="card" style="padding:24px;margin-bottom:16px">
      <h3 style="font-size:0.875rem;font-weight:600;margin:0 0 4px">Intereses pagados por mes</h3>
      <p class="text-soft" style="font-size:0.78rem;margin:0 0 20px">Costo mensual del crédito</p>
      <div style="position:relative;height:240px"><canvas id="sim-interest-chart"></canvas></div>
    </div>
    ${amortTable}`;
}

function _renderAmortizationTable(data, extra, currency) {
  const rows = data.monthly_breakdown?.slice(0, 24) || [];
  if (!rows.length) return '';
  const hasExtra = extra > 0;

  const tableRows = rows.map((r, i) => `
    <tr>
      <td style="font-variant-numeric:tabular-nums;color:var(--fin-ink-3)">${r.month}</td>
      <td style="font-variant-numeric:tabular-nums;text-align:right">${fmtCurrency(r.balance_total, currency)}</td>
      <td style="font-variant-numeric:tabular-nums;text-align:right;color:var(--fin-danger)">${fmtCurrency(r.interest_paid, currency)}</td>
      ${hasExtra ? `
        <td style="font-variant-numeric:tabular-nums;text-align:right;color:var(--fin-success)">${fmtCurrency(r.balance_total_extra, currency)}</td>
        <td style="font-variant-numeric:tabular-nums;text-align:right;color:var(--fin-success)">${fmtCurrency(r.interest_paid_extra, currency)}</td>
      ` : ''}
    </tr>`).join('');

  return `
    <div class="card" style="padding:24px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div>
          <h3 style="font-size:0.875rem;font-weight:600;margin:0 0 2px">Tabla de amortización</h3>
          <p class="text-soft" style="font-size:0.78rem;margin:0">Primeros 24 meses</p>
        </div>
        <button id="amort-toggle" style="font-size:0.78rem;color:var(--fin-accent);background:none;border:none;cursor:pointer;padding:4px 8px">Mostrar tabla ▾</button>
      </div>
      <div id="amort-table-wrap" style="display:none;overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
          <thead>
            <tr style="border-bottom:1px solid var(--fin-border)">
              <th style="text-align:left;padding:6px 8px;font-weight:600;color:var(--fin-ink-3)">Mes</th>
              <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--fin-ink-3)">Saldo base</th>
              <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--fin-ink-3)">Interés base</th>
              ${hasExtra ? `
                <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--fin-success)">Saldo +extra</th>
                <th style="text-align:right;padding:6px 8px;font-weight:600;color:var(--fin-success)">Interés +extra</th>
              ` : ''}
            </tr>
          </thead>
          <tbody>
            ${tableRows}
          </tbody>
        </table>
      </div>
    </div>`;
}

function _setupAmortizationToggle(container) {
  const btn = container.querySelector('#amort-toggle');
  const wrap = container.querySelector('#amort-table-wrap');
  if (!btn || !wrap) return;
  btn.addEventListener('click', () => {
    const open = wrap.style.display !== 'none';
    wrap.style.display = open ? 'none' : 'block';
    btn.textContent = open ? 'Mostrar tabla ▾' : 'Ocultar tabla ▴';
  });
}

// ─── Strategy comparison tab ─────────────────────────────────────────────────

function renderStrategyResults(data, extra, selectedDebt) {
  const currency = selectedDebt?.currency_code || 'COP';

  const strategies = [
    { key: 'avalanche', label: 'Avalancha', emoji: '🏔️', desc: 'Paga primero la de mayor tasa', color: 'var(--fin-accent)', border: 'rgba(99,179,237,0.35)', bg: 'rgba(99,179,237,0.05)' },
    { key: 'snowball',  label: 'Bola de nieve', emoji: '❄️', desc: 'Paga primero la de menor saldo', color: '#a78bfa', border: 'rgba(167,139,250,0.35)', bg: 'rgba(167,139,250,0.05)' },
    { key: 'minimum_only', label: 'Solo mínimo', emoji: '😬', desc: 'Sin estrategia, cuota mínima', color: 'var(--fin-ink-3)', border: 'var(--fin-border)', bg: 'var(--fin-bg-2)' },
  ];

  // Find best strategy by total interest
  const best = ['avalanche', 'snowball'].reduce((a, b) =>
    (data[a]?.total_interest ?? Infinity) <= (data[b]?.total_interest ?? Infinity) ? a : b
  );

  const cols = strategies.map(s => {
    const d = data[s.key];
    if (!d) return '';
    const isBest = s.key === best;
    const savedInterest = d.interest_saved_vs_minimum || 0;
    const savedMonths = d.months_saved_vs_minimum || 0;

    const orderList = d.debt_payoff_order?.length
      ? `<div style="margin-top:16px">
          <div style="font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--fin-ink-3);margin-bottom:8px">Orden de pago</div>
          ${d.debt_payoff_order.map((dd, i) =>
            `<div style="display:flex;align-items:center;gap:8px;font-size:0.78rem;padding:4px 0">
               <span style="width:18px;height:18px;border-radius:50%;background:${s.color};color:#000;font-size:0.65rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0">${i+1}</span>
               <span>${sanitize(dd.name)}</span>
             </div>`
          ).join('')}
         </div>`
      : '';

    return `
      <div style="padding:22px;background:${s.bg};border-radius:12px;border:1px solid ${s.border};flex:1;min-width:0;position:relative">
        ${isBest ? `<div style="position:absolute;top:-10px;right:14px;background:var(--fin-success);color:#000;font-size:0.65rem;font-weight:700;padding:3px 10px;border-radius:20px;text-transform:uppercase">Recomendado</div>` : ''}
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="font-size:1.2rem">${s.emoji}</span>
          <span style="font-size:0.875rem;font-weight:700;color:${s.color}">${s.label}</span>
        </div>
        <div style="font-size:0.75rem;color:var(--fin-ink-3);margin-bottom:20px">${s.desc}</div>

        <div style="font-size:0.72rem;color:var(--fin-ink-3);margin-bottom:3px">Tiempo para liquidar</div>
        <div style="font-size:1.75rem;font-weight:800;line-height:1.1;margin-bottom:18px">${monthsLabel(d.months)}</div>

        <div style="font-size:0.72rem;color:var(--fin-ink-3);margin-bottom:3px">Total en intereses</div>
        <div style="font-size:1.15rem;font-weight:700;color:var(--fin-danger);font-variant-numeric:tabular-nums;margin-bottom:14px">${fmtCurrency(d.total_interest, currency)}</div>

        <div style="font-size:0.72rem;color:var(--fin-ink-3);margin-bottom:3px">Libre el</div>
        <div style="font-size:0.85rem;font-weight:600;margin-bottom:14px">${d.payoff_date ?? '—'}</div>

        ${s.key !== 'minimum_only' && (savedInterest > 0 || savedMonths > 0) ? `
          <div style="padding:10px;background:rgba(34,197,94,0.08);border-radius:8px;border:1px solid rgba(34,197,94,0.2)">
            <div style="font-size:0.7rem;color:var(--fin-ink-3);margin-bottom:4px">vs solo mínimo</div>
            ${savedInterest > 0 ? `<div style="font-size:0.82rem;font-weight:600;color:var(--fin-success)">-${fmtCurrency(savedInterest, currency)} en intereses</div>` : ''}
            ${savedMonths > 0 ? `<div style="font-size:0.82rem;font-weight:600;color:var(--fin-success)">-${monthsLabel(savedMonths)} de plazo</div>` : ''}
          </div>
        ` : ''}

        ${orderList}
      </div>`;
  }).join('');

  const extraNote = extra > 0
    ? `<p class="text-soft" style="font-size:0.78rem;margin:0 0 20px">Con ${fmtCurrency(extra, currency)} de abono extra mensual distribuido según cada estrategia.</p>`
    : `<p class="text-soft" style="font-size:0.78rem;margin:0 0 20px">Solo con la cuota mínima actual. Añade un abono extra arriba para ver el impacto combinado.</p>`;

  return `
    <div class="card" style="padding:24px">
      <h3 style="font-size:0.875rem;font-weight:600;margin:0 0 6px">Comparador de estrategias</h3>
      ${extraNote}
      <div style="display:flex;gap:16px">${cols}</div>
    </div>`;
}

// ─── Charts ──────────────────────────────────────────────────────────────────

function renderBalanceChart(data, extra, currency) {
  if (_balanceChart) { _balanceChart.destroy(); _balanceChart = null; }
  const canvas = document.getElementById('sim-balance-chart');
  if (!canvas || !data.monthly_breakdown?.length) return;

  const hasExtra = extra > 0;
  const labels = data.monthly_breakdown.map(r => r.month);
  const baseData = data.monthly_breakdown.map(r => r.balance_total);
  const extraData = hasExtra ? data.monthly_breakdown.map(r => r.balance_total_extra) : null;

  const fmtVal = v => {
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000) return (v / 1_000).toFixed(0) + 'K';
    return v.toFixed(0);
  };

  const datasets = [{
    label: 'Sin abono extra',
    data: baseData,
    borderColor: 'rgba(129,140,248,0.95)',
    backgroundColor: 'rgba(129,140,248,0.12)',
    borderWidth: 2.5,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBackgroundColor: 'rgba(129,140,248,1)',
    fill: true,
    tension: 0.3,
  }];

  if (extraData) {
    datasets.push({
      label: `+ ${fmtCurrency(extra, currency)} extra/mes`,
      data: extraData,
      borderColor: 'rgba(74,222,128,0.95)',
      backgroundColor: 'rgba(74,222,128,0.1)',
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 5,
      pointHoverBackgroundColor: 'rgba(74,222,128,1)',
      fill: true,
      tension: 0.3,
    });
  }

  _balanceChart = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { bottom: 4 } },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            maxRotation: 45,
            minRotation: 45,
            autoSkip: true,
            maxTicksLimit: 14,
            font: { size: 11 },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255,255,255,0.06)' },
          ticks: { font: { size: 11 }, callback: v => fmtVal(v) },
        },
      },
      plugins: {
        legend: { position: 'top', align: 'end' },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmtCurrency(ctx.parsed.y, currency)}` } },
      },
    },
  });
}

function renderInterestChart(data, currency) {
  if (_interestChart) { _interestChart.destroy(); _interestChart = null; }
  const canvas = document.getElementById('sim-interest-chart');
  if (!canvas || !data.monthly_breakdown?.length) return;

  // Show only first 36 months to keep it readable
  const rows = data.monthly_breakdown.slice(0, 36);
  const labels = rows.map(r => r.month);
  const baseInterest = rows.map(r => r.interest_paid);
  const extraInterest = rows.map(r => r.interest_paid_extra);
  const hasExtra = extraInterest.some(v => v !== baseInterest[labels.indexOf(labels[0])]);

  const fmtVal = v => {
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000) return (v / 1_000).toFixed(0) + 'K';
    return v.toFixed(0);
  };

  const datasets = [{
    label: 'Interés sin extra',
    data: baseInterest,
    borderColor: 'rgba(248,113,113,0.9)',
    backgroundColor: 'rgba(248,113,113,0.12)',
    borderWidth: 2.5,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBackgroundColor: 'rgba(248,113,113,1)',
    fill: true,
    tension: 0.3,
  }];

  if (hasExtra) {
    datasets.push({
      label: 'Interés con extra',
      data: extraInterest,
      borderColor: 'rgba(74,222,128,0.9)',
      backgroundColor: 'rgba(74,222,128,0.1)',
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 5,
      pointHoverBackgroundColor: 'rgba(74,222,128,1)',
      fill: true,
      tension: 0.3,
    });
  }

  _interestChart = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { bottom: 4 } },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            maxRotation: 45,
            minRotation: 45,
            autoSkip: true,
            maxTicksLimit: 14,
            font: { size: 11 },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255,255,255,0.06)' },
          ticks: { font: { size: 11 }, callback: v => fmtVal(v) },
        },
      },
      plugins: {
        legend: { position: 'top', align: 'end' },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmtCurrency(ctx.parsed.y, currency)}` } },
      },
    },
  });
}
