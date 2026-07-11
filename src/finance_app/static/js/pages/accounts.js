import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, accountTypeLabel, accountTypeIcon } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Cuentas';

let _accounts = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    _accounts = await api.accounts.list();
    render(container, _accounts);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container, accounts) {
  const grouped = groupByType(accounts);

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Cuentas</h1>
        <p>${accounts.length} cuenta${accounts.length !== 1 ? 's' : ''} registrada${accounts.length !== 1 ? 's' : ''}</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-primary" id="btnNewAccount">+ Nueva Cuenta</button>
      </div>
    </div>

    ${summaryBanner(accounts)}
    ${Object.entries(grouped).map(([type, list]) => accountGroup(type, list)).join('')}
  `;

  container.querySelector('#btnNewAccount')?.addEventListener('click', () => openAccountModal(null, container));

  container.querySelectorAll('[data-edit-account]').forEach(btn => {
    const id = parseInt(btn.dataset.editAccount);
    const acct = accounts.find(a => a.id === id);
    btn.addEventListener('click', () => openAccountModal(acct, container));
  });

  container.querySelectorAll('[data-adjust-account]').forEach(btn => {
    const id = parseInt(btn.dataset.adjustAccount);
    const acct = accounts.find(a => a.id === id);
    btn.addEventListener('click', () => openAdjustModal(acct, container));
  });
}

function groupByType(accounts) {
  const order = ['savings','checking','cash','credit_card','credit_loan','mortgage','cdt','investment'];
  const map = {};
  for (const a of accounts) {
    (map[a.type] ??= []).push(a);
  }
  const result = {};
  for (const type of order) {
    if (map[type]?.length) result[type] = map[type];
  }
  for (const [type, list] of Object.entries(map)) {
    if (!result[type]) result[type] = list;
  }
  return result;
}

function summaryBanner(accounts) {
  const byCurrency = {};
  for (const a of accounts) {
    const cur = a.currency?.code ?? 'COP';
    byCurrency[cur] = (byCurrency[cur] ?? 0) + (a.balance ?? 0);
  }
  return `
    <div class="stat-row">
      ${Object.entries(byCurrency).map(([cur, total]) => `
        <div class="stat-chip">
          <span class="stat-chip-label">Balance ${cur}</span>
          <span class="stat-chip-value amount ${total >= 0 ? 'text-success' : 'text-danger'}">
            ${fmtCurrency(total, cur)}
          </span>
        </div>
      `).join('')}
      <div class="stat-chip">
        <span class="stat-chip-label">Cuentas</span>
        <span class="stat-chip-value">${accounts.length}</span>
      </div>
    </div>`;
}

function accountGroup(type, accounts) {
  return `
    <div class="mb-3">
      <h3 class="text-soft" style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 12px;font-weight:600">
        ${accountTypeIcon(type)} ${accountTypeLabel(type)}
      </h3>
      <div class="section-grid cols-auto">
        ${accounts.map(a => accountCard(a)).join('')}
      </div>
    </div>`;
}

function accountCard(a) {
  const isDebt = ['credit_card','credit_loan','mortgage'].includes(a.type);
  const balance = a.balance ?? 0;
  const balanceClass = isDebt ? 'text-danger' : balance >= 0 ? 'text-success' : 'text-danger';
  const currCode = a.currency?.code ?? 'COP';

  let utilization = '';
  if (a.type === 'credit_card' && a.credit_limit) {
    const used = Math.abs(balance);
    const pct  = Math.min(100, (used / a.credit_limit) * 100);
    const cls  = pct >= 80 ? 'danger' : pct >= 50 ? 'warning' : 'ok';
    utilization = `
      <div class="mt-2">
        <div class="flex justify-between mt-1 mb-1" style="font-size:0.72rem">
          <span class="text-soft">Utilización</span>
          <span class="text-soft">${pct.toFixed(0)}%</span>
        </div>
        <div class="progress-wrap">
          <div class="progress-fill ${cls}" style="width:${pct}%"></div>
        </div>
        <div class="text-soft mt-1" style="font-size:0.72rem">
          Cupo: <span class="amount">${fmtCurrency(a.credit_limit, currCode)}</span>
        </div>
      </div>`;
  }

  return `
    <div class="card" style="padding:0">
      <div style="padding:16px 20px">
        <div class="flex justify-between items-center mb-2">
          <div>
            <div style="font-weight:600;font-size:0.9375rem">${sanitize(a.name)}</div>
            <div class="text-soft" style="font-size:0.75rem">${sanitize(a.country ?? '')}</div>
          </div>
          <span class="badge badge-neutral" style="font-size:0.65rem">${currCode}</span>
        </div>
        <div class="amount ${balanceClass}" style="font-size:1.375rem;font-weight:600;margin-top:8px">
          ${fmtCurrency(balance, currCode)}
        </div>
        ${utilization}
        ${isDebt && a.loan_start_date ? `
          <div class="text-soft mt-2" style="font-size:0.72rem">
            Inicio: <span class="amount">${a.loan_start_date}</span>
          </div>` : ''}
        ${a.notes ? `
          <div class="text-soft mt-2" style="font-size:0.72rem;font-style:italic">
            ${sanitize(a.notes)}
          </div>` : ''}
      </div>
      <div class="flex gap-1" style="padding:10px 20px;border-top:1px solid var(--fin-border);background:var(--fin-surface-2)">
        ${a.type !== 'mortgage' ? `<button class="btn btn-ghost btn-xs" data-adjust-account="${a.id}">Ajustar saldo</button>` : ''}
        <button class="btn btn-ghost btn-xs" data-edit-account="${a.id}">Editar</button>
      </div>
    </div>`;
}

function accountFormHtml(acct) {
  const types = ['savings','checking','credit_card','credit_loan','mortgage','cdt','investment','cash'];
  const currencies = ['COP', 'USD'];
  const a = acct ?? {};

  return `
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Nombre</label>
        <input type="text" id="af-name" value="${sanitize(a.name ?? '')}" placeholder="Ej: Davivienda Ahorros">
      </div>
      <div class="form-group">
        <label class="form-label required">Tipo</label>
        <select id="af-type">
          ${types.map(t => `<option value="${t}" ${a.type === t ? 'selected' : ''}>${accountTypeLabel(t)}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group" id="af-balance-group" style="${a.type === 'mortgage' ? 'display:none' : ''}">
        <label class="form-label">Saldo Actual</label>
        <input type="number" id="af-balance" value="${a.balance ?? ''}" step="0.01" placeholder="0">
      </div>
      <div class="form-group" id="af-mortgage-balance-note" style="${a.type === 'mortgage' ? '' : 'display:none'}">
        <label class="form-label">Saldo Actual</label>
        <input type="text" value="Se calcula automáticamente" readonly disabled>
      </div>
      <div class="form-group">
        <label class="form-label">Moneda</label>
        <select id="af-currency">
          ${currencies.map(c => `<option value="${c}" ${(a.currency ?? 'COP') === c ? 'selected' : ''}>${c}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">País / Institución</label>
        <input type="text" id="af-institution" value="${sanitize(a.country ?? '')}" placeholder="Ej: Colombia">
      </div>
      <div class="form-group" id="af-limit-group" style="${!a.credit_limit ? 'display:none' : ''}">
        <label class="form-label">Cupo / Monto Original</label>
        <input type="number" id="af-limit" value="${a.credit_limit ?? a.original_amount ?? ''}" step="0.01" placeholder="0">
      </div>
    </div>
    <div class="form-row cols-2" id="af-debt-fields" style="${!['credit_loan','mortgage'].includes(a.type) ? 'display:none' : ''}">
      <div class="form-group">
        <label class="form-label">Tasa de Interés (% EA)</label>
        <input type="number" id="af-rate" value="${a.interest_rate ?? ''}" step="0.01" placeholder="0.00">
      </div>
      <div class="form-group">
        <label class="form-label">Plazo (años)</label>
        <input type="number" id="af-years" value="${a.loan_years ?? ''}" step="1" min="1" placeholder="20">
      </div>
    </div>
    <div class="form-row cols-2" id="af-debt-fields-2" style="${!['credit_loan','mortgage'].includes(a.type) ? 'display:none' : ''}">
      <div class="form-group">
        <label class="form-label">Fecha de Inicio</label>
        <input type="date" id="af-start-date" value="${a.loan_start_date ?? ''}">
      </div>
      <div class="form-group">
        <label class="form-label">Cuota calculada</label>
        <input type="text" id="af-calculated-payment" value="" placeholder="—" readonly disabled>
      </div>
    </div>
    <div class="form-row cols-2" id="af-debt-fields-3" style="${!['credit_loan','mortgage'].includes(a.type) ? 'display:none' : ''}">
      <div class="form-group" id="af-actual-payment-group" style="${a.type === 'mortgage' ? 'display:none' : ''}">
        <label class="form-label">Cuota real que pagas</label>
        <input type="number" id="af-actual-payment" value="${a.actual_payment_amount ?? a.monthly_payment ?? ''}" step="0.01" placeholder="Igual a la calculada si la dejas vacía">
      </div>
      <div class="form-group" style="display:flex;flex-direction:column;justify-content:center;gap:6px">
        <label class="flex items-center gap-1" style="font-size:0.82rem">
          <input type="checkbox" id="af-has-insurance" ${a.has_insurance ? 'checked' : ''}>
          La cuota incluye seguros
        </label>
        <label class="flex items-center gap-1" id="af-includes-principal-group" style="font-size:0.82rem;${a.type === 'mortgage' ? 'display:none' : ''}">
          <input type="checkbox" id="af-includes-principal" ${a.includes_principal_payment ? 'checked' : ''}>
          La cuota incluye abono a capital extra
        </label>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Notas</label>
      <textarea id="af-notes" rows="2">${sanitize(a.notes ?? '')}</textarea>
    </div>
  `;
}

function calculateMonthlyPayment(principal, annualRatePct, years) {
  if (!principal || !years || annualRatePct == null) return null;
  const rate = annualRatePct / 100;
  if (rate === 0) return principal / (years * 12);
  const monthlyRate = Math.pow(1 + rate, 1 / 12) - 1;
  const n = years * 12;
  const factor = Math.pow(1 + monthlyRate, n);
  return principal * (monthlyRate * factor) / (factor - 1);
}

function refreshCalculatedPayment(container) {
  const limitEl = container.querySelector('#af-limit');
  const rateEl = container.querySelector('#af-rate');
  const yearsEl = container.querySelector('#af-years');
  const outEl = container.querySelector('#af-calculated-payment');
  const actualEl = container.querySelector('#af-actual-payment');
  if (!outEl) return;
  const principal = parseFloat(limitEl?.value || '');
  const rate = parseFloat(rateEl?.value || '');
  const years = parseInt(yearsEl?.value || '', 10);
  const payment = calculateMonthlyPayment(principal, rate, years);
  if (payment != null && !Number.isNaN(payment)) {
    outEl.value = fmtCurrency(payment, 'COP');
    if (actualEl && !actualEl.value) actualEl.placeholder = `Ej: ${fmtCurrency(payment, 'COP')}`;
  } else {
    outEl.value = '';
  }
}

function openAccountModal(acct, container) {
  const isEdit = !!acct;
  const modal = openModal({
    title: isEdit ? `Editar: ${acct.name}` : 'Nueva Cuenta',
    size: 'md',
    content: accountFormHtml(acct),
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const currencyIdMap = { COP: 1, USD: 2 };
      const currencyCode = body.querySelector('#af-currency').value;
      const data = {
        name:        body.querySelector('#af-name').value.trim(),
        type:        body.querySelector('#af-type').value,
        balance:     parseFloat(body.querySelector('#af-balance').value || '0'),
        currency_id: currencyIdMap[currencyCode] ?? 1,
        country:     body.querySelector('#af-institution').value.trim() || null,
        notes:       body.querySelector('#af-notes').value.trim() || null,
      };
      const limit      = body.querySelector('#af-limit')?.value;
      const rate       = body.querySelector('#af-rate')?.value;
      const years      = body.querySelector('#af-years')?.value;
      const startDate  = body.querySelector('#af-start-date')?.value;
      const actualPay  = body.querySelector('#af-actual-payment')?.value;
      const hasInsurance     = body.querySelector('#af-has-insurance')?.checked;
      const includesCapital  = body.querySelector('#af-includes-principal')?.checked;
      if (limit)     data.credit_limit = parseFloat(limit);
      if (limit)     data.original_amount = parseFloat(limit);
      if (rate)      data.interest_rate = parseFloat(rate);
      if (years)     data.loan_years = parseInt(years, 10);
      if (startDate) data.loan_start_date = startDate;
      if (data.type === 'mortgage') {
        // Hipoteca: solo los 4 campos base + seguros informativo. La cuota, el saldo
        // y todo lo demás se derivan en el backend — no se envía saldo manual ni
        // cuota real/abono extra.
        delete data.balance;
        data.has_insurance = !!hasInsurance;
      } else if (data.type === 'credit_loan') {
        if (actualPay) data.actual_payment_amount = parseFloat(actualPay);
        data.has_insurance = !!hasInsurance;
        data.includes_principal_payment = !!includesCapital;
      }

      if (!data.name) throw new Error('El nombre es obligatorio');
      if (data.type === 'mortgage' && (!data.original_amount || !data.interest_rate || !data.loan_years || !data.loan_start_date)) {
        throw new Error('Una hipoteca requiere monto inicial, tasa de interés, plazo (años) y fecha de inicio');
      }

      if (isEdit) {
        await api.accounts.update(acct.id, data);
        toast.success('Cuenta actualizada');
      } else {
        await api.accounts.create(data);
        toast.success('Cuenta creada');
      }
      _accounts = await api.accounts.list();
      render(container, _accounts);
    },
  });

  // Show/hide debt fields on type change
  const typeEl = document.getElementById('af-type');
  const debtFieldGroups = [
    document.getElementById('af-debt-fields'),
    document.getElementById('af-debt-fields-2'),
    document.getElementById('af-debt-fields-3'),
  ];
  const limitGroup = document.getElementById('af-limit-group');
  const balanceGroup = document.getElementById('af-balance-group');
  const mortgageBalanceNote = document.getElementById('af-mortgage-balance-note');
  const actualPaymentGroup = document.getElementById('af-actual-payment-group');
  const includesPrincipalGroup = document.getElementById('af-includes-principal-group');
  typeEl?.addEventListener('change', () => {
    const t = typeEl.value;
    const showDebt = ['credit_loan', 'mortgage'].includes(t);
    const isMortgage = t === 'mortgage';
    debtFieldGroups.forEach(el => { if (el) el.style.display = showDebt ? '' : 'none'; });
    limitGroup.style.display = ['credit_card', 'credit_loan', 'mortgage'].includes(t) ? '' : 'none';
    if (balanceGroup) balanceGroup.style.display = isMortgage ? 'none' : '';
    if (mortgageBalanceNote) mortgageBalanceNote.style.display = isMortgage ? '' : 'none';
    if (actualPaymentGroup) actualPaymentGroup.style.display = isMortgage ? 'none' : '';
    if (includesPrincipalGroup) includesPrincipalGroup.style.display = isMortgage ? 'none' : '';
  });

  // Live preview of the calculated (French-system) monthly payment
  ['#af-limit', '#af-rate', '#af-years'].forEach(sel => {
    document.querySelector(sel)?.addEventListener('input', () => refreshCalculatedPayment(document));
  });
  refreshCalculatedPayment(document);
}

function openAdjustModal(acct, container) {
  openModal({
    title: `Ajustar saldo: ${acct.name}`,
    size: 'sm',
    content: `
      <div class="form-group mb-3">
        <label class="form-label">Saldo actual registrado</label>
        <div class="amount" style="font-size:1.125rem;font-weight:600;padding:8px 0">
          ${fmtCurrency(acct.balance ?? 0, acct.currency?.code ?? 'COP')}
        </div>
      </div>
      <div class="form-group mb-3">
        <label class="form-label required">Saldo real del extracto</label>
        <input type="number" id="adj-balance" value="${acct.balance ?? ''}" step="0.01">
      </div>
      <div class="form-group">
        <label class="form-label">Nota (opcional)</label>
        <input type="text" id="adj-note" placeholder="Ej: Conciliación mayo 2026">
      </div>
    `,
    submitLabel: 'Ajustar',
    onSubmit: async (body) => {
      const newBalance = parseFloat(body.querySelector('#adj-balance').value);
      const note = body.querySelector('#adj-note').value.trim();
      if (isNaN(newBalance)) throw new Error('Ingresa un saldo válido');
      await api.accounts.adjust(acct.id, { new_balance: newBalance, note: note || undefined });
      toast.success('Saldo ajustado');
      _accounts = await api.accounts.list();
      render(container, _accounts);
    },
  });
}
