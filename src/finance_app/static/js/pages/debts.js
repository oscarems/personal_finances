import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, fmtNumber, sanitize, progressBar } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Deudas';

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    const [debts, summary] = await Promise.all([api.debts.list(), api.debts.summary().catch(() => null)]);
    renderPage(container, debts, summary);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function renderPage(container, debts, summary) {
  const totalCOP = debts.filter(d => (d.currency_code ?? 'COP') === 'COP').reduce((s,d) => s + (d.current_balance ?? d.balance ?? 0), 0);
  const totalUSD = debts.filter(d => d.currency_code === 'USD').reduce((s,d) => s + (d.current_balance ?? d.balance ?? 0), 0);
  const totalMonthly = debts.reduce((s,d) => s + (d.monthly_payment ?? 0), 0);
  const avgRate = debts.filter(d => d.interest_rate > 0);
  const avgInterest = avgRate.length ? avgRate.reduce((s,d) => s + d.interest_rate, 0) / avgRate.length : 0;

  const cards  = debts.filter(d => d.debt_type === 'credit_card' || d.account_type === 'credit_card');
  const loans  = debts.filter(d => ['personal_loan','credit_loan','loan'].includes(d.debt_type ?? d.account_type));
  const mortgs = debts.filter(d => d.debt_type === 'mortgage' || d.account_type === 'mortgage');
  const other  = debts.filter(d => !cards.includes(d) && !loans.includes(d) && !mortgs.includes(d));

  const hasAlerts = summary && (
    (summary.high_utilization_alerts?.length > 0) ||
    (summary.high_interest_debts?.length > 0) ||
    (summary.total_monthly_interest_credit_cards?.COP > 0)
  );

  const alertsBanner = hasAlerts ? `
    <div class="alerts-banner" style="margin-bottom:16px;display:flex;flex-direction:column;gap:8px">
      ${(summary.high_utilization_alerts ?? []).map(a => `
        <div class="alert alert-${a.severity === 'critical' ? 'danger' : 'warning'}">
          ⚠ <strong>${sanitize(a.name)}</strong>: utilización del ${a.utilization_pct.toFixed(0)}% del cupo —
          ${a.severity === 'critical' ? 'Alto riesgo de score' : 'Moderado'}
        </div>`).join('')}
      ${summary.total_monthly_interest_credit_cards?.COP > 0 ? `
        <div class="alert alert-info">
          💳 Interés mensual estimado en tarjetas: <strong>${fmtCurrency(summary.total_monthly_interest_credit_cards.COP, 'COP')}</strong>
        </div>` : ''}
    </div>` : '';

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text"><h1>Deudas</h1></div>
      <div class="page-header-actions">
        <button class="btn btn-primary btn-sm" id="btnNewDebt">+ Nueva Deuda</button>
      </div>
    </div>

    ${alertsBanner}

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

  container.querySelector('#btnNewDebt')?.addEventListener('click', () => openDebtForm(null, () => mount(container)));

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

  container.querySelectorAll('[data-edit-debt]').forEach(btn => {
    const id = parseInt(btn.dataset.editDebt);
    const debt = debts.find(d => d.id === id);
    btn.addEventListener('click', () => openDebtForm(debt, () => mount(container)));
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

  const absBalance = Math.abs(balance);
  const hasLimit = original > 0 && absBalance > 0;
  const pct = hasLimit ? Math.min(100, (absBalance / original) * 100) : 0;
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
              <div class="progress-fill ${pct >= 70 ? 'danger' : pct >= 30 ? 'warning' : 'ok'}" style="width:${pct}%"></div>
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
        <button class="btn btn-ghost btn-xs" data-edit-debt="${d.id}">Editar</button>
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
    const isCard = (debt.debt_type === 'credit_card' || debt.account_type === 'credit_card');
    const [amort, costAnalysis, installments] = await Promise.all([
      api.debts.schedule(debt.id, 'plan'),
      api.debts.costAnalysis(debt.id).catch(() => null),
      isCard ? api.debts.installments(debt.id).catch(() => []) : Promise.resolve([]),
    ]);
    const rows = (amort?.schedule ?? []).slice(0, 24);
    const currency = debt.currency_code ?? 'COP';

    const installmentsSection = isCard ? (() => {
      const list = installments ?? [];
      return `
        <div style="margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <h4 style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);margin:0;font-weight:600">Compras en Cuotas</h4>
            <button class="btn btn-ghost btn-xs" id="btnAddInstallment">+ Agregar</button>
          </div>
          ${list.length ? `
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Descripción</th>
                <th class="td-right">Total</th>
                <th class="td-right">Cuotas</th>
                <th class="td-right">Saldo pendiente</th>
                <th class="td-right">Cuota mensual</th>
              </tr></thead>
              <tbody>
                ${list.map(inst => `<tr>
                  <td>${sanitize(inst.description ?? '')}</td>
                  <td class="td-right td-mono">${fmtCurrency(inst.total_amount ?? 0, currency)}</td>
                  <td class="td-right">${inst.installments_paid ?? 0}/${inst.installments_total ?? 0}</td>
                  <td class="td-right td-mono negative">${fmtCurrency(inst.amount_remaining ?? 0, currency)}</td>
                  <td class="td-right td-mono">${fmtCurrency(inst.monthly_amount ?? 0, currency)}</td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>` : `<div class="empty-state" style="padding:12px 0"><p style="font-size:0.85rem">Sin cuotas diferidas registradas.</p></div>`}
        </div>`;
    })() : '';

    const costSection = costAnalysis ? `
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-muted)">
        <h4 style="font-size:0.8rem;text-transform:uppercase;color:var(--text-soft);margin:0 0 12px;font-weight:600">Costo Total de la Deuda</h4>
        <div class="stat-row">
          <div class="stat-chip">
            <span class="stat-chip-label">Pagado hasta hoy</span>
            <span class="stat-chip-value">${fmtCurrency(costAnalysis.total_paid_to_date ?? 0, currency)}</span>
          </div>
          <div class="stat-chip">
            <span class="stat-chip-label">Interés pagado</span>
            <span class="stat-chip-value negative">${fmtCurrency(costAnalysis.interest_paid_to_date ?? 0, currency)}</span>
          </div>
          <div class="stat-chip">
            <span class="stat-chip-label">% en intereses</span>
            <span class="stat-chip-value warning">${(costAnalysis.interest_pct_of_paid ?? 0).toFixed(1)}%</span>
          </div>
        </div>
        ${costAnalysis.minimum_projection?.months_if_minimum != null ? `
          <div class="alert alert-warning" style="margin-top:12px;font-size:0.85rem">
            ⚠ Si solo pagas el mínimo mensual (${fmtCurrency(costAnalysis.minimum_projection.monthly_minimum ?? 0, currency)}):
            pagarás en ${costAnalysis.minimum_projection.months_if_minimum} meses
            con <strong>${fmtCurrency(costAnalysis.minimum_projection.total_interest_if_minimum ?? 0, currency)} adicionales en intereses</strong>
            (fecha de liquidación estimada: ${costAnalysis.minimum_projection.payoff_date_minimum ?? '—'}).
          </div>` : ''}
      </div>` : '';

    modal.body.innerHTML = `
      <div class="stat-row" style="margin-bottom:16px">
        <div class="stat-chip">
          <span class="stat-chip-label">Saldo Actual</span>
          <span class="stat-chip-value negative">${fmtCurrency(debt.current_balance ?? debt.balance ?? 0, currency)}</span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip-label">Tasa</span>
          <span class="stat-chip-value">${(debt.interest_rate ?? 0).toFixed(2)}% EA</span>
        </div>
        <div class="stat-chip">
          <span class="stat-chip-label">Cuota</span>
          <span class="stat-chip-value">${fmtCurrency(debt.monthly_payment ?? 0, currency)}</span>
        </div>
      </div>
      ${installmentsSection}
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
                  <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(r.payment ?? r.total_payment ?? 0, currency)}</td>
                  <td class="td-right td-mono" style="font-size:0.8rem;color:var(--color-danger)">${fmtCurrency(r.interest ?? r.interest_payment ?? 0, currency)}</td>
                  <td class="td-right td-mono" style="font-size:0.8rem;color:var(--color-success)">${fmtCurrency(r.principal ?? r.principal_payment ?? 0, currency)}</td>
                  <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(r.ending_balance ?? r.balance ?? r.remaining_balance ?? 0, currency)}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      ` : '<div class="empty-state"><p>Sin tabla de amortización disponible</p></div>'}
      ${costSection}
    `;

    if (isCard) {
      modal.body.querySelector('#btnAddInstallment')?.addEventListener('click', () => {
        openInstallmentForm(debt.id, currency, () => openDebtDetail(debt));
      });
    }
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
      const result = await api.debts.simulate({ extra_payment: extra, strategy });
      modal.body.querySelector('#sim-result').innerHTML = `
        <div class="stat-row">
          <div class="stat-chip">
            <span class="stat-chip-label">Meses ahorrados</span>
            <span class="stat-chip-value">${result?.months_saved ?? '—'}</span>
          </div>
          <div class="stat-chip">
            <span class="stat-chip-label">Total intereses</span>
            <span class="stat-chip-value negative">${fmtCurrency(result?.total_interest ?? 0, currency)}</span>
          </div>
          <div class="stat-chip">
            <span class="stat-chip-label">Ahorro en intereses</span>
            <span class="stat-chip-value positive">${fmtCurrency(result?.interest_saved ?? 0, currency)}</span>
          </div>
          ${result?.payoff_date_extra ? `
          <div class="stat-chip">
            <span class="stat-chip-label">Fecha liquidación (con abono)</span>
            <span class="stat-chip-value">${result.payoff_date_extra}</span>
          </div>` : ''}
        </div>`;
    } catch (err) {
      modal.showError(err.message);
    }
  });
}

