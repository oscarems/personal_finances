import * as api from '../api/client.js';
import { sanitize } from '../utils.js';
import { toast } from '../components/toast.js';

export const title = 'Reconciliación';

export async function mount(container) {
  let accounts = [];
  try {
    accounts = await api.accounts.list();
  } catch (e) {
    container.innerHTML = `<div class="alert alert-danger">Error al cargar cuentas: ${sanitize(e.message)}</div>`;
    return;
  }

  const budgetAccounts = accounts.filter(a => !['credit_loan', 'mortgage'].includes(a.type));

  container.innerHTML = renderStep1(budgetAccounts);
  bindStep1(container, budgetAccounts);
}

// ── Step 1: Account + statement info ──────────────────────

function renderStep1(accounts) {
  const today = new Date().toISOString().slice(0, 10);
  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1 class="page-title">Reconciliación de Cuentas</h1>
        <p class="page-subtitle">Concilia tu registro con el extracto bancario</p>
      </div>
    </div>
    <div class="card" style="max-width:520px;margin:0 auto">
      <div class="card-header"><h3 class="card-title">Iniciar reconciliación</h3></div>
      <div style="padding:24px;display:flex;flex-direction:column;gap:16px">
        <div class="form-group">
          <label class="form-label">Cuenta</label>
          <select id="r-account" class="form-control">
            <option value="">Selecciona una cuenta…</option>
            ${accounts.map(a => `<option value="${a.id}">${sanitize(a.name)} (${a.currency?.code ?? 'COP'})</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Fecha del extracto</label>
          <input id="r-date" type="date" class="form-control" value="${today}">
        </div>
        <div class="form-group">
          <label class="form-label">Saldo del extracto</label>
          <input id="r-balance" type="number" step="0.01" class="form-control" placeholder="0.00">
        </div>
        <button id="r-start" class="btn btn-primary">Iniciar reconciliación →</button>
      </div>
    </div>
  `;
}

function bindStep1(container, accounts) {
  container.querySelector('#r-start').addEventListener('click', async () => {
    const accountId = parseInt(container.querySelector('#r-account').value);
    const statementDate = container.querySelector('#r-date').value;
    const statementBalance = parseFloat(container.querySelector('#r-balance').value);

    if (!accountId) return toast('Selecciona una cuenta', 'warning');
    if (!statementDate) return toast('Ingresa la fecha del extracto', 'warning');
    if (isNaN(statementBalance)) return toast('Ingresa el saldo del extracto', 'warning');

    const account = accounts.find(a => a.id === accountId);
    await loadStep2(container, account, statementDate, statementBalance);
  });
}

// ── Step 2: Transaction checklist ─────────────────────────

async function loadStep2(container, account, statementDate, statementBalance) {
  container.innerHTML = `<div style="padding:40px;text-align:center"><div class="spinner"></div><p style="margin-top:12px;color:var(--fin-ink-3)">Cargando transacciones…</p></div>`;

  try {
    const [summary, txResp] = await Promise.all([
      api.reconciliation.summary({ account_id: account.id, statement_date: statementDate }),
      api.transactions.list({ account_id: account.id, limit: 500 }),
    ]);

    const transactions = (Array.isArray(txResp) ? txResp : txResp?.transactions ?? txResp?.items ?? [])
      .filter(tx => !tx.is_adjustment)
      .sort((a, b) => new Date(b.date) - new Date(a.date));

    container.innerHTML = renderStep2(account, statementDate, statementBalance, transactions, summary);
    bindStep2(container, account, statementDate, statementBalance, transactions);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">Error: ${sanitize(err.message)}</div>`;
  }
}

function renderStep2(account, statementDate, statementBalance, transactions, summary) {
  const fmt = v => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(v);
  const cleared = transactions.filter(tx => tx.cleared);
  const clearedSum = cleared.reduce((s, tx) => s + (tx.amount ?? 0), 0);
  const diff = statementBalance - clearedSum;

  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1 class="page-title">Reconciliación — ${sanitize(account.name)}</h1>
        <p class="page-subtitle">Extracto al ${statementDate} · Marca las transacciones confirmadas</p>
      </div>
      <button id="r-back" class="btn btn-ghost">← Volver</button>
    </div>

    <div id="r-panel" class="card" style="position:sticky;top:8px;z-index:10;margin-bottom:16px;border:1px solid var(--fin-border)">
      <div style="display:flex;gap:24px;align-items:center;padding:16px 20px;flex-wrap:wrap">
        <div>
          <div style="font-size:11px;color:var(--fin-ink-3);text-transform:uppercase">Saldo extracto</div>
          <div style="font-size:20px;font-weight:700;font-family:monospace">${fmt(statementBalance)}</div>
        </div>
        <div>
          <div style="font-size:11px;color:var(--fin-ink-3);text-transform:uppercase">Suma marcadas</div>
          <div id="r-cleared-sum" style="font-size:20px;font-weight:700;font-family:monospace">${fmt(clearedSum)}</div>
        </div>
        <div style="margin-left:auto">
          <div style="font-size:11px;color:var(--fin-ink-3);text-transform:uppercase">Diferencia</div>
          <div id="r-diff" style="font-size:24px;font-weight:800;font-family:monospace;color:${Math.abs(diff) < 1 ? 'var(--fin-success)' : 'var(--fin-danger)'}">${fmt(diff)}</div>
        </div>
        <button id="r-finish" class="btn btn-primary" ${Math.abs(diff) >= 1 ? 'disabled' : ''}>
          Finalizar reconciliación
        </button>
      </div>
      <div id="r-diff-hint" style="padding:0 20px 12px;font-size:12px;color:var(--fin-ink-3);${Math.abs(diff) < 1 ? 'display:none' : ''}">
        Marca las transacciones confirmadas hasta que la diferencia sea $0
      </div>
    </div>

    <div class="card">
      <div style="padding:12px 16px;border-bottom:1px solid var(--fin-border);display:flex;gap:12px;align-items:center">
        <span style="font-size:13px;color:var(--fin-ink-3)">${transactions.length} transacciones</span>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;margin-left:auto">
          <input type="checkbox" id="r-filter-uncleared"> Solo no confirmadas
        </label>
      </div>
      <div style="overflow-x:auto">
        <table class="data-table" id="r-table">
          <thead>
            <tr>
              <th style="width:40px"></th>
              <th>Fecha</th>
              <th>Descripción</th>
              <th style="text-align:right">Monto</th>
            </tr>
          </thead>
          <tbody>
            ${transactions.map(tx => renderTxRow(tx)).join('')}
          </tbody>
        </table>
      </div>
    </div>

    <div id="r-finish-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:100;display:none;align-items:center;justify-content:center">
      <div class="card" style="max-width:400px;width:90%;padding:24px">
        <h3 style="margin:0 0 12px">¿Finalizar reconciliación?</h3>
        <p style="color:var(--fin-ink-3);font-size:14px;margin:0 0 16px">
          Diferencia: <strong style="color:var(--fin-success)">${fmt(diff)}</strong><br>
          Se guardará el historial de esta reconciliación.
        </p>
        <div class="form-group">
          <label class="form-label">Notas (opcional)</label>
          <input id="r-notes" type="text" class="form-control" placeholder="Ej: Extracto Mayo 2026">
        </div>
        <div style="display:flex;gap:8px;margin-top:16px">
          <button id="r-cancel-finish" class="btn btn-ghost" style="flex:1">Cancelar</button>
          <button id="r-confirm-finish" class="btn btn-primary" style="flex:1">Confirmar</button>
        </div>
      </div>
    </div>
  `;
}

function renderTxRow(tx) {
  const fmt = v => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(v);
  const isPos = (tx.amount ?? 0) >= 0;
  return `
    <tr data-tx-id="${tx.id}" data-cleared="${tx.cleared ? '1' : '0'}" class="${tx.cleared ? 'row-cleared' : ''}">
      <td style="text-align:center">
        <input type="checkbox" class="r-tx-check" data-id="${tx.id}" data-amount="${tx.amount ?? 0}" ${tx.cleared ? 'checked' : ''} style="width:18px;height:18px;cursor:pointer">
      </td>
      <td style="white-space:nowrap;font-size:13px">${tx.date ?? ''}</td>
      <td style="font-size:13px">${sanitize(tx.payee_name ?? tx.memo ?? 'Sin descripción')}</td>
      <td style="text-align:right;font-family:monospace;font-size:13px;color:${isPos ? 'var(--fin-success)' : 'var(--fin-danger)'}">
        ${isPos ? '+' : ''}${fmt(tx.amount ?? 0)}
      </td>
    </tr>
  `;
}

function bindStep2(container, account, statementDate, statementBalance, transactions) {
  const fmt = v => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(v);

  let clearedSet = new Set(transactions.filter(tx => tx.cleared).map(tx => tx.id));
  let amountMap  = Object.fromEntries(transactions.map(tx => [tx.id, tx.amount ?? 0]));

  function recomputePanel() {
    const sum = [...clearedSet].reduce((s, id) => s + (amountMap[id] ?? 0), 0);
    const diff = statementBalance - sum;
    const ok = Math.abs(diff) < 1;
    container.querySelector('#r-cleared-sum').textContent = fmt(sum);
    const diffEl = container.querySelector('#r-diff');
    diffEl.textContent = fmt(diff);
    diffEl.style.color = ok ? 'var(--fin-success)' : 'var(--fin-danger)';
    container.querySelector('#r-finish').disabled = !ok;
    const hint = container.querySelector('#r-diff-hint');
    if (hint) hint.style.display = ok ? 'none' : '';
  }

  container.querySelector('#r-back').addEventListener('click', () => mount(container));

  container.querySelector('#r-filter-uncleared').addEventListener('change', e => {
    const showAll = !e.target.checked;
    container.querySelectorAll('#r-table tbody tr').forEach(row => {
      const cleared = row.dataset.cleared === '1';
      row.style.display = showAll || !cleared ? '' : 'none';
    });
  });

  container.addEventListener('change', async e => {
    const cb = e.target.closest('.r-tx-check');
    if (!cb) return;
    const id = parseInt(cb.dataset.id);
    const checked = cb.checked;
    const row = cb.closest('tr');

    cb.disabled = true;
    try {
      await api.reconciliation.markCleared({ transaction_ids: [id], cleared: checked });
      if (checked) {
        clearedSet.add(id);
        row.dataset.cleared = '1';
        row.classList.add('row-cleared');
      } else {
        clearedSet.delete(id);
        row.dataset.cleared = '0';
        row.classList.remove('row-cleared');
      }
      recomputePanel();
    } catch (err) {
      cb.checked = !checked;
      toast(`Error: ${err.message}`, 'error');
    } finally {
      cb.disabled = false;
    }
  });

  const modal = container.querySelector('#r-finish-modal');

  container.querySelector('#r-finish').addEventListener('click', () => {
    modal.style.display = 'flex';
  });

  container.querySelector('#r-cancel-finish').addEventListener('click', () => {
    modal.style.display = 'none';
  });

  container.querySelector('#r-confirm-finish').addEventListener('click', async () => {
    const notes = container.querySelector('#r-notes').value.trim() || null;
    try {
      await api.reconciliation.createSession({
        account_id: account.id,
        statement_date: statementDate,
        statement_balance: statementBalance,
        notes,
        create_adjustment_entry: false,
      });
      modal.style.display = 'none';
      toast('Reconciliación guardada', 'success');
      await mount(container);
    } catch (err) {
      toast(`Error al guardar: ${err.message}`, 'error');
    }
  });
}
