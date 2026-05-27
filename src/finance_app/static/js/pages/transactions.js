import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, debounce, todayISO } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Transacciones';

let _accounts  = [];
let _categories= [];
let _filters   = { search: '', account_id: '', category_id: '', date_from: '', date_to: '', type: '', limit: 100 };

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    [_accounts, _categories] = await Promise.all([api.accounts.list(), api.categories.list()]);
    renderPage(container);
    await loadTransactions(container);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function renderPage(container) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text"><h1>Transacciones</h1></div>
      <div class="page-header-actions">
        <button class="btn btn-secondary btn-sm" id="btnTransfer">⇄ Transferencia</button>
        <button class="btn btn-primary btn-sm" id="btnNewTx">+ Nueva</button>
      </div>
    </div>

    <div class="filter-panel">
      <div class="filter-row">
        <div class="filter-search-field">
          <svg class="filter-search-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="8.5" cy="8.5" r="5.5"/><path d="M15 15l-3-3" stroke-linecap="round"/>
          </svg>
          <input type="search" id="f-search" class="filter-search-input" placeholder="Buscar beneficiario, memo…" value="${sanitize(_filters.search)}">
        </div>
        <button class="filter-quick-btn" id="btnQuickMonth">Este mes</button>
        <button class="filter-quick-btn" id="btnQuickLast30">30 días</button>
      </div>

      <div class="filter-row">
        <div class="filter-select-wrap" id="wrap-account">
          <select class="filter-select" id="f-account">
            <option value="">Cuenta</option>
            ${_accounts.map(a => `<option value="${a.id}" ${_filters.account_id == a.id ? 'selected' : ''}>${sanitize(a.name)}</option>`).join('')}
          </select>
        </div>
        <div class="filter-select-wrap" id="wrap-category">
          <select class="filter-select" id="f-category">
            <option value="">Categoría</option>
            ${(() => { const g = {}; _categories.forEach(c => { const k = c.category_group_name || ''; if (!g[k]) g[k] = []; g[k].push(c); }); return Object.entries(g).map(([k,cs]) => `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${_filters.category_id == c.id ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`).join(''); })()}
          </select>
        </div>
        <div class="filter-select-wrap" id="wrap-type">
          <select class="filter-select" id="f-type">
            <option value="">Tipo</option>
            <option value="expense"  ${_filters.type === 'expense'  ? 'selected' : ''}>Gasto</option>
            <option value="income"   ${_filters.type === 'income'   ? 'selected' : ''}>Ingreso</option>
            <option value="transfer" ${_filters.type === 'transfer' ? 'selected' : ''}>Transferencia</option>
          </select>
        </div>
        <div class="filter-divider"></div>
        <div class="filter-date-range" id="filter-date-range">
          <input type="date" id="f-from" class="filter-date" value="${_filters.date_from}" title="Desde">
          <span class="filter-date-sep">—</span>
          <input type="date" id="f-to" class="filter-date" value="${_filters.date_to}" title="Hasta">
        </div>
        <button class="filter-clear-btn" id="btnClearFilters">
          Limpiar <span class="filter-active-count" id="filterActiveCount" style="display:none">0</span>
        </button>
      </div>
    </div>

    <div id="tx-summary" style="display:flex;gap:8px;margin-bottom:12px;font-size:0.8125rem;color:var(--text-secondary)"></div>
    <div id="tx-table-wrap" class="table-wrap">
      <div class="page-loading" style="min-height:200px"><div class="spinner"></div></div>
    </div>
  `;

  bindFilters(container);
  updateFilterActiveStates(container);
  container.querySelector('#btnNewTx').addEventListener('click', () => openTxModal(null, container));
  container.querySelector('#btnTransfer').addEventListener('click', () => openTransferModal(container));
}

function bindFilters(container) {
  const doLoad = debounce(() => loadTransactions(container), 350);
  const doLoadAndUpdate = () => { updateFilterActiveStates(container); doLoad(); };

  container.querySelector('#f-search').addEventListener('input', e => { _filters.search = e.target.value; doLoadAndUpdate(); });
  container.querySelector('#f-account').addEventListener('change', e => { _filters.account_id = e.target.value; doLoadAndUpdate(); });
  container.querySelector('#f-category').addEventListener('change', e => { _filters.category_id = e.target.value; doLoadAndUpdate(); });
  container.querySelector('#f-type').addEventListener('change', e => { _filters.type = e.target.value; doLoadAndUpdate(); });
  container.querySelector('#f-from').addEventListener('change', e => { _filters.date_from = e.target.value; doLoadAndUpdate(); });
  container.querySelector('#f-to').addEventListener('change', e => { _filters.date_to = e.target.value; doLoadAndUpdate(); });

  container.querySelector('#btnQuickMonth').addEventListener('click', () => {
    const now = new Date();
    const y = now.getFullYear(), m = String(now.getMonth() + 1).padStart(2, '0');
    _filters.date_from = `${y}-${m}-01`;
    _filters.date_to   = `${y}-${m}-${new Date(y, now.getMonth() + 1, 0).getDate()}`;
    container.querySelector('#f-from').value = _filters.date_from;
    container.querySelector('#f-to').value   = _filters.date_to;
    updateFilterActiveStates(container);
    loadTransactions(container);
  });

  container.querySelector('#btnQuickLast30').addEventListener('click', () => {
    const now = new Date();
    const to = now.toISOString().slice(0, 10);
    const from = new Date(now - 30 * 864e5).toISOString().slice(0, 10);
    _filters.date_from = from;
    _filters.date_to   = to;
    container.querySelector('#f-from').value = from;
    container.querySelector('#f-to').value   = to;
    updateFilterActiveStates(container);
    loadTransactions(container);
  });

  container.querySelector('#btnClearFilters').addEventListener('click', () => {
    _filters = { search: '', account_id: '', category_id: '', date_from: '', date_to: '', type: '', limit: 100 };
    container.querySelector('#f-search').value   = '';
    container.querySelector('#f-account').value  = '';
    container.querySelector('#f-category').value = '';
    container.querySelector('#f-type').value     = '';
    container.querySelector('#f-from').value     = '';
    container.querySelector('#f-to').value       = '';
    updateFilterActiveStates(container);
    loadTransactions(container);
  });
}

function updateFilterActiveStates(container) {
  const setActive = (wrapId, selectId, isActive) => {
    const wrap = container.querySelector(wrapId);
    const sel  = container.querySelector(selectId);
    if (!wrap || !sel) return;
    wrap.classList.toggle('is-active', isActive);
    sel.classList.toggle('is-active', isActive);
  };

  setActive('#wrap-account',  '#f-account',  !!_filters.account_id);
  setActive('#wrap-category', '#f-category', !!_filters.category_id);
  setActive('#wrap-type',     '#f-type',     !!_filters.type);

  const dateActive = !!_filters.date_from || !!_filters.date_to;
  container.querySelector('#filter-date-range')?.classList.toggle('is-active', dateActive);

  const count = [_filters.account_id, _filters.category_id, _filters.type,
                  _filters.date_from || _filters.date_to, _filters.search]
                .filter(Boolean).length;
  const badge = container.querySelector('#filterActiveCount');
  if (badge) { badge.textContent = count; badge.style.display = count ? '' : 'none'; }
}

async function loadTransactions(container) {
  const wrap = container.querySelector('#tx-table-wrap');
  if (!wrap) return;
  wrap.innerHTML = '<div class="page-loading" style="min-height:200px"><div class="spinner"></div></div>';

  try {
    const params = {};
    if (_filters.search)      params.search      = _filters.search;
    if (_filters.account_id)  params.account_id  = _filters.account_id;
    if (_filters.category_id) params.category_id = _filters.category_id;
    if (_filters.date_from)   params.start_date  = _filters.date_from;
    if (_filters.date_to)     params.end_date    = _filters.date_to;
    if (_filters.type)        params.transaction_type = _filters.type;
    params.limit = _filters.limit;

    const resp = await api.transactions.list(params);
    const txList = Array.isArray(resp) ? resp : (resp?.transactions ?? resp?.items ?? []);

    // Summary — use cop_amount (pre-converted) so USD accounts don't pollute the COP total
    const income  = txList.filter(t => (t.amount ?? 0) >= 0 && !t.transfer_account_id)
                          .reduce((s,t) => s + Math.abs(t.cop_amount ?? t.amount ?? 0), 0);
    const expense = txList.filter(t => (t.amount ?? 0) < 0  && !t.transfer_account_id)
                          .reduce((s,t) => s + Math.abs(t.cop_amount ?? t.amount ?? 0), 0);
    const summary = container.querySelector('#tx-summary');
    if (summary) {
      summary.innerHTML = `
        <span>${txList.length} resultado${txList.length !== 1 ? 's' : ''}</span>
        <span style="margin-left:8px;color:var(--color-success)">↑ ${fmtCurrency(income, 'COP')}</span>
        <span style="margin-left:8px;color:var(--color-danger)">↓ ${fmtCurrency(expense, 'COP')}</span>
      `;
    }

    if (!txList.length) {
      wrap.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📋</div><h3>Sin transacciones</h3><p>No se encontraron resultados con los filtros aplicados.</p></div>`;
      return;
    }

    wrap.innerHTML = `
      <table>
        <thead>
          <tr>
            <th style="width:100px">Fecha</th>
            <th>Beneficiario / Desc.</th>
            <th>Cuenta</th>
            <th>Categoría</th>
            <th class="td-right" style="width:140px">Monto</th>
            <th style="width:60px"></th>
          </tr>
        </thead>
        <tbody>
          ${txList.map(tx => txRow(tx)).join('')}
        </tbody>
      </table>
    `;

    wrap.querySelectorAll('[data-edit-tx]').forEach(btn => {
      const id = parseInt(btn.dataset.editTx);
      const tx = txList.find(t => t.id === id);
      btn.addEventListener('click', () => openTxModal(tx, container));
    });

    wrap.querySelectorAll('[data-delete-tx]').forEach(btn => {
      const id = parseInt(btn.dataset.deleteTx);
      btn.addEventListener('click', () => deleteTx(id, container));
    });

  } catch (err) {
    wrap.innerHTML = `<div class="alert alert-danger" style="margin:16px">${sanitize(err.message)}</div>`;
  }
}