function openDebtForm(debt, onSaved) {
  const isEdit = debt != null;
  const today = new Date().toISOString().split('T')[0];

  const content = `
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Nombre</label>
        <input type="text" id="df-name" value="${sanitize(debt?.name ?? '')}" required>
      </div>
      <div class="form-group">
        <label class="form-label">Tipo</label>
        <select id="df-type">
          <option value="credit_card" ${(debt?.debt_type === 'credit_card') ? 'selected' : ''}>Tarjeta de crédito</option>
          <option value="credit_loan" ${(debt?.debt_type === 'credit_loan') ? 'selected' : ''}>Préstamo personal</option>
          <option value="mortgage"    ${(debt?.debt_type === 'mortgage')    ? 'selected' : ''}>Hipoteca</option>
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Institución</label>
        <input type="text" id="df-institution" value="${sanitize(debt?.institution ?? '')}">
      </div>
      <div class="form-group">
        <label class="form-label">Moneda</label>
        <select id="df-currency">
          <option value="COP" ${(debt?.currency_code ?? 'COP') === 'COP' ? 'selected' : ''}>COP</option>
          <option value="USD" ${debt?.currency_code === 'USD' ? 'selected' : ''}>USD</option>
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Monto original</label>
        <input type="number" id="df-original" value="${debt?.original_amount ?? ''}" step="0.01" min="0">
      </div>
      <div class="form-group">
        <label class="form-label">Saldo actual</label>
        <input type="number" id="df-balance" value="${debt?.current_balance ?? ''}" step="0.01" min="0">
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Tasa de interés (% EA)</label>
        <input type="number" id="df-rate" value="${debt?.interest_rate ?? ''}" step="0.01" min="0">
      </div>
      <div class="form-group">
        <label class="form-label">Cuota mensual</label>
        <input type="number" id="df-monthly" value="${debt?.monthly_payment ?? ''}" step="0.01" min="0">
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Fecha de inicio</label>
      <input type="text" id="df-start" value="${debt?.start_date ?? today}">
    </div>
    <div id="df-cc-fields" style="display:none">
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label">Límite de crédito</label>
          <input type="number" id="df-limit" value="${debt?.credit_limit ?? ''}" step="0.01" min="0">
        </div>
        <div class="form-group">
          <label class="form-label">Día de corte (1-31)</label>
          <input type="number" id="df-statement-day" value="${debt?.statement_day ?? ''}" min="1" max="31">
        </div>
      </div>
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label">Día de pago (1-31)</label>
          <input type="number" id="df-payment-day" value="${debt?.payment_due_day ?? ''}" min="1" max="31">
        </div>
        <div class="form-group">
          <label class="form-label">% pago mínimo</label>
          <input type="number" id="df-min-pct" value="${debt?.min_payment_percentage ?? ''}" step="0.01" min="0">
        </div>
      </div>
    </div>
  `;

  const modal = openModal({
    title: isEdit ? `Editar: ${debt.name}` : 'Nueva Deuda',
    size: 'lg',
    content,
    submitLabel: isEdit ? 'Guardar cambios' : 'Crear deuda',
    onSubmit: async () => {
      const name = modal.body.querySelector('#df-name').value.trim();
      if (!name) { modal.showError('El nombre es requerido'); return; }

      const dtype = modal.body.querySelector('#df-type').value;
      const data = {
        name,
        debt_type: dtype,
        institution: modal.body.querySelector('#df-institution').value.trim() || null,
        currency_code: modal.body.querySelector('#df-currency').value,
        original_amount: parseFloat(modal.body.querySelector('#df-original').value) || null,
        current_balance: parseFloat(modal.body.querySelector('#df-balance').value) || null,
        interest_rate: parseFloat(modal.body.querySelector('#df-rate').value) || null,
        monthly_payment: parseFloat(modal.body.querySelector('#df-monthly').value) || null,
        start_date: modal.body.querySelector('#df-start').value || null,
      };

      if (dtype === 'credit_card') {
        const limit = parseFloat(modal.body.querySelector('#df-limit').value);
        const stDay = parseInt(modal.body.querySelector('#df-statement-day').value);
        const pmDay = parseInt(modal.body.querySelector('#df-payment-day').value);
        const minPct = parseFloat(modal.body.querySelector('#df-min-pct').value);
        if (!isNaN(limit)) data.credit_limit = limit;
        if (!isNaN(stDay)) data.statement_day = stDay;
        if (!isNaN(pmDay)) data.payment_due_day = pmDay;
        if (!isNaN(minPct)) data.min_payment_percentage = minPct;
      }

      try {
        if (isEdit) {
          await api.debts.update(debt.id, data);
        } else {
          await api.debts.create(data);
        }
        modal.close();
        onSaved();
      } catch (err) {
        modal.showError(err.message);
      }
    },
  });

  // Toggle credit card fields based on type selection
  const typeSelect = modal.body.querySelector('#df-type');
  const ccFields   = modal.body.querySelector('#df-cc-fields');
  const toggleCC = () => { ccFields.style.display = typeSelect.value === 'credit_card' ? '' : 'none'; };
  typeSelect.addEventListener('change', toggleCC);
  toggleCC();

  // Init flatpickr on date field if available
  if (window.flatpickr) {
    const startInput = modal.body.querySelector('#df-start');
    startInput.type = 'text';
    startInput.setAttribute('autocomplete', 'off');
    flatpickr(startInput, { dateFormat: 'Y-m-d', altInput: true, altFormat: 'j M Y', allowInput: true, defaultDate: startInput.value || null });
  }
}

