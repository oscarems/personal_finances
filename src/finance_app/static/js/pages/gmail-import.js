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

// ---------------------------------------------------------------------------
// Page-scoped styles (injected once)
// ---------------------------------------------------------------------------

const _CSS = `
.gi-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
.gi-filter-bar { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
.gi-filter-bar .form-group { margin: 0; }
.gi-filter-bar .fg-date  { flex: 1; min-width: 140px; }
.gi-filter-bar .fg-max   { width: 90px; }
.gi-filter-bar .fg-model { flex: 1; min-width: 160px; }
.gi-bulk-toolbar {
  display: none; margin-bottom: 8px; padding: 10px 14px;
  background: var(--fin-surface-2); border-radius: var(--fin-radius);
  border: 1px solid var(--fin-accent); align-items: center;
  gap: 10px; flex-wrap: wrap;
}
.gi-bulk-toolbar.is-active { display: flex; }
.gi-bulk-count { font-size: 0.8rem; min-width: 100px; }
.gi-list-meta  { font-size: 0.75rem; margin-bottom: 8px; padding: 0 4px; }
.gi-email-row  {
  padding: 12px 16px; border-bottom: 1px solid var(--fin-border);
  transition: background 0.15s;
}
.gi-email-row.is-selected { background: var(--fin-surface-2); }
.gi-email-subject {
  font-size: 0.8125rem; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gi-email-meta  { font-size: 0.72rem; margin-top: 2px; }
.gi-email-preview {
  font-size: 0.7rem; margin-top: 4px;
  display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}
.gi-email-actions { display: flex; gap: 6px; margin-top: 6px; }
.gi-email-actions.is-done { margin-top: 4px; }
.gi-bulk-check { margin-right: 8px; cursor: pointer; flex-shrink: 0; accent-color: var(--fin-accent); }
.gi-badge { font-size: 0.65rem; }
.gi-btn-preview { font-size: 0.7rem; padding: 2px 7px; opacity: 0.7; }
.gi-btn-reprocess { font-size: 0.7rem; padding: 2px 8px; }
.gi-btn-sm-action { font-size: 0.75rem; padding: 4px 10px; }
.gi-progress-wrap { text-align: center; padding: 8px 0; }
.gi-progress-subject {
  font-size: 0.78rem; margin-bottom: 16px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 280px; margin-left: auto; margin-right: auto;
}
.gi-progress-track { background: var(--fin-border); border-radius: 999px; height: 6px; overflow: hidden; }
.gi-progress-fill  { background: var(--fin-accent); height: 100%; transition: width 0.3s; }
.gi-progress-pct   { font-size: 0.72rem; margin-top: 8px; }
.gi-preview-meta   { margin-bottom: 12px; font-size: 0.8rem; display: flex; flex-direction: column; gap: 4px; }
.gi-preview-body   {
  white-space: pre-wrap; word-break: break-word; font-size: 0.78rem;
  line-height: 1.6; max-height: 420px; overflow-y: auto;
  background: var(--fin-bg, #F4FBF3); padding: 12px;
  border-radius: var(--fin-radius); border: 1px solid var(--fin-border);
}
.gi-review-item {
  border-radius: 8px; padding: 14px; margin-bottom: 10px;
  background: var(--fin-surface);
}
.gi-review-grid    { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.gi-review-monto   { display: grid; grid-template-columns: 1fr 80px; gap: 6px; }
.gi-full-col       { grid-column: 1 / -1; }
.gi-form-sm label  { font-size: 0.72rem; }
.gi-form-sm input,
.gi-form-sm select { font-size: 0.78rem; padding: 5px 8px; }
.gi-review-scroll  { max-height: 520px; overflow-y: auto; padding-right: 4px; }
.gi-save-rule-row  {
  margin-top: 4px; display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; background: var(--fin-surface-2);
  border-radius: var(--fin-radius); border: 1px solid var(--fin-border);
}
.gi-save-rule-row input[type="checkbox"] { cursor: pointer; accent-color: var(--fin-accent); }
.gi-save-rule-row label { font-size: 0.78rem; cursor: pointer; margin: 0; }
.gi-warning-block  {
  border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;
}
.gi-warning-block--danger {
  background: color-mix(in srgb, var(--fin-danger) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--fin-danger) 30%, transparent);
}
.gi-warning-block--success {
  background: color-mix(in srgb, var(--fin-success) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--fin-success) 30%, transparent);
  font-size: 0.82rem;
}
.gi-warning-title  { font-weight: 600; font-size: 0.875rem; margin-bottom: 6px; }
.gi-summary-row {
  display: flex; justify-content: space-between;
  font-size: 0.82rem; padding: 5px 0;
  border-bottom: 1px solid var(--fin-border);
}
.gi-prompt-summary { font-size: 0.75rem; cursor: pointer; user-select: none; padding: 6px 8px; border-radius: var(--fin-radius); border: 1px solid var(--fin-border); }
.gi-prompt-pre     {
  margin-top: 6px; white-space: pre-wrap; word-break: break-word;
  font-size: 0.72rem; line-height: 1.55; max-height: 340px; overflow-y: auto;
  background: var(--fin-bg, #F4FBF3); padding: 12px;
  border-radius: var(--fin-radius); border: 1px solid var(--fin-border);
}
.gi-monto-grid { display: grid; grid-template-columns: 1fr 120px; gap: 12px; }
.gi-card-title-ellipsis { font-size: 0.875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gi-right-empty { padding: 32px; text-align: center; }
.gi-right-icon  { font-size: 2rem; margin-bottom: 12px; }
.gi-analyzing   { padding: 32px; text-align: center; }
.gi-spinner-center { margin: 0 auto 16px; }
.gi-process-label { font-size: 0.9rem; font-weight: 500; margin-bottom: 6px; }
.gi-filter-card-body { padding: 16px; }
.gi-fg-compact  { margin: 0; }
.gi-email-row-top   { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.gi-email-row-left  { display: flex; align-items: flex-start; min-width: 0; flex: 1; }
.gi-email-row-content { min-width: 0; flex: 1; }
.gi-email-badge { flex-shrink: 0; }
.gi-review-item-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.gi-review-item-title  { flex: 1; min-width: 0; }
.gi-review-check { cursor: pointer; accent-color: var(--fin-accent); }
.gi-card-body-md { padding: 20px; }
.gi-actions-row  { display: flex; gap: 10px; margin-top: 20px; }
.gi-cancel-right { margin-left: auto; }
.gi-review-info-text { font-size: 0.78rem; }
.gi-summary-note { font-size: 0.8rem; margin: 0; }
.gi-warning-detail { font-size: 0.82rem; }
`;

