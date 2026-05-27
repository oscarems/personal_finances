import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, todayISO } from '../utils.js';
import { toast } from '../components/toast.js';
import { openModal } from '../components/modal.js';

export const title = 'Importar Gmail';

let _categories = [];
let _accounts = [];
let _emails = [];
let _selectedMessageId = null;
let _ollamaModels = [];
let _defaultModel = '';
let _bulkMode = false;
let _selectedIds = new Set();

const defaultSince = () => {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().split('T')[0];
};

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    [_categories, _accounts] = await Promise.all([
      api.categories.list(),
      api.accounts.list(),
    ]);
    try {
      _ollamaModels = await api.gmailImport.models();
      _defaultModel = _ollamaModels[0] || '';
    } catch {
      _ollamaModels = [];
      _defaultModel = '';
    }
    renderShell(container);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function renderShell(container) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Importar desde Gmail</h1>
        <p>Analiza correos bancarios con Ollama y crea transacciones.</p>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start">
      <div>
        <div class="card" style="margin-bottom:16px">
          <div class="card-body" style="padding:16px">
            <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
              <div class="form-group" style="margin:0;flex:1;min-width:140px">
                <label class="form-label">Desde</label>
                <input type="date" id="gi-since" value="${defaultSince()}">
              </div>
              <div class="form-group" style="margin:0;width:90px">
                <label class="form-label">Máx.</label>
                <input type="number" id="gi-max" value="50" min="1" max="200">
              </div>
              <div class="form-group" style="margin:0;flex:1;min-width:160px">
                <label class="form-label">Modelo Ollama</label>
                ${_ollamaModels.length
                  ? `<select id="gi-model" class="form-input">
                      ${_ollamaModels.map(m => `<option value="${sanitize(m)}">${sanitize(m)}</option>`).join('')}
                     </select>`
                  : `<input type="text" id="gi-model" class="form-input" placeholder="gemma4:e4b" value="${sanitize(_defaultModel)}">`
                }
              </div>
              <button class="btn btn-primary" id="btnSync">Sincronizar</button>
              <button class="btn btn-secondary" id="btnBulkToggle" title="Modo lote: selecciona varios correos y procésalos a la vez">Lote</button>
            </div>
          </div>
        </div>

        <div id="gi-bulk-toolbar" style="display:none;margin-bottom:8px;padding:10px 14px;background:var(--bg-elevated);border-radius:8px;border:1px solid var(--color-primary,#3b82f6);align-items:center;gap:10px;flex-wrap:wrap">
          <span id="gi-bulk-count" style="font-size:0.8rem;color:var(--text-soft);min-width:100px">0 seleccionados</span>
          <button class="btn btn-secondary btn-sm" id="btnSelectAll" style="font-size:0.75rem;padding:4px 10px">Todos los pendientes</button>
          <button class="btn btn-secondary btn-sm" id="btnSelectNone" style="font-size:0.75rem;padding:4px 10px">Ninguno</button>
          <button class="btn btn-primary btn-sm" id="btnBulkProcess" style="font-size:0.75rem;padding:4px 14px;margin-left:auto" disabled>
            Procesar (0)
          </button>
        </div>

        <div id="gi-email-list">
          <div class="empty-state">
            <div class="empty-state-icon">📧</div>
            <h3>Sin correos cargados</h3>
            <p>Presiona Sincronizar para traer correos de Gmail.</p>
          </div>
        </div>
      </div>

      <div id="gi-right-panel">
        ${rightPanelEmpty()}
      </div>
    </div>
  `;

  container.querySelector('#btnSync').addEventListener('click', () => syncEmails(container));
  container.querySelector('#btnBulkToggle').addEventListener('click', () => toggleBulkMode(container));
}

// ---------------------------------------------------------------------------
// Sync
// ---------------------------------------------------------------------------

async function syncEmails(container) {
  const since = container.querySelector('#gi-since').value;
  const max = container.querySelector('#gi-max').value;
  const listEl = container.querySelector('#gi-email-list');

  const btn = container.querySelector('#btnSync');
  btn.disabled = true;
  btn.textContent = 'Sincronizando...';
  listEl.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';

  try {
    _emails = await api.gmailImport.emails({ since_date: since, max_emails: max });
    _selectedIds.clear();
    renderEmailList(container);
  } catch (err) {
    listEl.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sincronizar';
  }
}

// ---------------------------------------------------------------------------
// Email list
// ---------------------------------------------------------------------------

function renderEmailList(container) {
  const listEl = container.querySelector('#gi-email-list');

  if (!_emails.length) {
    listEl.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📭</div>
        <h3>Sin correos encontrados</h3>
        <p>Prueba cambiando la fecha de inicio.</p>
      </div>`;
    updateBulkToolbar(container);
    return;
  }

  const pending = _emails.filter(e => !e.processed && !e.skipped);
  listEl.innerHTML = `
    <div style="font-size:0.75rem;color:var(--text-soft);margin-bottom:8px;padding:0 4px">
      ${_emails.length} correo${_emails.length !== 1 ? 's' : ''} ·
      <span style="color:var(--color-warning)">${pending.length} pendiente${pending.length !== 1 ? 's' : ''}</span>
    </div>
    <div class="card" style="overflow:hidden">
      ${_emails.map(e => emailRow(e)).join('')}
    </div>
  `;

  listEl.querySelectorAll('.btn-process').forEach(btn => {
    btn.addEventListener('click', () => startProcess(container, btn.dataset.mid));
  });
  listEl.querySelectorAll('.btn-skip').forEach(btn => {
    btn.addEventListener('click', () => skipEmail(container, btn.dataset.mid));
  });
  listEl.querySelectorAll('.btn-preview').forEach(btn => {
    btn.addEventListener('click', () => previewEmail(btn.dataset.mid));
  });
  listEl.querySelectorAll('.btn-reprocess').forEach(btn => {
    btn.addEventListener('click', () => reprocessEmail(container, btn.dataset.mid));
  });
  listEl.querySelectorAll('.gi-bulk-check').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) _selectedIds.add(cb.dataset.mid);
      else _selectedIds.delete(cb.dataset.mid);
      updateBulkToolbar(container);
    });
  });

  // Wire bulk toolbar buttons
  const btnSelectAll = container.querySelector('#btnSelectAll');
  const btnSelectNone = container.querySelector('#btnSelectNone');
  const btnBulkProcess = container.querySelector('#btnBulkProcess');

  btnSelectAll?.addEventListener('click', () => {
    _emails.filter(e => !e.processed && !e.skipped).forEach(e => _selectedIds.add(e.message_id));
    listEl.querySelectorAll('.gi-bulk-check[data-pending="true"]').forEach(cb => { cb.checked = true; });
    updateBulkToolbar(container);
  });

  btnSelectNone?.addEventListener('click', () => {
    _selectedIds.clear();
    listEl.querySelectorAll('.gi-bulk-check').forEach(cb => { cb.checked = false; });
    updateBulkToolbar(container);
  });

  btnBulkProcess?.addEventListener('click', () => startBulkProcess(container));

  updateBulkToolbar(container);
}

