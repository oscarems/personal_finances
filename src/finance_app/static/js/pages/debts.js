import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, fmtNumber, sanitize, progressBar } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Deudas';

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    const debts = await api.debts.list();
    renderPage(container, debts);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function renderPage(container, debts) {
  const totalCOP = debts.filter(d => (d.currency_code ?? 'COP') === 'COP').reduce((s,d) => s + (d.current_balance ?? d.balance ?? 0), 0);
  const totalUSD = debts.filter(d => d.currency_code === 'USD').reduce((s,d) => s + (d.current_balance ?? d.balance ?? 0), 0);
  const totalMonthly = debts.reduce((s,d) => s + (d.monthly_payment ?? 0), 0);
  const avgRate = debts.filter(d => d.interest_rate > 0);
  const avgInterest = avgRate.length ? avgRate.reduce((s,d) => s + d.interest_rate, 0) / avgRate.length : 0;

  const cards  = debts.filter(d => d.debt_type === 'credit_card' || d.account_type === 'credit_card');
  const loans  = debts.filter(d => ['personal_loan','credit_loan','loan'].includes(d.debt_type ?? d.account_type));
  const mortgs = debts.filter(d => d.debt_type === 'mortgage' || d.account_type === 'mortgage');
  const other  = debts.filter(d => !cards.includes(d) && !loans.includes(d) && !mortgs.includes(d));

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text"><h1>Deudas</h1></div>
    </div>

    <div class="kpi-grid" style="margin-bottom:24px">
      <div class="kpi-card">
        <div class="kpi-label">Total Deuda COP</div>
        <div class="kpi-value negative">${fmtCurrency(totalCOP, 'COP')}</div>
      </div>
      ${totalUSD > 0 ? `<div class="kpi-card">
        <div class="kpi-label">Total Deuda USD</div>
        <div class="kpi-value negative">${fmtCurrency(totalUSD, 'USD')}</div>
      </div>` : ''}
      <div class="kpi-card">
        <div class="kpi-label">Cuota Total Mensual</div>
        <div class="kpi-value warning">${fmtCurrency(totalMonthly, 'COP')}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Tasa Promedio</div>
        <div class="kpi-value">${avgInterest.toFixed(1)}% EA</div>
      </div>
    </div>

    ${debtSection('Tarjetas de Crédito', cards, container)}
    ${debtSection('Créditos / Préstamos', loans, container)}
    ${debtSection('Hipotecas', mortgs, container)}
    ${debtSection('Otros', other, container)}

    ${debts.length === 0 ? `<div class="empty-state">
      <div class="empty-state-icon">🎉</div>
      <h3>Sin deudas registradas</h3>
      <p>Mantén tus cuentas al día para verlas aquí.</p>
    </div>` : ''}
  `;

  container.querySelectorAll('[data-detail-debt]').forEach(btn => {
    const id = parseInt(btn.dataset.detailDebt);
    const debt = debts.find(d => d.id === id);
    btn.addEventListener('click', () => openDebtDetail(debt));
  });

  container.querySelectorAll('[data-simulate-debt]').forEach(btn => {
    const id = parseInt(btn.dataset.simulateDebt);
    const debt = debts.find(d => d.id === id);
    btn.addEventListener('click', () => openSimulateModal(debt));
  });
}

function debtSection(title, debts, container) {
  if (!debts.length) return '';
  return `
    <div style="margin-bottom:28px">
      <h3 style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);margin:0 0 12px;font-weight:600">${title}</h3>
      <div class="section-grid cols-auto">
        ${debts.map(d => debtCard(d)).join('')}
      </div>
    </div>`;
}

function debtCard(d) {
  const balance  = d.current_balance ?? d.balance ?? 0;
  const original = d.original_amount ?? d.credit_limit ?? 0;
  const currency = d.currency_code ?? 'COP';
  const rate     = d.interest_rate ?? 0;
  const monthly  = d.monthly_payment ?? 0;

  const hasLimit = original > 0 && balance > 0;
  const pct = hasLimit ? Math.min(100, (balance / original) * 100) : 0;
  const rateClass = rate >= 25 ? 'danger' : rate >= 15 ? 'warning' : 'neutral';

  return `
    <div class="card">
      <div style="padding:16px 20px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
          <div>
            <div style="font-weight:600;font-size:0.9375rem">${sanitize(d.name)}</div>
            <div style="font-size:0.72rem;color:var(--text-soft)">${sanitize(d.institution ?? d.debt_type ?? '—')}</div>
          </div>
          ${rate > 0 ? `<span class="badge badge-${rateClass}">${rate.toFixed(1)}% EA</span>` : ''}
        </div>

        <div class="amount negative" style="font-size:1.375rem;font-weight:600;margin-bottom:8px">
          ${fmtCurrency(balance, currency)}
        </div>

        ${hasLimit ? `
          <div style="margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--text-soft);margin-bottom:4px">
              <span>Usado</span>
              <span>${pct.toFixed(0)}%</span>
            </div>
            <div class="progress-wrap">
              <div class="progress-fill ${pct >= 80 ? 'danger' : pct >= 50 ? 'warning' : 'ok'}" style="width:${pct}%"></div>
            </div>
            <div style="font-size:0.72rem;color:var(--text-soft);margin-top:4px">
              ${fmtCurrency(original, currency)} original/límite
            </div>
          </div>
        ` : ''}

        ${monthly > 0 ? `
          <div style="font-size:0.8rem;color:var(--text-secondary)">
            Cuota mensual: <strong style="font-family:var(--font-mono)">${fmtCurrency(monthly, currency)}</strong>
          </div>` : ''}
      </div>
      <div style="display:flex;gap:8px;padding:10px 20px;border-top:1px solid var(--border-muted);background:var(--bg-surface-muted)">
        <button class="btn btn-ghost btn-xs" data-detail-debt="${d.id}">Ver detalles</button>
        <button class="btn btn-ghost btn-xs" data-simulate-debt="${d.id}">Simular pago</button>
      </div>
    </div>`;
}

async function openDebtDetail(debt) {
  const modal = openModal({
    title: `Amortización: ${debt.name}`,
    size: 'lg',
    content: '<div class="page-loading"><div class="spinner"></div></div>',
  });

  try {
    const amort = await api.debts.amortization(debt.id);
    const rows = (amort?.schedule ?? []).slice(0, 24);

    modal.body.innerHTML = `
      <div class="stat-row" style="margin-bottom:16px">
        <div class="stat-chip">
          <span class="stat-chip-label">Saldo Actual</span>
          <span class="stat-chip-value negative">${fmtCurrency(debt.current_balance ?? debt.balance ?? 0, debt.currency_code ?? 'COP')}</span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip-label">Tasa</span>
          <span class="stat-chip-value">${(debt.interest_rate ?? 0).toFixed(2)}% EA</span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip-label">Cuota</span>
          <span class="stat-chip-value">${fmtCurrency(debt.monthly_payment ?? 0, debt.currency_code ?? 'COP')}</span>
        </div>
      </div>
      ${rows.length ? `
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Mes</th>
                <th class="td-right">Cuota</th>
                <th class="td-right">Interés</th>
                <th class="td-right">Capital</th>
                <th class="td-right">Saldo</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(r => `
                <tr>
                  <td class="td-soft" style="font-size:0.8rem">${fmtDate(r.date ?? r.payment_date)}</td>
                  <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(r.payment ?? r.total_payment ?? 0, debt.currency_code ?? 'COP')}</td>
                  <td class="td-right td-mono" style="font-size:0.8rem;color:var(--color-danger)">${fmtCurrency(r.interest ?? r.interest_payment ?? 0, debt.currency_code ?? 'COP')}</td>
                  <td class="td-right td-mono" style="font-size:0.8rem;color:var(--color-success)">${fmtCurrency(r.principal ?? r.principal_payment ?? 0, debt.currency_code ?? 'COP')}</td>
                  <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(r.balance ?? r.remaining_balance ?? 0, debt.currency_code ?? 'COP')}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      ` : '<div class="empty-state"><p>Sin tabla de amortización disponible</p></div>'}
    `;
  } catch (err) {
    modal.body.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function openSimulateModal(debt) {
  const currency = debt.currency_code ?? debt.currency?.code ?? 'COP';

  const content = `
    <p style="font-size:0.875rem;color:var(--text-secondary);margin-bottom:16px">
      Saldo actual: <strong class="amount negative">${fmtCurrency(debt.current_balance ?? debt.balance ?? 0, currency)}</strong> —
      Tasa: <strong>${(debt.interest_rate ?? 0).toFixed(2)}% EA</strong>
    </p>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Abono extra mensual</label>
        <input type="number" id="sim-extra" value="0" step="10000" min="0">
      </div>
      <div class="form-group">
        <label class="form-label">Estrategia</label>
        <select id="sim-strategy">
          <option value="standard">Cuota estándar</option>
          <option value="avalanche">Avalancha (mayor tasa)</option>
          <option value="snowball">Bola de nieve (menor saldo)</option>
        </select>
      </div>
    </div>
    <div id="sim-result" style="margin-top:16px"></div>
    <div class="modal-footer" style="border-top:none;padding:0;justify-content:flex-start;margin-top:8px">
      <button class="btn btn-primary btn-sm" id="btnRunSim">Simular</button>
    </div>
  `;

  const modal = openModal({ title: `Simular Pago: ${debt.name}`, size: 'md', content });

  modal.body.querySelector('#btnRunSim').addEventListener('click', async () => {
    const extra    = parseFloat(modal.body.querySelector('#sim-extra').value) || 0;
    const strategy = modal.body.querySelector('#sim-strategy').value;
    try {
      const result = await api.debts.simulate({ debt_id: debt.id, extra_payment: extra, strategy });
      modal.body.querySelector('#sim-result').innerHTML = `
        <div class="stat-row">
          <div class="stat-chip">
            <span class="stat-chip-label">Meses restantes</span>
            <span class="stat-chip-value">${result?.months_remaining ?? '—'}</span>
          </div>
          <div class="stat-chip">
            <span class="stat-chip-label">Total intereses</span>
            <span class="stat-chip-value negative">${fmtCurrency(result?.total_interest ?? 0, currency)}</span>
          </div>
          <div class="stat-chip">
            <span class="stat-chip-label">Ahorro vs. mínimo</span>
            <span class="stat-chip-value positive">${fmtCurrency(result?.interest_savings ?? 0, currency)}</span>
          </div>
        </div>`;
    } catch (err) {
      modal.showError(err.message);
    }
  });
}