function txRow(tx) {
  const isTransfer = tx.transfer_account_id != null;
  const isIncome = !isTransfer && (tx.amount ?? 0) >= 0;
  const cls = isIncome ? 'positive' : isTransfer ? '' : 'negative';
  const sign = isIncome ? '+' : isTransfer ? '⇄ ' : '-';

  return `
    <tr>
      <td class="td-soft" style="font-size:0.8rem;white-space:nowrap">${fmtDate(tx.date)}</td>
      <td style="font-size:0.8125rem">
        <div style="font-weight:500">${sanitize(tx.payee_name || tx.memo || '—')}</div>
        ${tx.memo ? `<div style="font-size:0.72rem;color:var(--text-soft)">${sanitize(tx.memo)}</div>` : ''}
      </td>
      <td class="td-soft" style="font-size:0.8rem">${sanitize(tx.account_name ?? '—')}</td>
      <td style="font-size:0.8rem">${sanitize(tx.category_name ?? '—')}</td>
      <td class="td-right td-mono amount ${cls}" style="font-size:0.8125rem">
        ${sign}${fmtCurrency(Math.abs(tx.amount ?? 0), tx.currency?.code ?? 'COP')}
      </td>
      <td style="text-align:right">
        <button class="btn btn-ghost btn-xs" data-edit-tx="${tx.id}" title="Editar">✏</button>
        <button class="btn btn-ghost btn-xs" style="color:var(--color-danger)" data-delete-tx="${tx.id}" title="Eliminar">✕</button>
      </td>
    </tr>`;
}

