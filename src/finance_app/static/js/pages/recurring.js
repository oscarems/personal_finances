import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, todayISO } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';
import { emptyState } from '../components/emptyState.js';
import { loadingState, showError } from '../components/pageState.js';

export const title = 'Transacciones Recurrentes';

let _accounts = [], _categories = [], _currencies = [], _list = [], _upcoming = [];

export async function mount(container) {
  container.innerHTML = loadingState();
  try {
    [_accounts, _categories, _currencies, _list] = await Promise.all([
      api.accounts.list(), api.categories.list(), api.currencies.list(), api.recurring.list(),
    ]);
    const upcomingResp = await api.recurring.upcoming({ days: 21 }).catch(() => ({ items: [] }));
    _upcoming = upcomingResp.items ?? [];
    render(container, _list);
  } catch (err) {
    showError(container, {
      title: 'Recurrentes',
      message: err.message || 'Error al cargar las transacciones recurrentes',
      onRetry: () => mount(container),
    });
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

    ${upcomingSection()}

    ${active.length === 0 ? `
      ${emptyState({
        icon: '♻️',
        title: 'Sin transacciones recurrentes',
        hint: 'Configura pagos automáticos como nómina, servicios o suscripciones.',
        actionLabel: '+ Nueva',
        actionId: 'btnNewEmpty',
      })}` : `
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
        <summary style="cursor:pointer;font-size:0.875rem;color:var(--fin-ink-2);margin-bottom:12px">
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
  container.querySelector('#btnNewEmpty')?.addEventListener('click', () => openForm(null, container));
  container.querySelector('#btnGenerate')?.addEventListener('click', async () => {
    try {
      await api.recurring.generate();
      toast.success('Transacciones pendientes generadas');
      await mount(container);
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

  bindUpcomingActions(container);
}

function upcomingSection() {
  if (!_upcoming.length) {
    return `
      <div class="card mb-4">
        <div class="card-header"><span class="card-title">Próximas a aprobar</span></div>
        <div class="card-body">${emptyState({ icon: '📅', title: 'Nada pendiente', hint: 'No hay ocurrencias en los próximos 21 días.' })}</div>
      </div>`;
  }

  // One row per recurring (next occurrence only) to keep inbox clean
  const seen = new Set();
  const rows = [];
  for (const item of _upcoming) {
    if (seen.has(item.recurring_id)) continue;
    seen.add(item.recurring_id);
    rows.push(item);
  }

  return `
    <div class="card mb-4">
      <div class="card-header"><span class="card-title">Próximas a aprobar (${rows.length})</span></div>
      <div class="card-body" style="padding:0">
        <table class="fin-table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Descripción</th>
              <th class="td-right">Monto</th>
              <th>Estado</th>
              <th style="width:220px"></th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(item => `
              <tr>
                <td class="td-soft">${fmtDate(item.occurrence_date)}</td>
                <td>
                  <div style="font-weight:500">${sanitize(item.payee_name || item.description || '—')}</div>
                  <div class="text-soft text-sm">${sanitize(item.account_name || '')} · ${sanitize(item.category_name || '')}</div>
                </td>
                <td class="td-right amount ${item.transaction_type === 'income' ? 'text-success' : 'text-danger'}">
                  ${item.transaction_type === 'income' ? '+' : '-'}${fmtCurrency(Math.abs(item.amount ?? 0), item.currency?.code ?? 'COP')}
                </td>
                <td>${item.snoozed ? `<span class="badge badge-warning">Pospuesta</span>` : `<span class="badge badge-primary">Pendiente</span>`}</td>
                <td class="td-right">
                  <button class="btn btn-primary btn-xs" data-approve-rec="${item.recurring_id}" data-occ="${item.occurrence_date}">Aprobar</button>
                  <button class="btn btn-ghost btn-xs" data-skip-rec="${item.recurring_id}" data-occ="${item.occurrence_date}">Saltar</button>
                  <button class="btn btn-ghost btn-xs" data-snooze-rec="${item.recurring_id}">Posponer</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>`;
}

function bindUpcomingActions(container) {
  container.querySelectorAll('[data-approve-rec]').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api.recurring.approve(parseInt(btn.dataset.approveRec), { occurrence_date: btn.dataset.occ });
        toast.success('Ocurrencia aprobada y generada');
        await mount(container);
      } catch (err) { toast.error(err.message); }
    });
  });
  container.querySelectorAll('[data-skip-rec]').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api.recurring.skip(parseInt(btn.dataset.skipRec), { occurrence_date: btn.dataset.occ });
        toast.success('Ocurrencia saltada');
        await mount(container);
      } catch (err) { toast.error(err.message); }
    });
  });
  container.querySelectorAll('[data-snooze-rec]').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api.recurring.snooze(parseInt(btn.dataset.snoozeRec), { days: 7 });
        toast.success('Pospuesta 7 días');
        await mount(container);
      } catch (err) { toast.error(err.message); }
    });
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
        <button class="btn btn-ghost btn-xs" style="color:var(--fin-danger)" data-delete-rec="${r.id}">✕</button>
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