function _ensureStyles() {
  if (document.getElementById('gi-styles')) return;
  const el = document.createElement('style');
  el.id = 'gi-styles';
  el.textContent = _CSS;
  document.head.appendChild(el);
}

const LAST_SYNC_KEY = 'gmailImport.lastSyncDate';

const defaultSince = () => {
  const stored = localStorage.getItem(LAST_SYNC_KEY);
  if (stored) return stored;
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().split('T')[0];
};

export async function mount(container) {
  _ensureStyles();
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
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚠️</div>
        <h3>Error al cargar</h3>
        <p>${sanitize(err.message)}</p>
        <button class="btn btn-primary" id="btnRetry">Reintentar</button>
      </div>`;
    container.querySelector('#btnRetry').addEventListener('click', () => mount(container));
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

    <div class="gi-layout">
      <div>
        <div class="card mb-3">
          <div class="card-body gi-filter-card-body">
            <div class="gi-filter-bar">
              <div class="form-group fg-date">
                <label class="form-label">Desde</label>
                <input type="date" id="gi-since" value="${defaultSince()}">
              </div>
              <div class="form-group fg-max">
                <label class="form-label">Máx.</label>
                <input type="number" id="gi-max" value="50" min="1" max="200">
              </div>
              <div class="form-group fg-model">
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
              <button class="btn btn-warning" id="btnReprocessAll" title="Resetea todos los correos procesados/omitidos y los reprocesa con Ollama">↺ Reprocesar todos</button>
            </div>
          </div>
        </div>

        <div id="gi-bulk-toolbar" class="gi-bulk-toolbar">
          <span id="gi-bulk-count" class="gi-bulk-count text-muted">0 seleccionados</span>
          <button class="btn btn-secondary btn-sm gi-btn-sm-action" id="btnSelectAll">Todos los pendientes</button>
          <button class="btn btn-secondary btn-sm gi-btn-sm-action" id="btnSelectNone">Ninguno</button>
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
  container.querySelector('#btnReprocessAll').addEventListener('click', () => reprocessAll(container));
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
    localStorage.setItem(LAST_SYNC_KEY, todayISO());
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
    <div class="gi-list-meta text-muted">
      ${_emails.length} correo${_emails.length !== 1 ? 's' : ''} ·
      <span class="text-warning">${pending.length} pendiente${pending.length !== 1 ? 's' : ''}</span>
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
    ? '<span class="badge badge-success gi-badge">Procesado</span>'
    : email.skipped
    ? '<span class="badge badge-neutral gi-badge">Omitido</span>'
    : '<span class="badge badge-warning gi-badge">Pendiente</span>';

  const mid = sanitize(email.message_id);

  const bulkCheckbox = _bulkMode
    ? `<input type="checkbox" class="gi-bulk-check" data-mid="${mid}" data-pending="${isPending}"
         ${_selectedIds.has(email.message_id) ? 'checked' : ''}>`
    : '';

  const previewBtn = `<button class="btn btn-ghost btn-sm btn-preview gi-btn-preview" data-mid="${mid}" title="Ver cuerpo del correo">👁</button>`;

  const reprocessBtn = !isPending
    ? `<button class="btn btn-ghost btn-sm btn-reprocess gi-btn-reprocess text-warning" data-mid="${mid}"
         title="Reprocesar con las reglas actuales (elimina la transacción anterior)">↺ Reprocesar</button>`
    : '';

  const actions = isPending
    ? `<div class="gi-email-actions">
        <button class="btn btn-primary btn-sm btn-process gi-btn-sm-action" data-mid="${mid}">Procesar</button>
        <button class="btn btn-secondary btn-sm btn-skip gi-btn-sm-action" data-mid="${mid}">Omitir</button>
        ${previewBtn}
       </div>`
    : `<div class="gi-email-actions is-done">${reprocessBtn}${previewBtn}</div>`;

  const isSelected = _selectedMessageId === email.message_id;
  return `
    <div class="gi-email-row${isSelected ? ' is-selected' : ''}">
      <div class="gi-email-row-top">
        <div class="gi-email-row-left">
          ${bulkCheckbox}
          <div class="gi-email-row-content">
            <div class="gi-email-subject">${sanitize(email.subject || '(sin asunto)')}</div>
            <div class="gi-email-meta text-muted">
              ${fmtDate(email.received_at)} · ${sanitize((email.sender || '').replace(/<.*>/, '').trim())}
            </div>
            <div class="gi-email-preview text-soft">
              ${sanitize((email.preview || '').substring(0, 120))}
            </div>
          </div>
        </div>
        <div class="gi-email-badge">${statusBadge}</div>
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
      <div class="gi-preview-meta text-muted">
        <div><strong>De:</strong> ${sanitize(data.sender || '')}</div>
        <div><strong>Fecha:</strong> ${fmtDate(data.received_at)}</div>
      </div>
      <hr style="border-color:var(--fin-border);margin:0 0 12px">
      <pre class="gi-preview-body">${sanitize(data.body_text)}</pre>`;
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
  if (toolbar) toolbar.classList.toggle('is-active', _bulkMode);

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
  let ignoredCount = 0;

  for (let i = 0; i < ids.length; i++) {
    const messageId = ids[i];
    const email = _emails.find(e => e.message_id === messageId);
    progressModal.body.innerHTML = buildProgressHTML(i, ids.length, email?.subject || messageId);

    try {
      const result = await api.gmailImport.process(messageId, selectedModel);
      if (result.ignored) {
        if (email) email.skipped = true;
        ignoredCount++;
        continue;
      }
      const esTransaccion = result.es_transaccion !== false;
      const confianzaBaja = typeof result.confianza === 'number' && result.confianza < 50;
      const included = esTransaccion && !confianzaBaja;
      processedItems.push({ messageId, email, result, included, error: null });
    } catch (err) {
      processedItems.push({ messageId, email, result: {}, included: false, error: err.message });
    }
  }

  progressModal.close();
  if (ignoredCount > 0) {
    toast.info(`${ignoredCount} correo${ignoredCount !== 1 ? 's' : ''} omitido${ignoredCount !== 1 ? 's' : ''} automáticamente (comercio ignorado)`);
    renderEmailList(container);
  }
  if (processedItems.length === 0) return;
  showBulkReviewModal(container, processedItems);
}

function buildProgressHTML(current, total, subject) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  return `
    <div class="gi-progress-wrap">
      <div class="spinner gi-spinner-center"></div>
      <div class="gi-process-label">Procesando ${current + 1} de ${total}</div>
      <div class="gi-progress-subject text-muted">${sanitize(subject)}</div>
      <div class="gi-progress-track">
        <div class="gi-progress-fill" style="width:${pct}%"></div>
      </div>
      <div class="gi-progress-pct text-muted">${pct}%</div>
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
    const noEsTransaccion = r.es_transaccion === false;
    const confianzaBaja = typeof r.confianza === 'number' && r.confianza < 50;
    const borderColor = hasError
      ? 'var(--fin-danger)'
      : noEsTransaccion
      ? 'var(--fin-danger)'
      : (confianzaBaja || !r.cuenta_id || !r.monto)
      ? 'var(--fin-amber)'
      : 'var(--fin-border)';
    const confianzaBadge = typeof r.confianza === 'number'
      ? `<span class="text-muted">· confianza ${r.confianza}%${noEsTransaccion ? ' (no parece transacción)' : ''}</span>`
      : '';

    return `
      <div class="gi-review-item" style="border:1px solid ${borderColor}">
        <div class="gi-review-item-header">
          <input type="checkbox" class="br-include" data-idx="${idx}" ${item.included ? 'checked' : ''} class="gi-review-check">
          <div class="gi-review-item-title">
            <div class="gi-email-subject">${sanitize(item.email?.subject || item.messageId)}</div>
            <div class="gi-email-meta text-muted">
              ${fmtDate(item.email?.received_at)}
              ${hasError ? `· <span class="text-danger">Error: ${sanitize(item.error)}</span>` : confianzaBadge}
            </div>
          </div>
        </div>
        ${hasError ? '' : `
        <div class="gi-review-grid gi-form-sm">
          <div class="form-group gi-fg-compact">
            <label class="form-label">Fecha</label>
            <input type="date" class="form-input br-fecha" data-idx="${idx}" value="${fecha}">
          </div>
          <div class="gi-review-monto">
            <div class="form-group gi-fg-compact">
              <label class="form-label">Monto</label>
              <input type="number" class="form-input br-monto" data-idx="${idx}" value="${monto}" min="0" step="0.01" placeholder="0.00">
            </div>
            <div class="form-group gi-fg-compact">
              <label class="form-label">Moneda</label>
              <select class="form-input br-moneda" data-idx="${idx}" style="padding:5px 6px">
                <option value="COP" ${moneda === 'COP' ? 'selected' : ''}>COP</option>
                <option value="USD" ${moneda === 'USD' ? 'selected' : ''}>USD</option>
              </select>
            </div>
          </div>
          <div class="form-group gi-fg-compact">
            <label class="form-label">Cuenta</label>
            <select class="form-input br-cuenta" data-idx="${idx}">
              <option value="">— seleccionar —</option>${accountOptions(r.cuenta_id)}
            </select>
          </div>
          <div class="form-group gi-fg-compact">
            <label class="form-label">Categoría</label>
            <select class="form-input br-categoria" data-idx="${idx}">
              ${categoryOptions(r.categoria_id)}
            </select>
          </div>
          <div class="form-group gi-full-col" style="margin:0">
            <label class="form-label">Comentario</label>
            <input type="text" class="form-input br-comentario" data-idx="${idx}" value="${sanitize(r.comentario || '')}" placeholder="Descripción del gasto">
          </div>
        </div>`}
      </div>`;
  });

  return `
    <div class="text-muted mb-3 gi-review-info-text">
      Revisa y ajusta los campos antes de confirmar. Desmarca los correos que no quieras importar.
    </div>
    <div class="gi-review-scroll">
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
// Individual processing
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
      <div class="card-body gi-analyzing">
        <div class="spinner gi-spinner-center"></div>
        <p class="text-muted">Analizando con Ollama${selectedModel ? ` (${sanitize(selectedModel)})` : ''}… esto puede tardar 10-20 segundos.</p>
      </div>
    </div>`;

  try {
    const result = await api.gmailImport.process(messageId, selectedModel);
    if (result.ignored) {
      const email = _emails.find(e => e.message_id === messageId);
      if (email) email.skipped = true;
      _selectedMessageId = null;
      renderEmailList(container);
      rightPanel.innerHTML = rightPanelEmpty();
      toast.info(`Correo omitido automáticamente (comercio ignorado: ${result.matched_merchant})`);
      return;
    }
    renderConfirmForm(container, messageId, result);
  } catch (err) {
    renderManualForm(container, messageId, `Ollama no disponible: ${err.message}`);
  }
}