function emailRow(email) {
  const isPending = !email.processed && !email.skipped;
  const statusBadge = email.processed
    ? '<span class="badge badge-success" style="font-size:0.65rem">Procesado</span>'
    : email.skipped
    ? '<span class="badge badge-neutral" style="font-size:0.65rem">Omitido</span>'
    : '<span class="badge badge-warning" style="font-size:0.65rem">Pendiente</span>';

  const mid = sanitize(email.message_id);

  const bulkCheckbox = _bulkMode
    ? `<input type="checkbox" class="gi-bulk-check" data-mid="${mid}" data-pending="${isPending}"
         ${_selectedIds.has(email.message_id) ? 'checked' : ''}
         style="margin-right:8px;cursor:pointer;flex-shrink:0;accent-color:var(--color-primary,#3b82f6)">`
    : '';

  const previewBtn = `<button class="btn btn-ghost btn-sm btn-preview" data-mid="${mid}" title="Ver cuerpo del correo" style="font-size:0.7rem;padding:2px 7px;opacity:0.7">👁</button>`;

  const reprocessBtn = !isPending
    ? `<button class="btn btn-ghost btn-sm btn-reprocess" data-mid="${mid}"
         title="Reprocesar con las reglas actuales (elimina la transacción anterior)"
         style="font-size:0.7rem;padding:2px 8px;color:var(--color-warning,#f59e0b)">↺ Reprocesar</button>`
    : '';

  const actions = isPending
    ? `<div style="display:flex;gap:6px;margin-top:6px">
        <button class="btn btn-primary btn-sm btn-process" data-mid="${mid}" style="font-size:0.75rem;padding:4px 10px">Procesar</button>
        <button class="btn btn-secondary btn-sm btn-skip" data-mid="${mid}" style="font-size:0.75rem;padding:4px 10px">Omitir</button>
        ${previewBtn}
       </div>`
    : `<div style="display:flex;gap:6px;margin-top:4px">${reprocessBtn}${previewBtn}</div>`;

  return `
    <div style="padding:12px 16px;border-bottom:1px solid var(--border-color);${_selectedMessageId === email.message_id ? 'background:var(--bg-elevated);' : ''}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div style="display:flex;align-items:flex-start;min-width:0;flex:1">
          ${bulkCheckbox}
          <div style="min-width:0;flex:1">
            <div style="font-size:0.8125rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              ${sanitize(email.subject || '(sin asunto)')}
            </div>
            <div style="font-size:0.72rem;color:var(--text-soft);margin-top:2px">
              ${fmtDate(email.received_at)} · ${sanitize((email.sender || '').replace(/<.*>/, '').trim())}
            </div>
            <div style="font-size:0.7rem;color:var(--text-muted,var(--text-soft));margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">
              ${sanitize((email.preview || '').substring(0, 120))}
            </div>
          </div>
        </div>
        <div style="flex-shrink:0">${statusBadge}</div>
      </div>
      ${actions}
    </div>`;
}