function txFormHtml(tx) {
  const t = tx ?? {};
  return `
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Fecha</label>
        <input type="date" id="tf-date" value="${t.date ?? todayISO()}">
      </div>
      <div class="form-group">
        <label class="form-label required">Tipo</label>
        <select id="tf-type">
          <option value="expense" ${(t.amount ?? 0) < 0 || (!t.id) ? 'selected' : ''}>Gasto</option>
          <option value="income"  ${(t.amount ?? 0) >= 0 && t.id ? 'selected' : ''}>Ingreso</option>
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Monto</label>
        <input type="number" id="tf-amount" value="${t.amount ?? ''}" step="0.01" min="0" placeholder="0.00">
      </div>
      <div class="form-group">
        <label class="form-label">Moneda</label>
        <select id="tf-currency">
          <option value="COP" ${(t.currency?.code ?? 'COP') === 'COP' ? 'selected' : ''}>COP</option>
          <option value="USD" ${t.currency?.code === 'USD' ? 'selected' : ''}>USD</option>
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Cuenta</label>
        <select id="tf-account">
          <option value="">— seleccionar —</option>
          ${_accounts.map(a => `<option value="${a.id}" ${t.account_id == a.id ? 'selected' : ''}>${sanitize(a.name)}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Categoría</label>
        <select id="tf-category">
          <option value="">— sin categoría —</option>
          ${(() => { const g = {}; _categories.forEach(c => { const k = c.category_group_name || ''; if (!g[k]) g[k] = []; g[k].push(c); }); return Object.entries(g).map(([k,cs]) => `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${t.category_id == c.id ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`).join(''); })()}
        </select>
      </div>
    </div>
    <div class="form-group" style="margin-bottom:16px">
      <label class="form-label">Beneficiario / Descripción</label>
      <input type="text" id="tf-payee" value="${sanitize(t.payee_name ?? '')}" placeholder="Ej: Éxito">
    </div>
    <div class="form-group">
      <label class="form-label">Memo / Nota</label>
      <input type="text" id="tf-memo" value="${sanitize(t.memo ?? '')}" placeholder="Nota adicional">
    </div>
  `;
}

function openTxModal(tx, container) {
  const isEdit = !!tx;
  openModal({
    title: isEdit ? 'Editar Transacción' : 'Nueva Transacción',
    content: txFormHtml(tx),
    submitLabel: isEdit ? 'Actualizar' : 'Guardar',
    onSubmit: async (body) => {
      const currencyIdMap = { COP: 1, USD: 2 };
      const currCode = body.querySelector('#tf-currency').value;
      const data = {
        date:        body.querySelector('#tf-date').value,
        amount:      parseFloat(body.querySelector('#tf-amount').value),
        currency_id: currencyIdMap[currCode] ?? 1,
        account_id:  parseInt(body.querySelector('#tf-account').value) || null,
        category_id: parseInt(body.querySelector('#tf-category').value) || null,
        type:        body.querySelector('#tf-type').value,
        payee_name:  body.querySelector('#tf-payee').value.trim() || null,
        memo:        body.querySelector('#tf-memo').value.trim() || null,
      };
      if (!data.date || !data.amount || !data.account_id) throw new Error('Fecha, monto y cuenta son obligatorios');
      if (isEdit) {
        await api.transactions.update(tx.id, data);
        toast.success('Transacción actualizada');
      } else {
        await api.transactions.create(data);
        toast.success('Transacción creada');
      }
      await loadTransactions(container);
    },
  });
}

function openTransferModal(container) {
  openModal({
    title: 'Nueva Transferencia',
    size: 'md',
    content: `
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label required">Cuenta Origen</label>
          <select id="tr-from">
            <option value="">— seleccionar —</option>
            ${_accounts.map(a => `<option value="${a.id}">${sanitize(a.name)}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label class="form-label required">Cuenta Destino</label>
          <select id="tr-to">
            <option value="">— seleccionar —</option>
            ${_accounts.map(a => `<option value="${a.id}">${sanitize(a.name)}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label required">Monto</label>
          <input type="number" id="tr-amount" step="0.01" min="0" placeholder="0.00">
        </div>
        <div class="form-group">
          <label class="form-label required">Fecha</label>
          <input type="date" id="tr-date" value="${todayISO()}">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Descripción</label>
        <input type="text" id="tr-desc" placeholder="Ej: Fondos para gastos">
      </div>
    `,
    submitLabel: 'Transferir',
    onSubmit: async (body) => {
      const fromId  = parseInt(body.querySelector('#tr-from').value);
      const toId    = parseInt(body.querySelector('#tr-to').value);
      const amount  = parseFloat(body.querySelector('#tr-amount').value);
      const date    = body.querySelector('#tr-date').value;
      const desc    = body.querySelector('#tr-desc').value.trim();
      if (!fromId || !toId || !amount || !date) throw new Error('Todos los campos son obligatorios');
      if (fromId === toId) throw new Error('Las cuentas deben ser distintas');
      const currencyIdMap = { COP: 1, USD: 2 };
      const fromAcct = _accounts.find(a => a.id === fromId);
      const toAcct   = _accounts.find(a => a.id === toId);
      await api.transactions.transfer({
        from_account_id: fromId, to_account_id: toId, amount, date,
        from_currency_id: currencyIdMap[fromAcct?.currency?.code] ?? 1,
        to_currency_id:   currencyIdMap[toAcct?.currency?.code]   ?? 1,
        memo: desc || undefined,
      });
      toast.success('Transferencia registrada');
      await loadTransactions(container);
    },
  });
}

async function deleteTx(id, container) {
  if (!confirm('¿Eliminar esta transacción?')) return;
  try {
    await api.transactions.delete(id);
    toast.success('Transacción eliminada');
    await loadTransactions(container);
  } catch (err) {
    toast.error(err.message);
  }
}
