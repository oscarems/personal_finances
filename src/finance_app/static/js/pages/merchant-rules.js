import * as api from '../api/client.js';
import { sanitize } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Reglas de Comercios';

let _categories = [];
let _rules = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    [_categories, _rules] = await Promise.all([
      api.categories.list(),
      api.merchantRules.list(),
    ]);
    render(container);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container) {
  const grouped = groupByFirstLetter(_rules);

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Reglas de Comercios</h1>
        <p>Mapea nombres de comercios (tal como aparecen en los correos) a categorías. Ollama los usa para categorizar con mayor precisión.</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-primary" id="btnNew">+ Nueva Regla</button>
      </div>
    </div>

    ${_rules.length === 0 ? emptyState() : tableSection(grouped)}
  `;

  container.querySelector('#btnNew')?.addEventListener('click', () => openRuleModal(null, container));
  container.querySelector('#btnNewEmpty')?.addEventListener('click', () => openRuleModal(null, container));

  container.querySelectorAll('[data-edit]').forEach(btn => {
    const rule = _rules.find(r => r.id === parseInt(btn.dataset.edit));
    btn.addEventListener('click', () => openRuleModal(rule, container));
  });

  container.querySelectorAll('[data-delete]').forEach(btn => {
    btn.addEventListener('click', () => deleteRule(parseInt(btn.dataset.delete), container));
  });
}

function emptyState() {
  return `
    <div class="empty-state">
      <div class="empty-state-icon">🏪</div>
      <h3>Sin reglas de comercios</h3>
      <p>Agrega comercios y su categoría para que Ollama los identifique automáticamente al importar correos.</p>
      <button class="btn btn-primary" id="btnNewEmpty">+ Nueva Regla</button>
    </div>`;
}

function tableSection(grouped) {
  const letters = Object.keys(grouped).sort();
  return `
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
      ${letters.map(l => `
        <a href="#letter-${l}" style="font-size:0.78rem;padding:3px 8px;border-radius:4px;background:var(--bg-elevated);color:var(--text-soft);text-decoration:none;border:1px solid var(--border-color)">${l}</a>
      `).join('')}
    </div>
    <div class="card" style="overflow:hidden">
      <table>
        <thead>
          <tr>
            <th>Comercio</th>
            <th>Categoría</th>
            <th style="width:80px"></th>
          </tr>
        </thead>
        <tbody>
          ${letters.map(l => `
            <tr id="letter-${l}">
              <td colspan="3" style="padding:6px 16px;font-size:0.7rem;font-weight:700;color:var(--text-soft);letter-spacing:0.06em;background:var(--bg-elevated);border-bottom:1px solid var(--border-color)">${l}</td>
            </tr>
            ${grouped[l].map(r => ruleRow(r)).join('')}
          `).join('')}
        </tbody>
      </table>
    </div>
    <div style="font-size:0.75rem;color:var(--text-soft);margin-top:10px;text-align:right">
      ${_rules.length} regla${_rules.length !== 1 ? 's' : ''} configurada${_rules.length !== 1 ? 's' : ''}
    </div>`;
}

function ruleRow(r) {
  return `
    <tr>
      <td style="font-family:var(--font-mono);font-size:0.82rem;font-weight:500">${sanitize(r.merchant_name)}</td>
      <td style="font-size:0.82rem">
        <span style="color:var(--text-soft);font-size:0.7rem;margin-right:4px">${sanitize(r.category_group || '')}</span>
        ${sanitize(r.category_name || '—')}
      </td>
      <td style="text-align:right;white-space:nowrap">
        <button class="btn btn-ghost btn-xs" data-edit="${r.id}" title="Editar">✏</button>
        <button class="btn btn-ghost btn-xs" data-delete="${r.id}" title="Eliminar" style="color:var(--color-danger)">✕</button>
      </td>
    </tr>`;
}

function groupByFirstLetter(rules) {
  return rules.reduce((acc, r) => {
    const letter = (r.merchant_name?.[0] || '#').toUpperCase();
    const key = /[A-Z]/.test(letter) ? letter : '#';
    (acc[key] = acc[key] || []).push(r);
    return acc;
  }, {});
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

function ruleFormHtml(rule) {
  const r = rule ?? {};
  const catGrps = {};
  _categories.forEach(c => { const k = c.category_group_name || ''; if (!catGrps[k]) catGrps[k] = []; catGrps[k].push(c); });
  const categoryOptions = Object.entries(catGrps).map(([k, cs]) =>
    `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${c.id == r.category_id ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`
  ).join('');

  return `
    <div class="form-group">
      <label class="form-label">Nombre del comercio <span style="color:var(--color-danger)">*</span></label>
      <input type="text" id="mr-name" value="${sanitize(r.merchant_name || '')}" class="form-input"
        placeholder="Ej: RAPPI, NETFLIX, UBER EATS"
        style="font-family:var(--font-mono);text-transform:uppercase">
      <div style="font-size:0.72rem;color:var(--text-soft);margin-top:4px">
        Se guarda en mayúsculas tal como aparece en los correos bancarios.
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Categoría <span style="color:var(--color-danger)">*</span></label>
      <select id="mr-category" class="form-input">
        <option value="">— seleccionar categoría —</option>
        ${categoryOptions}
      </select>
    </div>`;
}

function openRuleModal(rule, container) {
  const isEdit = !!rule;
  openModal({
    title: isEdit ? 'Editar Regla de Comercio' : 'Nueva Regla de Comercio',
    content: ruleFormHtml(rule),
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const name = body.querySelector('#mr-name').value.trim();
      const categoryId = parseInt(body.querySelector('#mr-category').value);

      if (!name) throw new Error('El nombre del comercio es obligatorio');
      if (!categoryId) throw new Error('Selecciona una categoría');

      if (isEdit) {
        await api.merchantRules.update(rule.id, { merchant_name: name, category_id: categoryId });
        toast.success('Regla actualizada');
      } else {
        await api.merchantRules.create({ merchant_name: name, category_id: categoryId });
        toast.success('Regla creada');
      }

      _rules = await api.merchantRules.list();
      render(container);
    },
  });

  // Auto-uppercase as user types
  setTimeout(() => {
    const input = document.querySelector('#mr-name');
    if (input) input.addEventListener('input', () => {
      const pos = input.selectionStart;
      input.value = input.value.toUpperCase();
      input.setSelectionRange(pos, pos);
    });
  }, 50);
}

async function deleteRule(id, container) {
  if (!confirm('¿Eliminar esta regla de comercio?')) return;
  try {
    await api.merchantRules.delete(id);
    toast.success('Regla eliminada');
    _rules = await api.merchantRules.list();
    render(container);
  } catch (err) {
    toast.error(err.message);
  }
}