// ---------------------------------------------------------------------------
// Preview
// ---------------------------------------------------------------------------

async function previewEmail(messageId) {
  const email = _emails.find(e => e.message_id === messageId);
  const modal = openModal({
    title: email?.subject || 'Vista previa del correo',
    size: 'lg',
    content: `<div class="page-loading"><div class="spinner"></div></div>`,
  });

  try {
    const data = await api.gmailImport.preview(messageId);
    modal.body.innerHTML = `
      <div style="margin-bottom:12px;font-size:0.8rem;color:var(--text-soft);display:flex;flex-direction:column;gap:4px">
        <div><strong>De:</strong> ${sanitize(data.sender || '')}</div>
        <div><strong>Fecha:</strong> ${fmtDate(data.received_at)}</div>
      </div>
      <hr style="border-color:var(--border-color);margin:0 0 12px">
      <pre style="white-space:pre-wrap;word-break:break-word;font-size:0.78rem;line-height:1.6;max-height:420px;overflow-y:auto;background:var(--bg-base,#0f172a);padding:12px;border-radius:6px;border:1px solid var(--border-color)">${sanitize(data.body_text)}</pre>`;
  } catch (err) {
    modal.body.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Bulk mode helpers
// ---------------------------------------------------------------------------

function toggleBulkMode(container) {
  _bulkMode = !_bulkMode;
  _selectedIds.clear();

  const btn = container.querySelector('#btnBulkToggle');
  if (btn) {
    btn.textContent = _bulkMode ? 'Cancelar lote' : 'Lote';
    btn.className = _bulkMode ? 'btn btn-warning' : 'btn btn-secondary';
  }

  const toolbar = container.querySelector('#gi-bulk-toolbar');
  if (toolbar) toolbar.style.display = _bulkMode ? 'flex' : 'none';

  if (_emails.length) renderEmailList(container);
}

function updateBulkToolbar(container) {
  const count = _selectedIds.size;
  const alreadyProcessed = [..._selectedIds].filter(id => {
    const e = _emails.find(em => em.message_id === id);
    return e && (e.processed || e.skipped);
  }).length;

  const countEl = container.querySelector('#gi-bulk-count');
  const processBtn = container.querySelector('#btnBulkProcess');

  if (countEl) {
    countEl.textContent = alreadyProcessed > 0
      ? `${count} seleccionado${count !== 1 ? 's' : ''} (${alreadyProcessed} ya procesado${alreadyProcessed !== 1 ? 's' : ''})`
      : `${count} seleccionado${count !== 1 ? 's' : ''}`;
  }
  if (processBtn) {
    processBtn.textContent = alreadyProcessed > 0 ? `Reprocesar (${count})` : `Procesar (${count})`;
    processBtn.disabled = count === 0;
    processBtn.className = alreadyProcessed > 0
      ? 'btn btn-warning btn-sm'
      : 'btn btn-primary btn-sm';
    processBtn.style.cssText = 'font-size:0.75rem;padding:4px 14px;margin-left:auto';
  }
}

// ---------------------------------------------------------------------------
// Individual reprocess
// ---------------------------------------------------------------------------

async function reprocessEmail(container, messageId) {
  const email = _emails.find(e => e.message_id === messageId);
  const label = email?.processed ? 'Este correo ya fue procesado. Se eliminará la transacción asociada y se volverá a analizar con las reglas actuales. ¿Continuar?' : '¿Reprocesar este correo?';
  if (!confirm(label)) return;

  try {
    await api.gmailImport.reset(messageId);
    const em = _emails.find(e => e.message_id === messageId);
    if (em) { em.processed = false; em.skipped = false; em.transaction_id = null; }
    renderEmailList(container);
    startProcess(container, messageId);
  } catch (err) {
    toast.error(`Error al restablecer: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Bulk processing
// ---------------------------------------------------------------------------

async function startBulkProcess(container) {
  const ids = [..._selectedIds];
  if (!ids.length) return;

  const toReset = ids.filter(id => {
    const e = _emails.find(em => em.message_id === id);
    return e && (e.processed || e.skipped);
  });

  if (toReset.length > 0) {
    const msg = `${toReset.length} correo${toReset.length !== 1 ? 's' : ''} ya procesado${toReset.length !== 1 ? 's' : ''} serán restablecidos y sus transacciones eliminadas. ¿Continuar?`;
    if (!confirm(msg)) return;

    try {
      await api.gmailImport.bulkReset({ message_ids: toReset });
      toReset.forEach(id => {
        const e = _emails.find(em => em.message_id === id);
        if (e) { e.processed = false; e.skipped = false; e.transaction_id = null; }
      });
      renderEmailList(container);
    } catch (err) {
      toast.error(`Error al restablecer correos: ${err.message}`);
      return;
    }
  }

  const modelEl = container.querySelector('#gi-model');
  const selectedModel = modelEl?.value?.trim() || _defaultModel || undefined;

  const progressModal = openModal({
    title: `Procesando correos con Ollama`,
    size: 'sm',
    content: buildProgressHTML(0, ids.length, ''),
  });

  const processedItems = [];

  for (let i = 0; i < ids.length; i++) {
    const messageId = ids[i];
    const email = _emails.find(e => e.message_id === messageId);
    progressModal.body.innerHTML = buildProgressHTML(i, ids.length, email?.subject || messageId);

    try {
      const result = await api.gmailImport.process(messageId, selectedModel);
      processedItems.push({ messageId, email, result, included: true, error: null });
    } catch (err) {
      processedItems.push({ messageId, email, result: {}, included: false, error: err.message });
    }
  }

  progressModal.close();
  showBulkReviewModal(container, processedItems);
}

function buildProgressHTML(current, total, subject) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  return `
    <div style="text-align:center;padding:8px 0">
      <div class="spinner" style="margin:0 auto 16px"></div>
      <div style="font-size:0.9rem;font-weight:500;margin-bottom:6px">
        Procesando ${current + 1} de ${total}
      </div>
      <div style="font-size:0.78rem;color:var(--text-soft);margin-bottom:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:280px;margin-left:auto;margin-right:auto">
        ${sanitize(subject)}
      </div>
      <div style="background:var(--border-color);border-radius:999px;height:6px;overflow:hidden">
        <div style="background:var(--color-primary,#3b82f6);width:${pct}%;height:100%;transition:width 0.3s"></div>
      </div>
      <div style="font-size:0.72rem;color:var(--text-soft);margin-top:8px">${pct}%</div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Bulk review modal
// ---------------------------------------------------------------------------

function showBulkReviewModal(container, items) {
  const validCount = items.filter(i => i.included).length;

  const modal = openModal({
    title: `Revisar ${items.length} correos procesados`,
    size: 'xl',
    content: buildReviewHTML(items),
    submitLabel: `Confirmar seleccionados`,
    keepOpen: true,
    onSubmit: async (body) => {
      await submitBulkReview(container, body, items, modal);
    },
  });

  // Wire "incluir" checkboxes to update counter
  modal.body.querySelectorAll('.br-include').forEach(cb => {
    cb.addEventListener('change', () => {
      const idx = parseInt(cb.dataset.idx);
      items[idx].included = cb.checked;
      const countEl = modal.body.closest('.modal')?.querySelector('[data-submit]');
      const selected = items.filter(i => i.included).length;
      if (countEl) countEl.textContent = `Confirmar seleccionados (${selected})`;
    });
  });

  // Update button label with initial count
  const submitBtn = modal.body.closest('.modal')?.querySelector('[data-submit]');
  if (submitBtn) submitBtn.textContent = `Confirmar seleccionados (${validCount})`;
}

function buildReviewHTML(items) {
  const accountOptions = (selectedId) =>
    _accounts.map(a =>
      `<option value="${a.id}" ${Number(a.id) === Number(selectedId) ? 'selected' : ''}>${sanitize(a.name)}</option>`
    ).join('');

  const categoryOptions = (selectedId) => {
    const g = {};
    _categories.forEach(c => { const k = c.category_group_name || ''; if (!g[k]) g[k] = []; g[k].push(c); });
    return `<option value="">— sin categoría —</option>` +
      Object.entries(g).map(([k, cs]) =>
        `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${Number(c.id) === Number(selectedId) ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`
      ).join('');
  };

  const rows = items.map((item, idx) => {
    const r = item.result;
    const hasError = !!item.error;
    const fecha = r.fecha || todayISO();
    const monto = r.monto ?? '';
    const moneda = r.moneda || 'COP';
    const borderColor = hasError
      ? 'var(--color-danger,#ef4444)'
      : (!r.cuenta_id || !r.monto)
      ? 'var(--color-warning,#f59e0b)'
      : 'var(--border-color)';

    return `
      <div style="border:1px solid ${borderColor};border-radius:8px;padding:14px;margin-bottom:10px;background:var(--bg-card,var(--bg-elevated))">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
          <input type="checkbox" class="br-include" data-idx="${idx}" ${item.included ? 'checked' : ''} style="cursor:pointer;accent-color:var(--color-primary,#3b82f6)">
          <div style="flex:1;min-width:0">
            <div style="font-size:0.82rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              ${sanitize(item.email?.subject || item.messageId)}
            </div>
            <div style="font-size:0.7rem;color:var(--text-soft)">
              ${fmtDate(item.email?.received_at)}
              ${hasError ? `· <span style="color:var(--color-danger,#ef4444)">Error: ${sanitize(item.error)}</span>` : ''}
            </div>
          </div>
        </div>
        ${hasError ? '' : `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div class="form-group" style="margin:0">
            <label class="form-label" style="font-size:0.72rem">Fecha</label>
            <input type="date" class="form-input br-fecha" data-idx="${idx}" value="${fecha}" style="font-size:0.78rem;padding:5px 8px">
          </div>
          <div style="display:grid;grid-template-columns:1fr 80px;gap:6px">
            <div class="form-group" style="margin:0">
              <label class="form-label" style="font-size:0.72rem">Monto</label>
              <input type="number" class="form-input br-monto" data-idx="${idx}" value="${monto}" min="0" step="0.01" style="font-size:0.78rem;padding:5px 8px" placeholder="0.00">
            </div>
            <div class="form-group" style="margin:0">
              <label class="form-label" style="font-size:0.72rem">Moneda</label>
              <select class="form-input br-moneda" data-idx="${idx}" style="font-size:0.78rem;padding:5px 6px">
                <option value="COP" ${moneda === 'COP' ? 'selected' : ''}>COP</option>
                <option value="USD" ${moneda === 'USD' ? 'selected' : ''}>USD</option>
              </select>
            </div>
          </div>
          <div class="form-group" style="margin:0">
            <label class="form-label" style="font-size:0.72rem">Cuenta</label>
            <select class="form-input br-cuenta" data-idx="${idx}" style="font-size:0.78rem;padding:5px 8px">
              <option value="">— seleccionar —</option>${accountOptions(r.cuenta_id)}
            </select>
          </div>
          <div class="form-group" style="margin:0">
            <label class="form-label" style="font-size:0.72rem">Categoría</label>
            <select class="form-input br-categoria" data-idx="${idx}" style="font-size:0.78rem;padding:5px 8px">
              ${categoryOptions(r.categoria_id)}
            </select>
          </div>
          <div class="form-group" style="margin:0;grid-column:1/-1">
            <label class="form-label" style="font-size:0.72rem">Comentario</label>
            <input type="text" class="form-input br-comentario" data-idx="${idx}" value="${sanitize(r.comentario || '')}" style="font-size:0.78rem;padding:5px 8px" placeholder="Descripción del gasto">
          </div>
        </div>`}
      </div>`;
  });

  return `
    <div style="font-size:0.78rem;color:var(--text-soft);margin-bottom:14px">
      Revisa y ajusta los campos antes de confirmar. Desmarca los correos que no quieras importar.
    </div>
    <div style="max-height:520px;overflow-y:auto;padding-right:4px">
      ${rows.join('')}
    </div>`;
}

async function submitBulkReview(container, body, items, modal) {
  const confirmItems = [];

  items.forEach((item, idx) => {
    if (!item.included || item.error) return;

    const fecha = body.querySelector(`.br-fecha[data-idx="${idx}"]`)?.value;
    const monto = parseFloat(body.querySelector(`.br-monto[data-idx="${idx}"]`)?.value || '0');
    const moneda = body.querySelector(`.br-moneda[data-idx="${idx}"]`)?.value || 'COP';
    const cuentaId = body.querySelector(`.br-cuenta[data-idx="${idx}"]`)?.value;
    const categoriaId = body.querySelector(`.br-categoria[data-idx="${idx}"]`)?.value;
    const comentario = body.querySelector(`.br-comentario[data-idx="${idx}"]`)?.value || '';

    if (!fecha || !monto || monto <= 0 || !cuentaId) return;

    confirmItems.push({
      message_id: item.messageId,
      fecha,
      monto,
      moneda,
      cuenta_id: parseInt(cuentaId),
      categoria_id: categoriaId ? parseInt(categoriaId) : null,
      comentario: comentario || null,
    });
  });

  if (!confirmItems.length) {
    throw new Error('No hay transacciones válidas para confirmar. Verifica que cada correo seleccionado tenga monto y cuenta.');
  }

  const { results } = await api.gmailImport.bulkConfirm({ items: confirmItems });

  const created = results.filter(r => r.status === 'created').length;
  const errors = results.filter(r => r.status === 'error').length;

  // Update local state
  results.forEach(r => {
    const email = _emails.find(e => e.message_id === r.message_id);
    if (email && r.status === 'created') email.processed = true;
  });

  _selectedIds.clear();
  if (_bulkMode) toggleBulkMode(container);
  renderEmailList(container);
  modal.close();

  if (errors > 0) {
    toast.warning(`${created} transacciones creadas, ${errors} con error`);
  } else {
    toast.success(`${created} transacción${created !== 1 ? 'es' : ''} creada${created !== 1 ? 's' : ''} correctamente`);
  }
}

// ---------------------------------------------------------------------------
// Individual processing (unchanged behavior)
// ---------------------------------------------------------------------------

async function skipEmail(container, messageId) {
  try {
    await api.gmailImport.skip(messageId);
    const email = _emails.find(e => e.message_id === messageId);
    if (email) email.skipped = true;
    renderEmailList(container);
    if (_selectedMessageId === messageId) {
      container.querySelector('#gi-right-panel').innerHTML = rightPanelEmpty();
      _selectedMessageId = null;
    }
    toast.info('Correo omitido');
  } catch (err) {
    toast.error(err.message);
  }
}

async function startProcess(container, messageId) {
  _selectedMessageId = messageId;
  renderEmailList(container);

  const modelEl = container.querySelector('#gi-model');
  const selectedModel = modelEl?.value?.trim() || _defaultModel || undefined;

  const rightPanel = container.querySelector('#gi-right-panel');
  rightPanel.innerHTML = `
    <div class="card">
      <div class="card-body" style="padding:32px;text-align:center">
        <div class="spinner" style="margin:0 auto 16px"></div>
        <p style="color:var(--text-soft)">Analizando con Ollama${selectedModel ? ` (${sanitize(selectedModel)})` : ''}… esto puede tardar 10-20 segundos.</p>
      </div>
    </div>`;

  try {
    const result = await api.gmailImport.process(messageId, selectedModel);
    renderConfirmForm(container, messageId, result);
  } catch (err) {
    renderManualForm(container, messageId, `Ollama no disponible: ${err.message}`);
  }
}

function renderConfirmForm(container, messageId, ollama) {
  const rightPanel = container.querySelector('#gi-right-panel');
  const email = _emails.find(e => e.message_id === messageId);

  const promptSection = ollama._prompt
    ? `<details style="margin-top:16px">
        <summary style="font-size:0.75rem;color:var(--text-soft);cursor:pointer;user-select:none;padding:6px 8px;background:var(--bg-elevated);border-radius:6px;border:1px solid var(--border-color)">
          Ver prompt enviado al LLM
        </summary>
        <pre style="margin-top:6px;white-space:pre-wrap;word-break:break-word;font-size:0.72rem;line-height:1.55;max-height:340px;overflow-y:auto;background:var(--bg-base,#0f172a);padding:12px;border-radius:6px;border:1px solid var(--border-color);color:var(--text-soft)">${sanitize(ollama._prompt)}</pre>
      </details>`
    : '';

  rightPanel.innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title" style="font-size:0.875rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          ${sanitize(email?.subject || messageId)}
        </span>
      </div>
      <div class="card-body" style="padding:20px">
        ${formFields(ollama)}
        ${promptSection}
        <div style="display:flex;gap:10px;margin-top:20px">
          <button class="btn btn-primary" id="btnConfirm">Confirmar</button>
          <button class="btn btn-secondary" id="btnManual">Ingresar manual</button>
          <button class="btn btn-ghost" id="btnCancelRight" style="margin-left:auto">Cancelar</button>
        </div>
      </div>
    </div>`;

  rightPanel.querySelector('#btnConfirm').addEventListener('click', () =>
    submitConfirm(container, messageId)
  );
  rightPanel.querySelector('#btnManual').addEventListener('click', () =>
    renderManualForm(container, messageId)
  );
  rightPanel.querySelector('#btnCancelRight').addEventListener('click', () => {
    _selectedMessageId = null;
    renderEmailList(container);
    rightPanel.innerHTML = rightPanelEmpty();
  });
}

function renderManualForm(container, messageId, warningMsg = null) {
  const rightPanel = container.querySelector('#gi-right-panel');

  rightPanel.innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title" style="font-size:0.875rem">Ingreso manual</span>
      </div>
      <div class="card-body" style="padding:20px">
        ${warningMsg ? `<div class="alert alert-warning" style="margin-bottom:16px;font-size:0.8rem">${sanitize(warningMsg)}</div>` : ''}
        ${formFields({})}
        <div style="display:flex;gap:10px;margin-top:20px">
          <button class="btn btn-primary" id="btnConfirm">Confirmar</button>
          <button class="btn btn-ghost" id="btnCancelRight" style="margin-left:auto">Cancelar</button>
        </div>
      </div>
    </div>`;

  rightPanel.querySelector('#btnConfirm').addEventListener('click', () =>
    submitConfirm(container, messageId)
  );
  rightPanel.querySelector('#btnCancelRight').addEventListener('click', () => {
    _selectedMessageId = null;
    renderEmailList(container);
    rightPanel.innerHTML = rightPanelEmpty();
  });
}

function formFields(ollama) {
  const fecha = ollama.fecha || todayISO();
  const monto = ollama.monto ?? '';
  const moneda = ollama.moneda || 'COP';
  const cuentaId = ollama.cuenta_id ?? '';
  const categoriaId = ollama.categoria_id ?? '';
  const comentario = ollama.comentario || '';

  const accountOptions = _accounts
    .map(a => `<option value="${a.id}" ${Number(a.id) === Number(cuentaId) ? 'selected' : ''}>${sanitize(a.name)}</option>`)
    .join('');

  const catGroups = {};
  _categories.forEach(c => { const k = c.category_group_name || ''; if (!catGroups[k]) catGroups[k] = []; catGroups[k].push(c); });
  const categoryOptions =
    `<option value="">— sin categoría —</option>` +
    Object.entries(catGroups).map(([k, cs]) =>
      `<optgroup label="${sanitize(k)}">${cs.map(c => `<option value="${c.id}" ${Number(c.id) === Number(categoriaId) ? 'selected' : ''}>${sanitize(c.name)}</option>`).join('')}</optgroup>`
    ).join('');

  return `
    <div class="form-group">
      <label class="form-label">Fecha</label>
      <input type="date" id="fi-fecha" value="${fecha}" class="form-input">
    </div>
    <div style="display:grid;grid-template-columns:1fr 120px;gap:12px">
      <div class="form-group">
        <label class="form-label">Monto</label>
        <input type="number" id="fi-monto" value="${monto}" min="0" step="0.01" class="form-input" placeholder="0.00">
      </div>
      <div class="form-group">
        <label class="form-label">Moneda</label>
        <select id="fi-moneda" class="form-input">
          <option value="COP" ${moneda === 'COP' ? 'selected' : ''}>COP</option>
          <option value="USD" ${moneda === 'USD' ? 'selected' : ''}>USD</option>
        </select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Cuenta</label>
      <select id="fi-cuenta" class="form-input">
        <option value="">— seleccionar cuenta —</option>${accountOptions}
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Categoría</label>
      <select id="fi-categoria" class="form-input">
        ${categoryOptions}
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Comentario</label>
      <input type="text" id="fi-comentario" value="${sanitize(comentario)}" class="form-input" placeholder="Descripción del gasto">
    </div>
    <div style="margin-top:4px;display:flex;align-items:center;gap:8px;padding:8px 10px;background:var(--bg-elevated);border-radius:6px;border:1px solid var(--border-color)">
      <input type="checkbox" id="fi-save-rule" style="cursor:pointer;accent-color:var(--color-primary,#3b82f6)">
      <label for="fi-save-rule" style="font-size:0.78rem;color:var(--text-soft);cursor:pointer;margin:0">
        Guardar como regla de comercio para futuras importaciones
      </label>
    </div>`;
}

async function submitConfirm(container, messageId) {
  const rightPanel = container.querySelector('#gi-right-panel');

  const fecha = rightPanel.querySelector('#fi-fecha')?.value;
  const monto = parseFloat(rightPanel.querySelector('#fi-monto')?.value || '0');
  const moneda = rightPanel.querySelector('#fi-moneda')?.value;
  const cuentaId = rightPanel.querySelector('#fi-cuenta')?.value;
  const categoriaId = rightPanel.querySelector('#fi-categoria')?.value;
  const comentario = rightPanel.querySelector('#fi-comentario')?.value;

  if (!fecha) { toast.error('Ingresa la fecha'); return; }
  if (!monto || monto <= 0) { toast.error('Ingresa un monto válido'); return; }
  if (!cuentaId) { toast.error('Selecciona una cuenta'); return; }

  const saveRule = rightPanel.querySelector('#fi-save-rule')?.checked;

  const btn = rightPanel.querySelector('#btnConfirm');
  btn.disabled = true;
  btn.textContent = 'Guardando...';

  try {
    await api.gmailImport.confirm({
      message_id: messageId,
      fecha,
      monto,
      moneda,
      cuenta_id: parseInt(cuentaId),
      categoria_id: categoriaId ? parseInt(categoriaId) : null,
      comentario: comentario || null,
    });

    if (saveRule && comentario && categoriaId) {
      try {
        await api.merchantRules.create({
          merchant_name: comentario.trim(),
          category_id: parseInt(categoriaId),
        });
      } catch {
        // Silently ignore duplicate rule errors
      }
    }

    const email = _emails.find(e => e.message_id === messageId);
    if (email) email.processed = true;
    _selectedMessageId = null;
    renderEmailList(container);
    rightPanel.innerHTML = rightPanelEmpty();
    toast.success('Transacción creada correctamente');
  } catch (err) {
    toast.error(err.message);
    btn.disabled = false;
    btn.textContent = 'Confirmar';
  }
}

function rightPanelEmpty() {
  return `
    <div class="card">
      <div class="card-body" style="padding:32px;text-align:center;color:var(--text-soft)">
        <div style="font-size:2rem;margin-bottom:12px">✉️</div>
        <p>Selecciona un correo y presiona <strong>Procesar</strong> para analizarlo con Ollama.</p>
      </div>
    </div>`;
}
