import * as api from '../api/client.js';
import { fmtCurrency, fmtNumber, sanitize } from '../utils.js';

export const title = 'Simulador de Inversión';

let _chart = null;

export async function mount(container) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Simulador de Inversión</h1>
        <p>Proyecta el crecimiento de una inversión con interés compuesto.</p>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:340px 1fr;gap:24px">
      <div class="card">
        <div class="card-header"><span class="card-title">Parámetros</span></div>
        <div class="card-body">
          <div class="form-group" style="margin-bottom:16px">
            <label class="form-label required">Capital inicial</label>
            <input type="number" id="inv-initial" value="10000000" step="100000" min="0">
          </div>
          <div class="form-group" style="margin-bottom:16px">
            <label class="form-label">Aporte mensual</label>
            <input type="number" id="inv-monthly" value="500000" step="50000" min="0">
          </div>
          <div class="form-group" style="margin-bottom:16px">
            <label class="form-label required">Tasa de retorno anual (%)</label>
            <input type="number" id="inv-rate" value="12" step="0.5" min="0" max="100">
          </div>
          <div class="form-group" style="margin-bottom:16px">
            <label class="form-label required">Plazo (años)</label>
            <input type="number" id="inv-years" value="10" step="1" min="1" max="50">
          </div>
          <div class="form-group" style="margin-bottom:20px">
            <label class="form-label">Moneda</label>
            <select id="inv-currency">
              <option value="COP">COP</option>
              <option value="USD">USD</option>
            </select>
          </div>
          <button class="btn btn-primary" style="width:100%" id="btnSimulate">Simular</button>
        </div>
      </div>

      <div>
        <div class="kpi-grid" id="inv-kpis" style="margin-bottom:20px"></div>
        <div class="card">
          <div class="card-header"><span class="card-title">Proyección de crecimiento</span></div>
          <div class="card-body" style="height:300px;position:relative">
            <canvas id="invChart"></canvas>
          </div>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btnSimulate').addEventListener('click', () => simulate(container));
  simulate(container);
}

export function cleanup() { _chart?.destroy(); _chart = null; }

function simulate(container) {
  const initial  = parseFloat(container.querySelector('#inv-initial').value)  || 0;
  const monthly  = parseFloat(container.querySelector('#inv-monthly').value)   || 0;
  const rate     = parseFloat(container.querySelector('#inv-rate').value)      || 0;
  const years    = parseInt(container.querySelector('#inv-years').value)       || 10;
  const currency = container.querySelector('#inv-currency').value;

  const monthlyRate = rate / 100 / 12;
  const months = years * 12;

  let balance = initial;
  const data  = [{ month: 0, balance, invested: initial }];
  let totalInvested = initial;

  for (let m = 1; m <= months; m++) {
    balance = balance * (1 + monthlyRate) + monthly;
    totalInvested += monthly;
    if (m % 12 === 0 || m === months) {
      data.push({ month: m, balance, invested: totalInvested });
    }
  }

  const finalBalance = data[data.length - 1].balance;
  const totalGain    = finalBalance - totalInvested;
  const roi          = totalInvested > 0 ? (totalGain / totalInvested) * 100 : 0;

  const kpisEl = container.querySelector('#inv-kpis');
  kpisEl.innerHTML = `
    <div class="kpi-card">
      <div class="kpi-label">Valor final</div>
      <div class="kpi-value positive">${fmtCurrency(finalBalance, currency)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Total invertido</div>
      <div class="kpi-value">${fmtCurrency(totalInvested, currency)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Ganancia total</div>
      <div class="kpi-value positive">${fmtCurrency(totalGain, currency)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Retorno total</div>
      <div class="kpi-value accent">${roi.toFixed(1)}%</div>
    </div>
  `;

  _chart?.destroy();
  const ctx = container.querySelector('#invChart');
  _chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => `Año ${Math.floor(d.month / 12)}`),
      datasets: [
        {
          label: 'Valor de la inversión',
          data: data.map(d => d.balance),
          borderColor: 'var(--color-success)',
          backgroundColor: 'rgba(5,150,105,0.1)',
          fill: true, tension: 0.4,
        },
        {
          label: 'Total invertido',
          data: data.map(d => d.invested),
          borderColor: 'var(--color-primary)',
          backgroundColor: 'rgba(217,119,6,0.08)',
          fill: true, tension: 0.4,
          borderDash: [5, 5],
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { font: { size: 11 }, color: 'var(--text-secondary)' } },
        tooltip: { callbacks: { label: ctx => ` ${fmtCurrency(ctx.raw, currency)}` } },
      },
      scales: {
        y: { grid: { color: 'var(--border-muted)' }, ticks: { callback: v => fmtCurrency(v, currency), font: { size: 10 }, color: 'var(--text-soft)' } },
        x: { grid: { display: false }, ticks: { color: 'var(--text-soft)', font: { size: 10 } } },
      },
    },
  });
}
