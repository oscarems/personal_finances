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
          <span class="stat-chip-value" style="color:${total >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}">
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
    <div style="margin-bottom:24px">
      <h3 style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);margin:0 0 12px;font-weight:600">
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
  const balanceClass = isDebt ? 'negative' : balance >= 0 ? 'positive' : 'negative';
  const currCode = a.currency?.code ?? 'COP';

  let utilization = '';
  if (a.type === 'credit_card' && a.credit_limit) {
    const used = Math.abs(balance);
    const pct  = Math.min(100, (used / a.credit_limit) * 100);
    const cls  = pct >= 80 ? 'danger' : pct >= 50 ? 'warning' : 'ok';
    utilization = `
      <div style="margin-top:12px">
        <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--text-soft);margin-bottom:4px">
          <span>Utilización</span>
          <span>${pct.toFixed(0)}%</span>
        </div>
        <div class="progress-wrap">
          <div class="progress-fill ${cls}" style="width:${pct}%"></div>
        </div>
        <div style="font-size:0.72rem;color:var(--text-soft);margin-top:4px">
          Cupo: ${fmtCurrency(a.credit_limit, currCode)}
        </div>
      </div>`;
  }

  return `
    <div class="card" style="padding:0">
      <div style="padding:16px 20px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
          <div>
            <div style="font-weight:600;font-size:0.9375rem">${sanitize(a.name)}</div>
            <div style="font-size:0.75rem;color:var(--text-soft)">${sanitize(a.country ?? '')}</div>
          </div>
          <span class="badge badge-neutral" style="font-size:0.65rem">${currCode}</span>
        </div>
        <div class="amount ${balanceClass}" style="font-size:1.375rem;font-weight:600;margin-top:8px">
          ${fmtCurrency(balance, currCode)}
        </div>
        ${utilization}
        ${a.notes ? `
          <div style="font-size:0.72rem;color:var(--text-soft);margin-top:8px;font-style:italic">
            ${sanitize(a.notes)}
          </div>` : ''}
      </div>
      <div style="display:flex;gap:8px;padding:10px 20px;border-top:1px solid var(--border-muted);background:var(--bg-surface-muted)">
        <button class="btn btn-ghost btn-xs" data-adjust-account="${a.id}">Ajustar saldo</button>
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
      <div class="form-group">
        <label class="form-label">Saldo Actual</label>
        <input type="number" id="af-balance" value="${a.balance ?? ''}" step="0.01" placeholder="0">
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
        <label class="form-label">Cuota Mensual</label>
        <input type="number" id="af-payment" value="${a.monthly_payment ?? ''}" step="0.01" placeholder="0">
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Notas</label>
      <textarea id="af-notes" rows="2">${sanitize(a.notes ?? '')}</textarea>
    </div>
  `;
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
      const limit = body.querySelector('#af-limit')?.value;
      const rate  = body.querySelector('#af-rate')?.value;
      const pay   = body.querySelector('#af-payment')?.value;
      if (limit)   data.credit_limit = parseFloat(limit);
      if (rate)    data.interest_rate = parseFloat(rate);
      if (pay)     data.monthly_payment = parseFloat(pay);

      if (!data.name) throw new Error('El nombre es obligatorio');

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
  const debtFields = document.getElementById('af-debt-fields');
  const limitGroup = document.getElementById('af-limit-group');
  typeEl?.addEventListener('change', () => {
    const t = typeEl.value;
    debtFields.style.display = ['credit_loan','mortgage'].includes(t) ? '' : 'none';
    limitGroup.style.display = ['credit_card','credit_loan','mortgage'].includes(t) ? '' : 'none';
  });
}

function openAdjustModal(acct, container) {
  openModal({
    title: `Ajustar saldo: ${acct.name}`,
    size: 'sm',
    content: `
      <div class="form-group" style="margin-bottom:16px">
        <label class="form-label">Saldo actual registrado</label>
        <div style="font-family:var(--font-mono);font-size:1.125rem;font-weight:600;padding:8px 0;color:var(--text-primary)">
          ${fmtCurrency(acct.balance ?? 0, acct.currency?.code ?? 'COP')}
        </div>
      </div>
      <div class="form-group" style="margin-bottom:16px">
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
