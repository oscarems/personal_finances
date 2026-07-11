import * as api from '../api/client.js';
import { sanitize } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Reglas de Comercios';

let _categories = [];
let _rules = [];
let _ignoreRules = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    [_categories, _rules, _ignoreRules] = await Promise.all([
      api.categories.list(),
      api.merchantRules.list(),
      api.merchantIgnoreRules.list(),
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

    <div class="page-header" style="margin-top:32px">
      <div class="page-header-text">
        <h2 style="margin:0">Comercios Ignorados</h2>
        <p>Correos cuyo comercio coincida con alguno de estos nombres se omiten automáticamente al procesar, sin crear transacción.</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-secondary" id="btnNewIgnore">+ Ignorar Comercio</button>
      </div>
    </div>

    ${ignoreSection()}
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

  container.querySelector('#btnNewIgnore')?.addEventListener('click', () => openIgnoreModal(container));
  container.querySelectorAll('[data-delete-ignore]').forEach(btn => {
    btn.addEventListener('click', () => deleteIgnoreRule(parseInt(btn.dataset.deleteIgnore), container));
  });
}

// ---------------------------------------------------------------------------
// Ignore rules
// ---------------------------------------------------------------------------

function ignoreSection() {
  if (_ignoreRules.length === 0) {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">🚫</div>
        <h3>Sin comercios ignorados</h3>
        <p>Agrega un comercio para que sus correos se omitan automáticamente al importar.</p>
      </div>`;
  }
  return `
    <div class="card" style="overflow:hidden">
      <table>
        <thead>
          <tr>
            <th>Comercio</th>
            <th style="width:80px"></th>
          </tr>
        </thead>
        <tbody>
          ${_ignoreRules.map(r => `
            <tr>
              <td style="font-family:var(--font-mono);font-size:0.82rem;font-weight:500">${sanitize(r.merchant_name)}</td>
              <td style="text-align:right">
                <button class="btn btn-ghost btn-xs" data-delete-ignore="${r.id}" title="Eliminar" style="color:var(--fin-danger)">✕</button>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function openIgnoreModal(container) {
  openModal({
    title: 'Ignorar Comercio',
    content: `
      <div class="form-group">
        <label class="form-label">Nombre del comercio <span style="color:var(--fin-danger)">*</span></label>
        <input type="text" id="ig-name" class="form-input"
          placeholder="Ej: RAPPI, NETFLIX, UBER EATS"
          style="font-family:var(--font-mono);text-transform:uppercase">
        <div style="font-size:0.72rem;color:var(--text-soft);margin-top:4px">
          Se compara contra el asunto y cuerpo del correo (sin importar mayúsculas).
        </div>
      </div>`,
    submitLabel: 'Ignorar',
    onSubmit: async (body) => {
      const name = body.querySelector('#ig-name').value.trim();
      if (!name) throw new Error('El nombre del comercio es obligatorio');
      await api.merchantIgnoreRules.create({ merchant_name: name });
      toast.success('Comercio ignorado');
      _ignoreRules = await api.merchantIgnoreRules.list();
      render(container);
    },
  });

  setTimeout(() => {
    const input = document.querySelector('#ig-name');
    if (input) input.addEventListener('input', () => {
      const pos = input.selectionStart;
      input.value = input.value.toUpperCase();
      input.setSelectionRange(pos, pos);
    });
  }, 50);
}

async function deleteIgnoreRule(id, container) {
  if (!confirm('¿Dejar de ignorar este comercio?')) return;
  try {
    await api.merchantIgnoreRules.delete(id);
    toast.success('Regla eliminada');
    _ignoreRules = await api.merchantIgnoreRules.list();
    render(container);
  } catch (err) {
    toast.error(err.message);
  }
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
        <a href="#letter-${l}" style="font-size:0.78rem;padding:3px 8px;border-radius:4px;background:var(--fin-surface-2);color:var(--fin-ink-3);text-decoration:none;border:1px solid var(--fin-border)">${l}</a>
      `).join('')}
    </div>
    <div class="card" style="overflow:hidden">
      <table>
        <thead>
          <tr>
            <th>Condición</th>
            <th>Categoría</th>
            <th>Prioridad</th>
            <th style="width:80px"></th>
          </tr>
        </thead>
        <tbody>
          ${letters.map(l => `
            <tr id="letter-${l}">
              <td colspan="4" style="padding:6px 16px;font-size:0.7rem;font-weight:700;color:var(--fin-ink-3);letter-spacing:0.06em;background:var(--fin-surface-2);border-bottom:1px solid var(--fin-border)">${l}</td>
            </tr>
            ${grouped[l].map(r => ruleRow(r)).join('')}
          `).join('')}
        </tbody>
      </table>
    </div>
    <div style="font-size:0.75rem;color:var(--fin-ink-3);margin-top:10px;text-align:right">
      ${_rules.length} regla${_rules.length !== 1 ? 's' : ''} configurada${_rules.length !== 1 ? 's' : ''}
    </div>`;
}

const FIELD_LABELS = { payee: 'Comercio', memo: 'Descripción' };
const OPERATOR_LABELS = {
  contains: 'Contiene',
  equals: 'Es exactamente',
  starts_with: 'Empieza con',
  regex: 'Regex',
};

function ruleRow(r) {
  return `
    <tr>
      <td>
        <div class="text-soft text-xs">${sanitize(FIELD_LABELS[r.field] || r.field)} · ${sanitize(OPERATOR_LABELS[r.operator] || r.operator)}</div>
        <div class="font-mono text-sm">${sanitize(r.merchant_name)}</div>
      </td>
      <td class="text-sm">
        <span class="text-muted text-xs">${sanitize(r.category_group || '')}</span>
        ${sanitize(r.category_name || '—')}
      </td>
      <td class="font-mono text-sm">${sanitize(String(r.priority ?? 0))}</td>
      <td class="text-right nowrap">
        <button class="btn btn-ghost btn-xs" data-edit="${r.id}" title="Editar">✏</button>
        <button class="btn btn-ghost btn-xs text-danger" data-delete="${r.id}" title="Eliminar">✕</button>
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
  const field = r.field || 'payee';
  const operator = r.operator || 'contains';
  const catGrps = {};
  _categories.forEach(c => { const k = c.category_group_name || ''; if (!catGrps[k]) catGrps[k] = []; catGrps[k].push(c); });
  const categoryOptions = Object.entries(catGrps).map(([k, cs]) =>
    `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${c.id == r.category_id ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`
  ).join('');

  return `
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Campo objetivo <span class="text-danger">*</span></label>
        <select id="mr-field" class="form-input">
          <option value="payee" ${field === 'payee' ? 'selected' : ''}>Comercio</option>
          <option value="memo" ${field === 'memo' ? 'selected' : ''}>Descripción</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Operador <span class="text-danger">*</span></label>
        <select id="mr-operator" class="form-input">
          <option value="contains" ${operator === 'contains' ? 'selected' : ''}>Contiene</option>
          <option value="equals" ${operator === 'equals' ? 'selected' : ''}>Es exactamente</option>
          <option value="starts_with" ${operator === 'starts_with' ? 'selected' : ''}>Empieza con</option>
          <option value="regex" ${operator === 'regex' ? 'selected' : ''}>Regex</option>
        </select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Valor <span class="text-danger">*</span></label>
      <input type="text" id="mr-name" value="${sanitize(r.merchant_name || '')}" class="form-input font-mono"
        placeholder="Ej: RAPPI, NETFLIX, UBER EATS">
      <div class="text-soft text-xs mt-1" id="mr-name-hint">
        Se guarda en mayúsculas tal como aparece en los correos bancarios.
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Categoría destino <span class="text-danger">*</span></label>
      <select id="mr-category" class="form-input">
        <option value="">— seleccionar categoría —</option>
        ${categoryOptions}
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Prioridad</label>
      <input type="number" id="mr-priority" value="${sanitize(String(r.priority ?? 0))}" class="form-input" step="1">
      <div class="text-soft text-xs mt-1">
        Cuando varias reglas coinciden con la misma transacción, gana la de mayor prioridad.
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Previsualización</label>
      <div id="mr-preview"></div>
    </div>`;
}

function previewEmptyHtml() {
  return `<div class="alert alert-info">Escribe un valor para ver qué transacciones coincidirían.</div>`;
}

function previewErrorHtml(msg) {
  return `<div class="alert alert-danger">${sanitize(msg)}</div>`;
}

function previewNoMatchesHtml() {
  return `<div class="alert alert-warning">Ninguna transacción reciente coincide con esta condición.</div>`;
}

function previewTableHtml(matches, total) {
  const shown = matches.slice(0, 10);
  return `
    <div class="card" style="overflow:hidden">
      <table class="fin-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Comercio / descripción</th>
            <th class="amount">Monto</th>
            <th>Categoría actual</th>
          </tr>
        </thead>
        <tbody>
          ${shown.map(tx => `
            <tr>
              <td class="text-sm">${sanitize(tx.date || '—')}</td>
              <td class="text-sm">${sanitize(tx.payee_name || tx.memo || '—')}</td>
              <td class="amount ${Number(tx.amount) < 0 ? 'text-danger' : 'text-success'}">${sanitize(String(tx.amount))} ${sanitize(tx.currency || '')}</td>
              <td class="text-sm">${sanitize(tx.category_name || '—')}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>
    ${total > shown.length ? `<div class="text-soft text-xs mt-2">y ${total - shown.length} más</div>` : ''}`;
}

function openRuleModal(rule, container) {
  const isEdit = !!rule;
  const modal = openModal({
    title: isEdit ? 'Editar Regla de Comercio' : 'Nueva Regla de Comercio',
    content: ruleFormHtml(rule),
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    size: 'lg',
    onSubmit: async (body) => {
      const field = body.querySelector('#mr-field').value;
      const operator = body.querySelector('#mr-operator').value;
      const name = body.querySelector('#mr-name').value.trim();
      const categoryId = parseInt(body.querySelector('#mr-category').value);
      const priority = parseInt(body.querySelector('#mr-priority').value) || 0;

      if (!name) throw new Error('El valor de la regla es obligatorio');
      if (!categoryId) throw new Error('Selecciona una categoría');
      if (regexIsInvalid) throw new Error('La expresión regular no es válida');

      const payload = { merchant_name: name, category_id: categoryId, field, operator, priority };

      if (isEdit) {
        await api.merchantRules.update(rule.id, payload);
        toast.success('Regla actualizada');
      } else {
        await api.merchantRules.create(payload);
        toast.success('Regla creada');
      }

      _rules = await api.merchantRules.list();
      render(container);
    },
  });

  const body = modal.body;
  const fieldSel = body.querySelector('#mr-field');
  const operatorSel = body.querySelector('#mr-operator');
  const nameInput = body.querySelector('#mr-name');
  const nameHint = body.querySelector('#mr-name-hint');
  const previewEl = body.querySelector('#mr-preview');
  const submitBtn = body.closest('.modal')?.querySelector('[data-submit]');

  let regexIsInvalid = false;
  let debounceTimer = null;

  function applyUppercase() {
    if (operatorSel.value === 'regex') return;
    const pos = nameInput.selectionStart;
    nameInput.value = nameInput.value.toUpperCase();
    nameInput.setSelectionRange(pos, pos);
  }

  function setSubmitDisabled(disabled) {
    if (submitBtn) submitBtn.disabled = disabled;
  }

  async function runPreview() {
    const value = nameInput.value.trim();
    const field = fieldSel.value;
    const operator = operatorSel.value;

    nameHint.textContent = operator === 'regex'
      ? 'Se evalúa como expresión regular (respeta mayúsculas y minúsculas de tu patrón).'
      : 'Se guarda en mayúsculas tal como aparece en los correos bancarios.';

    if (!value) {
      regexIsInvalid = false;
      previewEl.innerHTML = previewEmptyHtml();
      setSubmitDisabled(false);
      return;
    }

    try {
      const result = await api.merchantRules.preview({ field, operator, value });
      regexIsInvalid = false;
      setSubmitDisabled(false);
      if (!result.matches || result.matches.length === 0) {
        previewEl.innerHTML = previewNoMatchesHtml();
      } else {
        previewEl.innerHTML = previewTableHtml(result.matches, result.total);
      }
    } catch (err) {
      regexIsInvalid = operator === 'regex';
      previewEl.innerHTML = previewErrorHtml(err.message);
      setSubmitDisabled(regexIsInvalid);
    }
  }

  function scheduleRunPreview() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runPreview, 300);
  }

  nameInput.addEventListener('input', () => {
    applyUppercase();
    scheduleRunPreview();
  });
  fieldSel.addEventListener('change', scheduleRunPreview);
  operatorSel.addEventListener('change', scheduleRunPreview);

  runPreview();
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