function renderConfirmForm(container, messageId, ollama) {
  const rightPanel = container.querySelector('#gi-right-panel');
  const email = _emails.find(e => e.message_id === messageId);

  const promptSection = ollama._prompt
    ? `<details class="mt-3">
        <summary class="gi-prompt-summary text-muted">Ver prompt enviado al LLM</summary>
        <pre class="gi-prompt-pre text-muted">${sanitize(ollama._prompt)}</pre>
      </details>`
    : '';

  const noEsTransaccion = ollama.es_transaccion === false;
  const confianzaBadge = typeof ollama.confianza === 'number'
    ? `<div class="gi-email-meta text-muted mb-2">
         Confianza del modelo: ${ollama.confianza}%
         ${noEsTransaccion ? ' · <span class="text-danger">el modelo indica que este correo no es una transacción</span>' : ''}
       </div>`
    : '';

  rightPanel.innerHTML = `
    <div class="card">
      <div class="card-header">
        <span class="card-title gi-card-title-ellipsis">
          ${sanitize(email?.subject || messageId)}
        </span>
      </div>
      <div class="card-body gi-card-body-md">
        ${confianzaBadge}
        ${formFields(ollama)}
        ${promptSection}
        <div class="gi-actions-row">
          <button class="btn btn-primary" id="btnConfirm">Confirmar</button>
          <button class="btn btn-secondary" id="btnManual">Ingresar manual</button>
          <button class="btn btn-ghost gi-cancel-right" id="btnCancelRight">Cancelar</button>
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
        <span class="card-title">Ingreso manual</span>
      </div>
      <div class="card-body gi-card-body-md">
        ${warningMsg ? `<div class="alert alert-warning mb-3 gi-review-info-text">${sanitize(warningMsg)}</div>` : ''}
        ${formFields({})}
        <div class="gi-actions-row">
          <button class="btn btn-primary" id="btnConfirm">Confirmar</button>
          <button class="btn btn-ghost gi-cancel-right" id="btnCancelRight">Cancelar</button>
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
    <div class="gi-monto-grid">
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
    <div class="gi-save-rule-row">
      <input type="checkbox" id="fi-save-rule">
      <label for="fi-save-rule">Guardar como regla de comercio para futuras importaciones</label>
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

// ---------------------------------------------------------------------------
// Reprocess all
// ---------------------------------------------------------------------------

async function reprocessAll(container) {
  if (!_emails.length) {
    toast.warning('Sincroniza primero para cargar correos.');
    return;
  }

  const processed = _emails.filter(e => e.processed || e.skipped);
  const pending   = _emails.filter(e => !e.processed && !e.skipped);

  const warningBlock = processed.length > 0
    ? `<div class="gi-warning-block gi-warning-block--danger">
        <div class="gi-warning-title text-danger">⚠ Transacciones que se eliminarán</div>
        <div class="text-muted" style="font-size:0.82rem">
          <strong>${sanitize(String(processed.length))} correo${processed.length !== 1 ? 's' : ''}</strong>
          ya procesado${processed.length !== 1 ? 's' : ''} o${processed.length !== 1 ? '' : ''} omitido${processed.length !== 1 ? 's' : ''}
          tendrán sus transacciones eliminadas de la base de datos.
        </div>

      </div>`
    : `<div class="gi-warning-block gi-warning-block--success text-muted">
        Sin transacciones previas en la lista — no se eliminará nada.
      </div>`;

  const summaryRows = [
    { label: 'Correos en lista',             value: _emails.length,   cls: '' },
    { label: 'Pendientes (se procesarán)',   value: pending.length,   cls: 'text-warning' },
    { label: 'Ya procesados / omitidos',     value: processed.length, cls: processed.length > 0 ? 'text-danger' : '' },
  ].map(r => `
    <div class="gi-summary-row">
      <span class="text-muted">${r.label}</span>
      <strong class="${r.cls}">${r.value}</strong>
    </div>`).join('');

  const modal = openModal({
    title: '↺ Reprocesar todos los correos',
    size: 'sm',
    content: `
      ${warningBlock}
      <div class="mb-3">${summaryRows}</div>
      <p class="text-muted" style="font-size:0.8rem;margin:0">
        Solo se afectan los <strong>${_emails.length} correo${_emails.length !== 1 ? 's' : ''}</strong>
        cargados actualmente en la lista. Ollama los analizará uno a uno.
      </p>`,
    submitLabel: processed.length > 0 ? `Eliminar y reprocesar (${processed.length})` : `Reprocesar todo (${_emails.length})`,
    cancelLabel: 'Cancelar',
    submitClass: processed.length > 0 ? 'btn btn-danger' : 'btn btn-primary',
    onSubmit: async () => {
      modal.close();
      await _doReprocessAll(container);
    },
  });
}

async function _doReprocessAll(container) {
  const btn = container.querySelector('#btnReprocessAll');
  btn.disabled = true;
  btn.textContent = 'Reseteando...';

  const listMessageIds = _emails.map(e => e.message_id);

  try {
    const { reset_count, deleted_transaction_count } = await api.gmailImport.reprocessAll({ message_ids: listMessageIds });
    if (reset_count > 0) {
      toast.info(`${reset_count} correo${reset_count !== 1 ? 's' : ''} reseteado${reset_count !== 1 ? 's' : ''} · ${deleted_transaction_count} transacción${deleted_transaction_count !== 1 ? 'es' : ''} eliminada${deleted_transaction_count !== 1 ? 's' : ''}`);
    }

    _emails.forEach(e => { e.processed = false; e.skipped = false; e.transaction_id = null; });
    _selectedIds.clear();
    _emails.forEach(e => _selectedIds.add(e.message_id));

    renderEmailList(container);
    await startBulkProcess(container);
  } catch (err) {
    toast.error(`Error al reprocesar: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '↺ Reprocesar todos';
  }
}

function rightPanelEmpty() {
  return `
    <div class="card">
      <div class="card-body gi-right-empty text-muted">
        <div class="gi-right-icon">✉️</div>
        <p>Selecciona un correo y presiona <strong>Procesar</strong> para analizarlo con Ollama.</p>
      </div>
    </div>`;
}
