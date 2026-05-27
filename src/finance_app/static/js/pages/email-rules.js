import * as api from '../api/client.js';
import { sanitize } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Reglas de Email';

let _accounts = [], _categories = [], _rules = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    [_accounts, _categories, _rules] = await Promise.all([
      api.accounts.list(), api.categories.list(), api.emailSenderRules.list(),
    ]);
    render(container, _rules);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container, rules) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Reglas de Email</h1>
        <p>Asigna automáticamente cuentas y categorías al importar correos de Gmail.</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-primary" id="btnNew">+ Nueva Regla</button>
      </div>
    </div>

    ${rules.length === 0 ? `
      <div class="empty-state">
        <div class="empty-state-icon">📧</div>
        <h3>Sin reglas configuradas</h3>
        <p>Las reglas permiten asignar categorías y cuentas automáticamente a transacciones de email según el remitente.</p>
        <button class="btn btn-primary" id="btnNewEmpty">+ Nueva Regla</button>
      </div>` : `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Remitente / Patrón</th>
              <th>Cuenta</th>
              <th>Categoría</th>
              <th>Prioridad</th>
              <th style="width:80px"></th>
            </tr>
          </thead>
          <tbody>
            ${rules.map(r => ruleRow(r)).join('')}
          </tbody>
        </table>
      </div>`}
  `;

  container.querySelector('#btnNew')?.addEventListener('click', () => openRuleModal(null, container));
  container.querySelector('#btnNewEmpty')?.addEventListener('click', () => openRuleModal(null, container));
  container.querySelectorAll('[data-edit-rule]').forEach(btn => {
    const rule = rules.find(r => r.id === parseInt(btn.dataset.editRule));
    btn.addEventListener('click', () => openRuleModal(rule, container));
  });
  container.querySelectorAll('[data-delete-rule]').forEach(btn => {
    const id = parseInt(btn.dataset.deleteRule);
    btn.addEventListener('click', () => deleteRule(id, container));
  });
}

function ruleRow(r) {
  return `
    <tr>
      <td style="font-size:0.8125rem">
        <div style="font-weight:500;font-family:var(--font-mono);font-size:0.8rem">${sanitize(r.sender_pattern ?? r.email_pattern ?? r.sender ?? '—')}</div>
        ${r.description ? `<div style="font-size:0.72rem;color:var(--text-soft)">${sanitize(r.description)}</div>` : ''}
      </td>
      <td class="td-soft" style="font-size:0.8rem">${sanitize(r.account_name ?? '—')}</td>
      <td class="td-soft" style="font-size:0.8rem">${sanitize(r.category_name ?? '—')}</td>
      <td style="font-size:0.8rem">${r.priority ?? '—'}</td>
      <td style="text-align:right">
        <button class="btn btn-ghost btn-xs" data-edit-rule="${r.id}">✏</button>
        <button class="btn btn-ghost btn-xs" style="color:var(--color-danger)" data-delete-rule="${r.id}">✕</button>
      </td>
    </tr>`;
}

function ruleFormHtml(r) {
  const rule = r ?? {};
  return `
    <div class="form-group" style="margin-bottom:16px">
      <label class="form-label required">Patrón de remitente</label>
      <input type="text" id="rf-pattern" value="${sanitize(rule.sender_pattern ?? rule.email_pattern ?? rule.sender ?? '')}"
        placeholder="Ej: noreply@davivienda.com o *@davivienda.com">
      <div style="font-size:0.72rem;color:var(--text-soft);margin-top:4px">Usa * como comodín. Ej: *@banco.com</div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Cuenta destino</label>
        <select id="rf-account">
          <option value="">— sin asignar —</option>
          ${_accounts.map(a => `<option value="${a.id}" ${rule.account_id == a.id ? 'selected' : ''}>${sanitize(a.name)}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Categoría destino</label>
        <select id="rf-category">
          <option value="">— sin asignar —</option>
          ${(() => { const g = {}; _categories.forEach(c => { const k = c.category_group_name || ''; if (!g[k]) g[k] = []; g[k].push(c); }); return Object.entries(g).map(([k,cs]) => `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${rule.category_id == c.id ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`).join(''); })()}
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Prioridad (número menor = mayor prioridad)</label>
        <input type="number" id="rf-priority" value="${rule.priority ?? 10}" min="1" max="999">
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Descripción (opcional)</label>
      <input type="text" id="rf-desc" value="${sanitize(rule.description ?? '')}" placeholder="Ej: Extractos Davivienda">
    </div>
  `;
}

function openRuleModal(rule, container) {
  const isEdit = !!rule;
  openModal({
    title: isEdit ? 'Editar Regla' : 'Nueva Regla',
    content: ruleFormHtml(rule),
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const data = {
        sender_pattern: body.querySelector('#rf-pattern').value.trim(),
        account_id:     parseInt(body.querySelector('#rf-account').value) || null,
        category_id:    parseInt(body.querySelector('#rf-category').value) || null,
        priority:       parseInt(body.querySelector('#rf-priority').value) || 10,
        description:    body.querySelector('#rf-desc').value.trim() || null,
      };
      if (!data.sender_pattern) throw new Error('El patrón de remitente es obligatorio');
      if (isEdit) { await api.emailSenderRules.update(rule.id, data); toast.success('Regla actualizada'); }
      else        { await api.emailSenderRules.create(data);          toast.success('Regla creada'); }
      _rules = await api.emailSenderRules.list();
      render(container, _rules);
    },
  });
}

async function deleteRule(id, container) {
  if (!confirm('¿Eliminar esta regla?')) return;
  try {
    await api.emailSenderRules.delete(id);
    toast.success('Regla eliminada');
    _rules = await api.emailSenderRules.list();
    render(container, _rules);
  } catch (err) { toast.error(err.message); }
}