function openInstallmentForm(debtId, currency, onSaved) {
  const content = `
    <div class="form-group">
      <label class="form-label">Descripción</label>
      <input type="text" id="inst-desc" placeholder="Ej: iPhone 15 Pro" required>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Monto total</label>
        <input type="number" id="inst-total" step="0.01" min="0" placeholder="0">
      </div>
      <div class="form-group">
        <label class="form-label">Número de cuotas</label>
        <input type="number" id="inst-count" step="1" min="1" placeholder="12">
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Cuota mensual (se calcula automáticamente)</label>
      <input type="number" id="inst-monthly" step="0.01" min="0" placeholder="0">
    </div>
    <div class="form-group">
      <label class="form-label">Fecha de inicio</label>
      <input type="text" id="inst-start" value="${new Date().toISOString().split('T')[0]}">
    </div>
    <div class="form-group">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" id="inst-interest">
        <span class="form-label" style="margin:0">Incluye intereses</span>
      </label>
    </div>
  `;

  const modal = openModal({
    title: 'Agregar compra en cuotas',
    size: 'md',
    content,
    submitLabel: 'Agregar cuota',
    onSubmit: async () => {
      const description = modal.body.querySelector('#inst-desc').value.trim();
      if (!description) { modal.showError('La descripción es requerida'); return; }

      const total_amount = parseFloat(modal.body.querySelector('#inst-total').value);
      const installments_total = parseInt(modal.body.querySelector('#inst-count').value);
      const monthly_amount = parseFloat(modal.body.querySelector('#inst-monthly').value);

      if (isNaN(total_amount) || total_amount <= 0) { modal.showError('Ingresa un monto total válido'); return; }
      if (isNaN(installments_total) || installments_total < 1) { modal.showError('Ingresa un número de cuotas válido'); return; }

      const data = {
        description,
        total_amount,
        installments_total,
        monthly_amount: isNaN(monthly_amount) ? total_amount / installments_total : monthly_amount,
        start_date: modal.body.querySelector('#inst-start').value || null,
        has_interest: modal.body.querySelector('#inst-interest').checked,
      };

      try {
        await api.debts.createInstallment(debtId, data);
        modal.close();
        onSaved();
      } catch (err) {
        modal.showError(err.message);
      }
    },
  });

  // Auto-calculate monthly amount when total or count changes
  const totalInput   = modal.body.querySelector('#inst-total');
  const countInput   = modal.body.querySelector('#inst-count');
  const monthlyInput = modal.body.querySelector('#inst-monthly');
  const recalc = () => {
    const t = parseFloat(totalInput.value);
    const c = parseInt(countInput.value);
    if (!isNaN(t) && !isNaN(c) && c > 0) monthlyInput.value = (t / c).toFixed(2);
  };
  totalInput.addEventListener('input', recalc);
  countInput.addEventListener('input', recalc);

  if (window.flatpickr) {
    const startInput = modal.body.querySelector('#inst-start');
    startInput.setAttribute('autocomplete', 'off');
    flatpickr(startInput, { dateFormat: 'Y-m-d', altInput: true, altFormat: 'j M Y', allowInput: true, defaultDate: startInput.value || null });
  }
}
