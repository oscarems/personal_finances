import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, todayISO } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Transacciones Recurrentes';

let _accounts = [], _categories = [], _currencies = [], _list = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    [_accounts, _categories, _currencies, _list] = await Promise.all([
      api.accounts.list(), api.categories.list(), api.currencies.list(), api.recurring.list(),
    ]);
    render(container, _list);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container, list) {
  const active   = list.filter(r => r.is_active !== false);
  const inactive = list.filter(r => r.is_active === false);

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Recurrentes</h1>
        <p>${active.length} activa${active.length !== 1 ? 's' : ''}</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-secondary btn-sm" id="btnGenerate">⟳ Generar pendientes</button>
        <button class="btn btn-primary btn-sm" id="btnNew">+ Nueva</button>
      </div>
    </div>

    ${active.length === 0 ? `
      <div class="empty-state">
        <div class="empty-state-icon">♻️</div>
        <h3>Sin transacciones recurrentes</h3>
        <p>Configura pagos automáticos como nómina, servicios, o suscripciones.</p>
      </div>` : `
      <div class="table-wrap" style="margin-bottom:24px">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Tipo</th>
              <th>Cuenta</th>
              <th>Categoría</th>
              <th>Frecuencia</th>
              <th class="td-right">Monto</th>
              <th>Próxima</th>
              <th style="width:80px"></th>
            </tr>
          </thead>
          <tbody>
            ${active.map(r => recurringRow(r)).join('')}
          </tbody>
        </table>
      </div>`}

    ${inactive.length ? `
      <details style="margin-top:16px">
        <summary style="cursor:pointer;font-size:0.875rem;color:var(--text-secondary);margin-bottom:12px">
          Inactivas (${inactive.length})
        </summary>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Nombre</th><th class="td-right">Monto</th><th>Frecuencia</th><th>Próxima</th><th style="width:80px"></th></tr></thead>
            <tbody>${inactive.map(r => recurringRow(r)).join('')}</tbody>
          </table>
        </div>
      </details>` : ''}
  `;

  container.querySelector('#btnNew').addEventListener('click', () => openForm(null, container));
  container.querySelector('#btnGenerate')?.addEventListener('click', async () => {
    try {
      await api.recurring.generate();
      toast.success('Transacciones pendientes generadas');
    } catch (err) { toast.error(err.message); }
  });

  container.querySelectorAll('[data-edit-rec]').forEach(btn => {
    const rec = list.find(r => r.id === parseInt(btn.dataset.editRec));
    btn.addEventListener('click', () => openForm(rec, container));
  });
  container.querySelectorAll('[data-delete-rec]').forEach(btn => {
    const id = parseInt(btn.dataset.deleteRec);
    btn.addEventListener('click', () => deleteRec(id, container));
  });
}

function recurringRow(r) {
  const freqMap = { daily: 'Diaria', weekly: 'Semanal', biweekly: 'Quincenal', monthly: 'Mensual', yearly: 'Anual' };
  const typeClass = r.transaction_type === 'income' ? 'positive' : 'negative';
  const sign = r.transaction_type === 'income' ? '+' : '-';

  return `
    <tr>
      <td style="font-size:0.8125rem;font-weight:500">${sanitize(r.name ?? r.description ?? '—')}</td>
      <td><span class="badge ${r.transaction_type === 'income' ? 'badge-success' : 'badge-danger'}" style="font-size:0.65rem">
        ${r.transaction_type === 'income' ? 'Ingreso' : 'Gasto'}
      </span></td>
      <td class="td-soft" style="font-size:0.8rem">${sanitize(r.account_name ?? '—')}</td>
      <td class="td-soft" style="font-size:0.8rem">${sanitize(r.category_name ?? '—')}</td>
      <td style="font-size:0.8rem">${freqMap[r.frequency] ?? r.frequency ?? '—'}</td>
      <td class="td-right td-mono amount ${typeClass}" style="font-size:0.8125rem">
        ${sign}${fmtCurrency(r.amount ?? 0, r.currency?.code ?? 'COP')}
        <span style="font-size:0.65rem;opacity:0.6;font-family:inherit;margin-left:2px">${r.currency?.code ?? 'COP'}</span>
      </td>
      <td class="td-soft" style="font-size:0.8rem">${r.next_occurrence_date ? fmtDate(r.next_occurrence_date) : '—'}</td>
      <td style="text-align:right">
        <button class="btn btn-ghost btn-xs" data-edit-rec="${r.id}">✏</button>
        <button class="btn btn-ghost btn-xs" style="color:var(--color-danger)" data-delete-rec="${r.id}">✕</button>
      </td>
    </tr>`;
}

function formHtml(r) {
  const rec = r ?? {};
  const freqs = ['daily', 'weekly', 'biweekly', 'monthly', 'yearly'];
  const freqLabels = { daily: 'Diaria', weekly: 'Semanal', biweekly: 'Quincenal', monthly: 'Mensual', yearly: 'Anual' };

  return `
    <div class="form-group" style="margin-bottom:16px">
      <label class="form-label required">Nombre</label>
      <input type="text" id="rf-name" value="${sanitize(rec.name ?? rec.description ?? '')}" placeholder="Ej: Nómina, Netflix">
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Tipo</label>
        <select id="rf-type">
          <option value="expense" ${rec.transaction_type === 'expense' ? 'selected' : ''}>Gasto</option>
          <option value="income"  ${rec.transaction_type === 'income'  ? 'selected' : ''}>Ingreso</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label required">Frecuencia</label>
        <select id="rf-freq">
          ${freqs.map(f => `<option value="${f}" ${rec.frequency === f ? 'selected' : ''}>${freqLabels[f]}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Monto</label>
        <input type="number" id="rf-amount" value="${rec.amount ?? ''}" step="0.01" min="0">
      </div>
      <div class="form-group">
        <label class="form-label">Moneda</label>
        <select id="rf-currency">
          ${_currencies.map(c => `<option value="${c.id}" ${rec.currency?.id == c.id || (!rec.currency && c.code === 'COP') ? 'selected' : ''}>${c.code}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Cuenta</label>
        <select id="rf-account">
          <option value="">— seleccionar —</option>
          ${_accounts.map(a => `<option value="${a.id}" ${rec.account_id == a.id ? 'selected' : ''}>${sanitize(a.name)}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label required">Categoría</label>
        <select id="rf-category">
          <option value="">— seleccionar —</option>
          ${(() => { const g = {}; _categories.forEach(c => { const k = c.category_group_name || ''; if (!g[k]) g[k] = []; g[k].push(c); }); return Object.entries(g).map(([k,cs]) => `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${rec.category_id == c.id ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`).join(''); })()}
        </select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label required">Próxima fecha</label>
      <input type="date" id="rf-next" value="${rec.next_occurrence_date ?? rec.start_date ?? todayISO()}">
    </div>
  `;
}

function openForm(rec, container) {
  const isEdit = !!rec;
  openModal({
    title: isEdit ? `Editar: ${rec.name ?? rec.description}` : 'Nueva Recurrente',
    content: formHtml(rec),
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const data = {
        description:      body.querySelector('#rf-name').value.trim(),
        transaction_type: body.querySelector('#rf-type').value,
        frequency:        body.querySelector('#rf-freq').value,
        amount:           parseFloat(body.querySelector('#rf-amount').value),
        currency_id:      parseInt(body.querySelector('#rf-currency').value) || null,
        account_id:       parseInt(body.querySelector('#rf-account').value) || null,
        category_id:      parseInt(body.querySelector('#rf-category').value) || null,
        start_date:       body.querySelector('#rf-next').value || null,
      };
      if (!data.description || !data.amount || !data.account_id) throw new Error('Nombre, monto y cuenta son obligatorios');
      if (!data.category_id) throw new Error('La categoría es obligatoria');
      if (isEdit) { await api.recurring.update(rec.id, data); toast.success('Actualizado'); }
      else        { await api.recurring.create(data);         toast.success('Creado'); }
      _list = await api.recurring.list();
      render(container, _list);
    },
  });
}

async function deleteRec(id, container) {
  if (!confirm('¿Eliminar esta recurrente?')) return;
  try {
    await api.recurring.delete(id);
    toast.success('Eliminada');
    _list = await api.recurring.list();
    render(container, _list);
  } catch (err) { toast.error(err.message); }
}
