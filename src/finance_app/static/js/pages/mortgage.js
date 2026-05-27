import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Hipoteca';

let _chart = null;

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    const [mortgages, accounts] = await Promise.all([
      api.mortgage.accounts(),
      api.accounts.list({ account_type: 'mortgage' }).catch(() => []),
    ]);
    const list = mortgages.length ? mortgages : accounts.filter(a => a.type === 'mortgage');
    render(container, list);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

export function cleanup() { _chart?.destroy(); _chart = null; }

function render(container, list) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Hipoteca</h1>
        <p>Tabla de amortización y seguimiento de pagos.</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-secondary" id="btnSimulate">Simulador rápido</button>
      </div>
    </div>

    ${list.length === 0 ? `
      <div class="empty-state">
        <div class="empty-state-icon">🏠</div>
        <h3>Sin hipotecas registradas</h3>
        <p>Agrega una cuenta de tipo Hipoteca en la sección de Cuentas.</p>
        <a class="btn btn-primary" data-link="/accounts">Ir a Cuentas</a>
      </div>` : `
      <div class="section-grid cols-auto">
        ${list.map(m => mortgageCard(m)).join('')}
      </div>
      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <span class="card-title">Tabla de Amortización</span>
          <select id="selMortgage" style="font-size:0.8rem;max-width:200px">
            ${list.map(m => `<option value="${m.id}">${sanitize(m.name)}</option>`).join('')}
          </select>
        </div>
        <div id="amortTable" class="card-body">
          <div class="page-loading"><div class="spinner"></div></div>
        </div>
      </div>
      <div class="card" style="margin-top:20px">
        <div class="card-header"><span class="card-title">Proyección de Saldo</span></div>
        <div class="card-body" style="height:260px;position:relative">
          <canvas id="mortChart"></canvas>
        </div>
      </div>`}
  `;

  container.querySelector('#btnSimulate')?.addEventListener('click', () => {
    const sel = container.querySelector('#selMortgage');
    const prefill = sel ? (() => {
      const m = list.find(x => x.id === parseInt(sel.value));
      if (!m) return {};
      const balance = Math.abs(m.balance ?? m.current_balance ?? 0);
      const rate = m.interest_rate ?? m.annual_interest_rate ?? null;
      const monthly = m.monthly_payment ?? null;
      const currency = m.currency?.code ?? m.currency_code ?? 'COP';
      // Estimate remaining years from balance and monthly payment if available
      let years = null;
      if (m.term_months) years = Math.ceil(m.term_months / 12);
      else if (monthly && rate && balance) {
        const mr = Math.pow(1 + rate / 100, 1 / 12) - 1;
        if (mr > 0) {
          const n = Math.ceil(-Math.log(1 - balance * mr / monthly) / Math.log(1 + mr));
          years = Math.max(1, Math.ceil(n / 12));
        }
      }
      return { balance, rate, years, currency };
    })() : {};
    openSimulateModal(prefill);
  });

  if (list.length) {
    const sel = container.querySelector('#selMortgage');
    loadAmortization(container, parseInt(sel.value), list);
    sel?.addEventListener('change', () => loadAmortization(container, parseInt(sel.value), list));
  }
}

async function loadAmortization(container, id, list) {
  const amortEl = container.querySelector('#amortTable');
  if (!amortEl) return;
  amortEl.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';

  try {
    const data = await api.mortgage.schedule(id);
    const rows = data?.schedule ?? data?.amortization ?? data ?? [];
    const mortgage = list.find(m => m.id === id);
    const currency = mortgage?.currency?.code ?? mortgage?.currency_code ?? 'COP';

    amortEl.innerHTML = rows.length ? `
      <div style="max-height:320px;overflow-y:auto">
        <table>
          <thead>
            <tr>
              <th>Mes</th>
              <th class="td-right">Cuota</th>
              <th class="td-right" style="color:var(--color-danger)">Interés</th>
              <th class="td-right" style="color:var(--color-success)">Capital</th>
              <th class="td-right">Saldo</th>
            </tr>
          </thead>
          <tbody>
            ${rows.slice(0, 60).map(r => `
              <tr>
                <td class="td-soft" style="font-size:0.8rem;white-space:nowrap">${fmtDate(r.date ?? r.payment_date)}</td>
                <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(r.payment ?? r.total_payment ?? 0, currency)}</td>
                <td class="td-right td-mono" style="font-size:0.8rem;color:var(--color-danger)">${fmtCurrency(r.interest ?? r.interest_payment ?? 0, currency)}</td>
                <td class="td-right td-mono" style="font-size:0.8rem;color:var(--color-success)">${fmtCurrency(r.principal ?? r.principal_payment ?? 0, currency)}</td>
                <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(r.balance ?? r.remaining_balance ?? 0, currency)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    ` : '<div class="empty-state"><p>Sin datos de amortización</p></div>';

    // Chart
    _chart?.destroy();
    const ctx = container.querySelector('#mortChart');
    if (ctx && rows.length) {
      const sample = rows.filter((_, i) => i % 6 === 0).slice(0, 20);
      _chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: sample.map(r => r.date ?? r.payment_date ?? ''),
          datasets: [{
            label: 'Saldo restante',
            data: sample.map(r => r.balance ?? r.remaining_balance ?? 0),
            borderColor: 'var(--color-primary)',
            backgroundColor: 'rgba(217,119,6,0.1)',
            fill: true, tension: 0.3,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: 'var(--border-muted)' }, ticks: { callback: v => fmtCurrency(v, currency), font: { size: 10 }, color: 'var(--text-soft)' } },
            x: { grid: { display: false }, ticks: { color: 'var(--text-soft)', font: { size: 10 } } },
          },
        },
      });
    }
  } catch (err) {
    amortEl.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function mortgageCard(m) {
  return `
    <div class="kpi-card">
      <div class="kpi-label">${sanitize(m.name)}</div>
      <div class="kpi-value negative">${fmtCurrency(m.balance ?? m.current_balance ?? 0, m.currency?.code ?? m.currency_code ?? 'COP')}</div>
      <div class="kpi-sub">
        ${m.interest_rate != null ? m.interest_rate.toFixed(2) + '% EA · ' : ''}
        Cuota: ${fmtCurrency(m.monthly_payment ?? 0, m.currency?.code ?? m.currency_code ?? 'COP')}
      </div>
    </div>`;
}

function openSimulateModal(prefill = {}) {
  openModal({
    title: 'Simulador de Abono Extra',
    size: 'lg',
    content: `
      <p style="color:var(--text-soft);font-size:0.85rem;margin-bottom:16px">
        Calcula cuánto tiempo e intereses ahorras si aumentas tu pago mensual.
      </p>
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label required">Saldo actual</label>
          <input type="number" id="ms-amount" placeholder="200000000" step="1000000" value="${prefill.balance ?? ''}">
        </div>
        <div class="form-group">
          <label class="form-label required">Tasa de interés (% EA)</label>
          <input type="number" id="ms-rate" placeholder="12.5" step="0.01" value="${prefill.rate ?? ''}">
        </div>
      </div>
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label required">Plazo restante (años)</label>
          <input type="number" id="ms-years" placeholder="15" step="1" min="1" value="${prefill.years ?? ''}">
        </div>
        <div class="form-group">
          <label class="form-label">Moneda</label>
          <select id="ms-currency">
            <option value="COP" ${(prefill.currency ?? 'COP') === 'COP' ? 'selected' : ''}>COP</option>
            <option value="USD" ${prefill.currency === 'USD' ? 'selected' : ''}>USD</option>
          </select>
        </div>
      </div>
      <div class="form-group" style="margin-top:4px">
        <label class="form-label">Abono extra al capital por mes</label>
        <input type="number" id="ms-extra" placeholder="500000" step="100000" min="0">
        <span style="font-size:0.78rem;color:var(--text-soft)">Deja en 0 para ver solo la proyección base.</span>
      </div>
      <div id="ms-result" style="margin-top:20px"></div>
    `,
    submitLabel: 'Simular',
    keepOpen: true,
    onSubmit: async (body) => {
      const amount   = parseFloat(body.querySelector('#ms-amount').value);
      const rate     = parseFloat(body.querySelector('#ms-rate').value);
      const years    = parseFloat(body.querySelector('#ms-years').value);
      const extra    = parseFloat(body.querySelector('#ms-extra').value) || 0;
      const currency = body.querySelector('#ms-currency').value;
      if (!amount || !rate || !years) throw new Error('Saldo, tasa y plazo son obligatorios');

      const resultEl = body.querySelector('#ms-result');
      resultEl.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';

      const [base, withExtra] = await Promise.all([
        api.mortgage.calculate({ principal: amount, annual_rate: rate, years: Math.ceil(years) }),
        extra > 0
          ? api.mortgage.calculate({ principal: amount, annual_rate: rate, years: Math.ceil(years), extra_payment: extra })
          : Promise.resolve(null),
      ]);

      const fmtMonths = m => {
        const y = Math.floor(m / 12), mo = m % 12;
        return [y && `${y} año${y !== 1 ? 's' : ''}`, mo && `${mo} mes${mo !== 1 ? 'es' : ''}`].filter(Boolean).join(' ');
      };

      resultEl.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr${withExtra ? ' 1fr' : ''};gap:16px">
          <div>
            <div style="font-size:0.75rem;font-weight:600;color:var(--text-soft);text-transform:uppercase;margin-bottom:10px">
              Escenario base
            </div>
            <div class="stat-chip" style="margin-bottom:8px">
              <span class="stat-chip-label">Cuota mensual</span>
              <span class="stat-chip-value">${fmtCurrency(base.monthly_payment, currency)}</span>
            </div>
            <div class="stat-chip" style="margin-bottom:8px">
              <span class="stat-chip-label">Plazo total</span>
              <span class="stat-chip-value">${fmtMonths(base.months)}</span>
            </div>
            <div class="stat-chip" style="margin-bottom:8px">
              <span class="stat-chip-label">Total intereses</span>
              <span class="stat-chip-value negative">${fmtCurrency(base.total_interest, currency)}</span>
            </div>
            <div class="stat-chip">
              <span class="stat-chip-label">Total pagado</span>
              <span class="stat-chip-value">${fmtCurrency(base.total_paid, currency)}</span>
            </div>
          </div>
          ${withExtra ? `
          <div style="background:var(--color-success-bg,rgba(34,197,94,0.08));border:1px solid var(--color-success);border-radius:8px;padding:14px">
            <div style="font-size:0.75rem;font-weight:600;color:var(--color-success);text-transform:uppercase;margin-bottom:10px">
              Con abono extra · ${fmtCurrency(extra, currency)}/mes
            </div>
            <div class="stat-chip" style="margin-bottom:8px">
              <span class="stat-chip-label">Cuota total</span>
              <span class="stat-chip-value">${fmtCurrency(withExtra.monthly_payment, currency)}</span>
            </div>
            <div class="stat-chip" style="margin-bottom:8px">
              <span class="stat-chip-label">Nuevo plazo</span>
              <span class="stat-chip-value">${fmtMonths(withExtra.months)}</span>
            </div>
            <div class="stat-chip" style="margin-bottom:8px">
              <span class="stat-chip-label">Total intereses</span>
              <span class="stat-chip-value negative">${fmtCurrency(withExtra.total_interest, currency)}</span>
            </div>
            <div class="stat-chip" style="margin-bottom:8px">
              <span class="stat-chip-label">Total pagado</span>
              <span class="stat-chip-value">${fmtCurrency(withExtra.total_paid, currency)}</span>
            </div>
            <div style="border-top:1px solid var(--color-success);margin-top:12px;padding-top:12px">
              <div style="font-size:0.75rem;font-weight:600;color:var(--color-success);margin-bottom:8px">Ahorros</div>
              <div class="stat-chip" style="margin-bottom:6px">
                <span class="stat-chip-label">Tiempo ahorrado</span>
                <span class="stat-chip-value positive">${fmtMonths(base.months - withExtra.months)}</span>
              </div>
              <div class="stat-chip">
                <span class="stat-chip-label">Intereses ahorrados</span>
                <span class="stat-chip-value positive">${fmtCurrency(base.total_interest - withExtra.total_interest, currency)}</span>
              </div>
            </div>
          </div>` : ''}
        </div>
        ${withExtra ? `<p style="font-size:0.78rem;color:var(--text-soft);margin-top:12px">
          Fecha estimada de pago: <strong>${withExtra.payoff_date}</strong> (vs ${base.payoff_date} sin abono extra)
        </p>` : `<p style="font-size:0.78rem;color:var(--text-soft);margin-top:12px">
          Fecha estimada de pago: <strong>${base.payoff_date}</strong>
        </p>`}
      `;
    },
  });
}
