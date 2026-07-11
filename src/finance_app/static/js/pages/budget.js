import * as api from '../api/client.js';
import { fmtCurrency, sanitize, currentMonth, prevMonth, nextMonth, fmtMonthLabel, optional, progressBar, progressPct } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Presupuesto';

let _month = currentMonth();
let _data  = null;
let _cats  = [];
let _rate  = 4200; // COP per 1 USD

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  await loadAndRender(container);
}

async function loadAndRender(container) {
  try {
    const [budgetData, cats, rateData] = await Promise.all([
      api.budgets.month(_month),
      api.categories.list(),
      optional(api.exchangeRates.current(), null, 'Tasa de Cambio'),
    ]);
    _data = budgetData;
    _cats = cats;
    if (rateData?.rate) _rate = rateData.rate;
    renderPage(container);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

// Flatten API groups structure into enriched category list
function flattenBudgetCats(data) {
  const cats = [];
  for (const group of (data?.groups ?? [])) {
    for (const cat of (group.categories ?? [])) {
      cats.push({
        ...cat,
        group: group.name,
        group_id: group.id,
        category_type: group.is_income ? 'income' : (cat.rollover_type === 'accumulate' ? 'savings' : 'expense'),
        spent: Math.abs(cat.activity ?? 0),
        available: cat.available ?? 0,
        covered: cat.covered ?? 0,
      });
    }
  }
  return cats;
}

// Show amount in its native currency with the other below.
// amount is always the COP-equivalent (from API). For USD categories, assigned_native holds the USD value.
function fmtDual(amount_cop, currency = 'COP', native = null) {
  if (currency === 'USD') {
    const usdVal = native !== null ? native : amount_cop / _rate;
    return `${fmtCurrency(usdVal, 'USD')}<br><small class="text-soft" style="font-size:0.7rem">≈ ${fmtCurrency(amount_cop, 'COP')}</small>`;
  }
  const usd = amount_cop / _rate;
  return `${fmtCurrency(amount_cop, 'COP')}<br><small class="text-soft" style="font-size:0.7rem">≈ ${fmtCurrency(usd, 'USD')}</small>`;
}

function renderPage(container) {
  const cats = flattenBudgetCats(_data);
  const expCats = cats.filter(c => c.category_type !== 'income');
  const savCats = cats.filter(c => c.category_type === 'savings');

  const totalAssigned    = expCats.reduce((s, c) => s + (c.assigned ?? 0), 0);
  const totalSpent       = expCats.reduce((s, c) => s + (c.spent    ?? 0), 0);
  const totalAvailable   = expCats.reduce((s, c) => s + (c.available ?? 0), 0);
  const totalSavings     = savCats.reduce((s, c) => s + (c.available ?? 0), 0);
  const readyToAssign    = _data?.ready_to_assign ?? 0;

  const groups = groupByGroup(cats);
  _isFirstGroup = true;
  _groupIndex   = 0;

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Presupuesto</h1>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-ghost btn-sm" id="btnRecalcSavings" title="Recalcula el disponible acumulado de todas las categorías de ahorro">↻ Recalcular ahorros</button>
        <button class="btn btn-ghost btn-sm" id="btnAddGroup">+ Grupo</button>
        <button class="btn btn-secondary btn-sm" id="btnAddCategory">+ Categoría</button>
        <button class="btn btn-primary btn-sm" id="btnInitMonth">Inicializar mes</button>
      </div>
    </div>

    <div class="flex items-center gap-4 mb-4">
      <div class="month-nav">
        <button class="btn btn-ghost btn-sm" id="btnPrevMonth">‹ Anterior</button>
        <span class="month-nav-label">${fmtMonthLabel(_month)}</span>
        <button class="btn btn-ghost btn-sm" id="btnNextMonth">Siguiente ›</button>
      </div>
    </div>

    <div class="stat-row mb-4">
      <div class="stat-chip">
        <span class="stat-chip-label">Asignado</span>
        <span class="stat-chip-value amount">${fmtCurrency(totalAssigned, 'COP')}</span>
        <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(totalAssigned / _rate, 'USD')}</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip-label">Gastado</span>
        <span class="stat-chip-value text-danger amount">${fmtCurrency(totalSpent, 'COP')}</span>
        <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(totalSpent / _rate, 'USD')}</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip-label">Disponible</span>
        <span class="stat-chip-value amount ${totalAvailable >= 0 ? 'text-success' : 'text-danger'}">
          ${fmtCurrency(totalAvailable, 'COP')}
        </span>
        <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(totalAvailable / _rate, 'USD')}</span>
      </div>
      ${totalSavings > 0 ? `
        <div class="stat-chip">
          <span class="stat-chip-label">Ahorros acumulados</span>
          <span class="stat-chip-value amount" style="color:var(--fin-accent)">${fmtCurrency(totalSavings, 'COP')}</span>
          <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(totalSavings / _rate, 'USD')}</span>
        </div>` : ''}
      <div class="stat-chip" style="border-color:${readyToAssign >= 0 ? 'var(--fin-success)' : 'var(--fin-danger)'}">
        <span class="stat-chip-label">
          Listo para asignar
          <span class="info-tooltip" tabindex="0" aria-label="Explicación de Listo para asignar">
            &#9432;
            <span class="tooltip-text">
              Dinero que tienes pero aún no has asignado a ninguna categoría.<br><br>
              <strong>= Saldo en cuentas de ahorro − Total disponible en presupuesto</strong><br><br>
              Positivo: hay dinero sin categorizar.<br>
              Negativo: asignaste más de lo que tienes.<br>
              Ideal: $0 (cada peso tiene un destino).
            </span>
          </span>
        </span>
        <span class="stat-chip-value amount ${readyToAssign >= 0 ? 'text-success' : 'text-danger'}">
          ${fmtCurrency(readyToAssign, 'COP')}
        </span>
        <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(readyToAssign / _rate, 'USD')}</span>
      </div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width:24%">Categoría</th>
            <th class="td-right" style="width:13%">Asignado<br><small class="text-soft" style="font-weight:400">COP / USD</small></th>
            <th class="td-right" style="width:13%">Gastado<br><small class="text-soft" style="font-weight:400">COP / USD</small></th>
            <th class="td-right" style="width:13%">Cubierto
              <span class="info-tooltip" tabindex="0" aria-label="Explicación de Cubierto" style="font-size:0.75rem;font-weight:400">
                &#9432;
                <span class="tooltip-text">
                  Movimientos internos de cobertura.<br><br>
                  <strong>Positivo:</strong> recibió dinero de otra categoría para cubrir su déficit.<br>
                  <strong>Negativo:</strong> cedió dinero a otra categoría.
                </span>
              </span>
              <br><small class="text-soft" style="font-weight:400">COP / USD</small>
            </th>
            <th class="td-right" style="width:13%">Disponible<br><small class="text-soft" style="font-weight:400">COP / USD</small></th>
            <th style="width:19%">Uso</th>
            <th style="width:5%"></th>
          </tr>
        </thead>
        <tbody>
          ${Object.entries(groups).map(([grp, list]) => groupRows(grp, list)).join('')}
        </tbody>
      </table>
    </div>
  `;

  // Month navigation
  container.querySelector('#btnPrevMonth').addEventListener('click', async () => {
    _month = prevMonth(_month);
    await loadAndRender(container);
  });
  container.querySelector('#btnNextMonth').addEventListener('click', async () => {
    _month = nextMonth(_month);
    await loadAndRender(container);
  });

  // Initialize month
  container.querySelector('#btnInitMonth').addEventListener('click', async () => {
    try {
      await api.budgets.initialize(_month);
      toast.success('Mes inicializado desde plantilla');
      await loadAndRender(container);
    } catch (err) {
      toast.error(err.message);
    }
  });

  // Recalculate savings rollover
  container.querySelector('#btnRecalcSavings').addEventListener('click', async () => {
    if (!confirm('¿Recalcular el disponible acumulado de todas las categorías de ahorro? Esto corrige datos desincronizados.')) return;
    try {
      await api.budgets.recalcSavings();
      toast.success('Ahorros recalculados correctamente');
      await loadAndRender(container);
    } catch (err) {
      toast.error(err.message);
    }
  });

  // Add group
  container.querySelector('#btnAddGroup').addEventListener('click', () => openGroupModal(null, container));

  // Add category
  container.querySelector('#btnAddCategory').addEventListener('click', () => openCategoryModal(null, container));

  // Edit group (click on group header row)
  container.querySelectorAll('[data-edit-group]').forEach(el => {
    const group = (_data?.groups ?? []).find(g => g.id === parseInt(el.dataset.editGroup));
    el.addEventListener('click', () => openGroupModal(group, container));
  });

  // Edit assigned cells
  container.querySelectorAll('[data-edit-assigned]').forEach(el => {
    el.addEventListener('click', () => openAssignedModal(el, container));
  });

  // Edit category
  container.querySelectorAll('[data-edit-cat]').forEach(btn => {
    const cat = cats.find(c => c.category_id === parseInt(btn.dataset.editCat));
    btn.addEventListener('click', () => openCategoryModal(cat, container));
  });

  // Cover overspending
  container.querySelectorAll('[data-cover-cat]').forEach(btn => {
    const cat = cats.find(c => c.category_id === parseInt(btn.dataset.coverCat));
    btn.addEventListener('click', () => openCoverModal(cat, cats, container));
  });
}

const GROUP_ACCENTS = ['#E07B54','#4E9D8F','#7B68C8','#C4883A','#4A90C4','#C45E8A','#5DA06A','#8E6BBF'];
let _isFirstGroup = true;
let _groupIndex   = 0;

function groupRows(group, cats) {
  const grpId       = cats[0]?.group_id ?? '';
  const grpName     = sanitize(group || 'Sin grupo');
  const totAssigned  = cats.reduce((s, c) => s + (c.assigned  ?? 0), 0);
  const totSpent     = cats.reduce((s, c) => s + (c.spent     ?? 0), 0);
  const totAvailable = cats.reduce((s, c) => s + (c.available ?? 0), 0);
  const totCovered   = cats.reduce((s, c) => s + (c.covered   ?? 0), 0);

  const accent      = GROUP_ACCENTS[_groupIndex % GROUP_ACCENTS.length];
  _groupIndex++;

  const pct         = progressPct(totSpent, totAssigned);
  const pctColor    = pct >= 100 ? '#DC2626' : pct >= 80 ? '#D97706' : '#059669';
  const pctLabel    = totAssigned > 0 ? `${Math.round(pct)}%` : '—';
  const availSign   = totAvailable >= 0 ? '+' : '';
  const availColor  = totAvailable >= 0 ? '#059669' : '#DC2626';

  const coveredSign  = totCovered >= 0 ? '+' : '';
  const coveredColor = totCovered > 0 ? '#4A90C4' : totCovered < 0 ? '#D97706' : 'var(--fin-ink-3)';

  const spacer = _isFirstGroup ? '' : `<tr><td colspan="7" style="height:20px;padding:0;border:none;background:transparent"></td></tr>`;
  _isFirstGroup = false;

  const header = `
    ${spacer}
    <tr class="budget-group-header" style="background:var(--fin-surface-2)">
      <td colspan="7" style="padding:0;border:none">
        <div style="
          border-left: 4px solid ${accent};
          border-top: 1px solid var(--fin-border);
          background: linear-gradient(90deg, ${accent}0d 0%, transparent 40%);
          padding: 10px 16px 8px 18px;
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 8px;
          align-items: center;
        ">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:0.72rem;font-weight:800;text-transform:uppercase;letter-spacing:0.09em;color:${accent};${grpId ? 'cursor:pointer' : ''}"
              ${grpId ? `data-edit-group="${grpId}" title="Editar grupo"` : ''}>${grpName}</span>
            <span style="
              font-size:0.67rem;font-weight:700;
              background:${pctColor}1a;color:${pctColor};
              border:1px solid ${pctColor}33;
              border-radius:999px;padding:1px 7px;
              font-variant-numeric:tabular-nums;
            ">${pctLabel} usado</span>
          </div>
          <div style="display:flex;align-items:center;gap:16px">
            <span style="font-size:0.72rem;color:var(--fin-ink-3)">
              <span style="font-variant-numeric:tabular-nums">${fmtCurrency(totSpent,'COP')}</span>
              <span style="margin:0 3px;opacity:0.4">/</span>
              <span style="font-variant-numeric:tabular-nums">${fmtCurrency(totAssigned,'COP')}</span>
            </span>
            ${totCovered !== 0 ? `<span style="font-size:0.72rem;font-weight:700;color:${coveredColor};font-variant-numeric:tabular-nums">${coveredSign}${fmtCurrency(totCovered,'COP')}</span>` : ''}
            <span style="font-size:0.72rem;font-weight:700;color:${availColor};font-variant-numeric:tabular-nums;min-width:72px;text-align:right">${availSign}${fmtCurrency(totAvailable,'COP')}</span>
          </div>
        </div>
        <div style="height:3px;background:var(--fin-border)">
          <div style="height:100%;width:${Math.min(pct,100)}%;background:${pctColor};transition:width 0.4s ease"></div>
        </div>
      </td>
    </tr>`;
  const rows = cats.map(c => categoryRow(c, accent)).join('');
  return header + rows;
}

function categoryRow(c, groupAccent = 'var(--fin-border)') {
  const assigned        = c.assigned        ?? 0;
  const assigned_native = c.assigned_native ?? null;
  const currency_code   = c.currency_code   ?? 'COP';
  const spent           = c.spent           ?? 0;
  const available       = c.available       ?? 0;
  const covered         = c.covered         ?? 0;
  const initial_amount  = c.initial_amount  ?? 0;
  const isSavings       = c.category_type   === 'savings';

  const assignedHtml = isSavings && initial_amount > 0
    ? `${fmtDual(assigned, currency_code, assigned_native)}<br><small class="amount" style="color:var(--fin-accent);font-size:0.68rem;white-space:nowrap">+ ${fmtCurrency(initial_amount, 'COP')} guardado</small>`
    : fmtDual(assigned, currency_code, assigned_native);

  const availClass = available >= 0 ? 'text-success' : 'text-danger';

  const pct      = progressPct(spent, assigned);
  const pctColor = pct >= 100 ? '#DC2626' : pct >= 80 ? '#D97706' : '#059669';
  const pctLabel = assigned > 0 ? `${Math.round(pct)}%` : '—';

  const usoCel = assigned > 0
    ? `<div style="display:flex;align-items:center;gap:6px">
         <div style="flex:1;height:6px;background:var(--fin-surface-3);border-radius:999px;overflow:hidden">
           <div style="height:100%;width:${Math.min(pct,100)}%;background:${pctColor};border-radius:999px;transition:width 0.35s ease"></div>
         </div>
         <span style="font-size:0.72rem;font-weight:700;color:${pctColor};font-variant-numeric:tabular-nums;min-width:32px;text-align:right">${pctLabel}</span>
       </div>`
    : `<span style="font-size:0.72rem;color:var(--fin-ink-3)">—</span>`;

  const coverBtn = (spent > assigned && assigned > 0) || available < 0
    ? `<button class="btn btn-xs" data-cover-cat="${c.category_id}" title="Cubrir exceso con otra categoría" style="background:var(--fin-danger);color:#fff;opacity:0.85;font-size:0.65rem;padding:2px 6px;margin-right:4px">Cubrir</button>`
    : '';

  const coveredClass = covered > 0 ? '' : covered < 0 ? 'text-warning' : 'td-soft';
  const coveredSign  = covered > 0 ? '+' : '';
  const coveredHtml  = covered !== 0
    ? `<span style="color:${covered > 0 ? '#4A90C4' : '#D97706'};font-weight:600">${coveredSign}${fmtDual(covered)}</span>`
    : `<span class="td-soft">—</span>`;

  return `
    <tr>
      <td style="font-size:0.8125rem;font-weight:500;padding-left:28px;border-left:3px solid ${groupAccent}33">
        ${sanitize(c.category_name)}
        ${isSavings ? '<span class="badge badge-accent" style="margin-left:6px;font-size:0.6rem">Ahorro</span>' : ''}
      </td>
      <td class="td-right td-mono" style="cursor:pointer;font-size:0.8125rem;line-height:1.4" data-edit-assigned="${c.category_id}" data-month="${_month}">
        ${assignedHtml}
      </td>
      <td class="td-right td-mono td-soft" style="font-size:0.8125rem;line-height:1.4">${fmtDual(spent)}</td>
      <td class="td-right td-mono" style="font-size:0.8125rem;line-height:1.4">${coveredHtml}</td>
      <td class="td-right td-mono ${availClass}" style="font-size:0.8125rem;line-height:1.4">
        ${fmtDual(available)}
      </td>
      <td style="padding-right:12px">${usoCel}</td>
      <td style="white-space:nowrap">
        ${coverBtn}<button class="btn btn-ghost btn-xs" data-edit-cat="${c.category_id}" title="Editar categoría">⋯</button>
      </td>
    </tr>`;
}

function groupByGroup(cats) {
  const map = {};
  for (const c of cats) {
    const grp = c.group ?? 'Sin grupo';
    (map[grp] ??= []).push(c);
  }
  return map;
}

function openAssignedModal(el, container) {
  const catId    = parseInt(el.dataset.editAssigned);
  const cat      = flattenBudgetCats(_data).find(c => c.category_id === catId);
  if (!cat) return;

  const isSavings      = cat.category_type === 'savings';
  const currentCurrency = cat.currency_code ?? 'COP';
  const currentAmount   = cat.assigned_native ?? (currentCurrency === 'USD' ? (cat.assigned ?? 0) / _rate : (cat.assigned ?? 0));
  // initial_amount from API is in display currency (COP). Convert to primary currency for editing.
  const initialNative   = currentCurrency === 'USD' ? (cat.initial_amount ?? 0) / _rate : (cat.initial_amount ?? 0);
  const spentCOP        = cat.spent ?? 0;
  const spentUSD        = spentCOP / _rate;

  const modal = openModal({
    title: `Asignar: ${cat.category_name}`,
    size: 'sm',
    content: `
      <p class="mb-3" style="font-size:0.875rem">
        Gastado: <strong class="amount">${fmtCurrency(spentCOP, 'COP')}</strong>
        <span class="text-soft">(≈ ${fmtCurrency(spentUSD, 'USD')})</span>
      </p>
      <div class="form-row cols-2" style="grid-template-columns:2fr 1fr">
        <div class="form-group">
          <label class="form-label required">Asignado este mes</label>
          <input type="number" id="ma-amount" value="${currentCurrency === 'USD' ? currentAmount.toFixed(2) : Math.round(currentAmount)}" step="${currentCurrency === 'USD' ? '0.01' : '1000'}" autofocus>
        </div>
        <div class="form-group">
          <label class="form-label">Moneda</label>
          <select id="ma-currency">
            <option value="COP" ${currentCurrency === 'COP' ? 'selected' : ''}>COP</option>
            <option value="USD" ${currentCurrency === 'USD' ? 'selected' : ''}>USD</option>
          </select>
        </div>
      </div>
      <p id="ma-preview" class="text-soft" style="font-size:0.8rem;margin-top:4px"></p>
      ${isSavings ? `
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--fin-surface-2)">
          <p class="text-soft" style="font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:10px">Ya ahorrado (acumulado anterior)</p>
          <div class="form-group">
            <label class="form-label">Monto (${currentCurrency})</label>
            <input type="number" id="ma-initial" value="${currentCurrency === 'USD' ? initialNative.toFixed(2) : Math.round(initialNative)}" step="${currentCurrency === 'USD' ? '0.01' : '1000'}" min="0">
          </div>
          <p id="ma-initial-preview" class="text-soft" style="font-size:0.8rem;margin-top:4px"></p>
        </div>
      ` : ''}
    `,
    submitLabel: 'Guardar',
    onSubmit: async (body) => {
      const amount = parseFloat(body.querySelector('#ma-amount').value);
      const currency_code = body.querySelector('#ma-currency').value;
      if (isNaN(amount) || amount < 0) throw new Error('Monto inválido');

      if (isSavings) {
        const initial = parseFloat(body.querySelector('#ma-initial').value);
        if (isNaN(initial) || initial < 0) throw new Error('Monto acumulado inválido');
        // initial is always in currency_code (same as assigned); single call
        await api.budgets.update(_month, catId, { assigned: amount, currency_code, initial_amount: initial });
      } else {
        await api.budgets.update(_month, catId, { assigned: amount, currency_code });
      }

      toast.success('Asignación actualizada');
      await loadAndRender(container);
    },
  });

  const amtInput  = modal.body.querySelector('#ma-amount');
  const curSelect = modal.body.querySelector('#ma-currency');
  const preview   = modal.body.querySelector('#ma-preview');

  function updatePreview() {
    const amt = parseFloat(amtInput.value) || 0;
    preview.textContent = curSelect.value === 'COP'
      ? `≈ ${fmtCurrency(amt / _rate, 'USD')}`
      : `≈ ${fmtCurrency(amt * _rate, 'COP')}`;
  }
  updatePreview();
  amtInput.addEventListener('input', updatePreview);
  curSelect.addEventListener('change', () => {
    const amt = parseFloat(amtInput.value) || 0;
    if (curSelect.value === 'USD') {
      amtInput.value = (amt / _rate).toFixed(2);
      amtInput.step  = '0.01';
    } else {
      amtInput.value = Math.round(amt * _rate);
      amtInput.step  = '1000';
    }
    updatePreview();
  });

  if (isSavings) {
    const initialInput   = modal.body.querySelector('#ma-initial');
    const initialPreview = modal.body.querySelector('#ma-initial-preview');
    if (initialInput && initialPreview) {
      const updateInitialPreview = () => {
        const amt = parseFloat(initialInput.value) || 0;
        initialPreview.textContent = currentCurrency === 'COP'
          ? `≈ ${fmtCurrency(amt / _rate, 'USD')}`
          : `≈ ${fmtCurrency(amt * _rate, 'COP')}`;
      };
      updateInitialPreview();
      initialInput.addEventListener('input', updateInitialPreview);
    }
  }
}

function openCategoryModal(cat, container) {
  const isEdit = !!cat;
  const c = cat ?? {};
  const groups = (_data?.groups ?? []).filter(g => !g.is_income);

  const modal = openModal({
    title: isEdit ? `Editar: ${c.category_name}` : 'Nueva Categoría',
    size: 'sm',
    content: `
      <div class="form-group mb-3">
        <label class="form-label required">Nombre</label>
        <input type="text" id="cf-name" value="${sanitize(c.category_name ?? '')}" placeholder="Ej: Alimentación" autofocus>
      </div>
      <div class="form-row cols-2">
        <div class="form-group">
          <label class="form-label">Tipo</label>
          <select id="cf-type">
            <option value="expense" ${c.category_type !== 'savings' ? 'selected' : ''}>Gasto</option>
            <option value="savings" ${c.category_type === 'savings' ? 'selected' : ''}>Ahorro (acumula)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Grupo</label>
          <select id="cf-group">
            ${groups.map(g => `<option value="${g.id}" ${g.id === c.group_id ? 'selected' : ''}>${sanitize(g.name)}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-group mt-3">
        <label class="flex items-center gap-2" style="cursor:pointer;font-size:0.875rem">
          <input type="checkbox" id="cf-essential" ${c.is_essential ? 'checked' : ''} style="width:16px;height:16px;cursor:pointer">
          <span>Gasto esencial <span class="text-soft" style="font-size:0.8125rem">(Necesidades en salud financiera)</span></span>
        </label>
      </div>
      ${isEdit ? `
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--fin-surface-2)">
          <button class="btn btn-danger btn-sm w-full" id="cf-delete-btn">Eliminar categoría</button>
        </div>
      ` : ''}
    `,
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const name = body.querySelector('#cf-name').value.trim();
      const type = body.querySelector('#cf-type').value;
      const groupId = parseInt(body.querySelector('#cf-group').value);
      const isEssential = body.querySelector('#cf-essential').checked;
      if (!name) throw new Error('El nombre es obligatorio');
      if (isNaN(groupId)) throw new Error('Selecciona un grupo');

      if (isEdit) {
        await api.categories.update(c.category_id, {
          name,
          rollover_type: type === 'savings' ? 'accumulate' : 'reset',
          category_group_id: groupId,
          is_essential: isEssential,
        });
        toast.success('Categoría actualizada');
      } else {
        await api.categories.create({
          name,
          category_group_id: groupId,
          rollover_type: type === 'savings' ? 'accumulate' : 'reset',
        });
        toast.success('Categoría creada');
      }
      await loadAndRender(container);
    },
  });

  if (isEdit) {
    modal.body.querySelector('#cf-delete-btn')?.addEventListener('click', async () => {
      const confirmed = confirm(`¿Eliminar "${c.category_name}"?\n\nSi tiene transacciones asociadas, quedarán sin categoría.`);
      if (!confirmed) return;
      try {
        await api.categories.delete(c.category_id);
        modal.close();
        toast.success('Categoría eliminada');
        await loadAndRender(container);
      } catch (err) {
        const d = err.detail;
        if (d?.transactions != null || d?.budgets != null) {
          const forceConfirmed = confirm(
            `Esta categoría tiene ${d.transactions ?? 0} transacción(es) y ${d.budgets ?? 0} mes(es) de presupuesto.\n\n¿Eliminar igualmente? Las transacciones quedarán sin categoría.`
          );
          if (forceConfirmed) {
            try {
              await api.categories.deleteForce(c.category_id);
              modal.close();
              toast.success('Categoría eliminada');
              await loadAndRender(container);
            } catch (e2) { toast.error(e2.message); }
          }
          return;
        }
        toast.error(err.message);
      }
    });
  }
}

function openCoverModal(cat, allCats, container) {
  const deficit   = Math.abs(cat.available ?? 0);
  const currency  = cat.currency_code ?? 'COP';
  const readyToAssign = _data?.ready_to_assign ?? 0;

  // Categories with positive available (exclude the target itself)
  const sources = allCats.filter(c => c.category_id !== cat.category_id && (c.available ?? 0) > 0);

  const sourcesHtml = [
    `<option value="__rta__">Listo para asignar (${fmtCurrency(readyToAssign, 'COP')})</option>`,
    ...sources.map(s => `<option value="${s.category_id}">${sanitize(s.category_name)} (disponible: ${fmtCurrency(s.available, 'COP')})</option>`),
  ].join('');

  openModal({
    title: `Cubrir exceso: ${cat.category_name}`,
    size: 'sm',
    content: `
      <p style="font-size:0.875rem;margin-bottom:16px">
        Exceso en <strong>${sanitize(cat.category_name)}</strong>:
        <span class="text-danger amount" style="font-weight:700">${fmtCurrency(deficit, currency)}</span>
      </p>
      <div class="form-group mb-3">
        <label class="form-label required">Tomar dinero de</label>
        <select id="cv-source">${sourcesHtml}</select>
      </div>
      <div class="form-group">
        <label class="form-label required">Monto a cubrir (${currency})</label>
        <input type="number" id="cv-amount" value="${currency === 'USD' ? deficit.toFixed(2) : Math.round(deficit)}" step="${currency === 'USD' ? '0.01' : '1000'}" min="0.01" autofocus>
      </div>
      <p id="cv-preview" class="text-soft" style="font-size:0.8rem;margin-top:4px"></p>
    `,
    submitLabel: 'Cubrir exceso',
    onSubmit: async (body) => {
      const sourceVal = body.querySelector('#cv-source').value;
      const amount    = parseFloat(body.querySelector('#cv-amount').value);
      if (isNaN(amount) || amount <= 0) throw new Error('Monto inválido');

      if (sourceVal === '__rta__') {
        // Tomar de listo para asignar → aumentar asignado de la categoría destino
        const currentAssigned = cat.assigned ?? 0;
        const newAssigned = currency === 'USD'
          ? (cat.assigned_native ?? currentAssigned / _rate) + amount
          : currentAssigned + amount;
        await api.budgets.update(_month, cat.category_id, { assigned: newAssigned, currency_code: currency });
      } else {
        await api.budgets.coverExcess({
          source_category_id: parseInt(sourceVal),
          target_category_id: cat.category_id,
          amount,
          currency_code: currency,
          month: _month + '-01',
        });
      }

      toast.success('Exceso cubierto');
      await loadAndRender(container);
    },
  });
}

function openGroupModal(group, container) {
  const isEdit = !!group;

  const modal = openModal({
    title: isEdit ? `Editar grupo: ${group.name}` : 'Nuevo Grupo',
    size: 'sm',
    content: `
      <div class="form-group mb-3">
        <label class="form-label required">Nombre del grupo</label>
        <input type="text" id="gf-name" value="${sanitize(group?.name ?? '')}" placeholder="Ej: Vivienda" autofocus>
      </div>
      ${!isEdit ? `
        <div class="form-group">
          <label class="form-label">Tipo</label>
          <select id="gf-income">
            <option value="false">Gastos / Ahorros</option>
            <option value="true">Ingresos</option>
          </select>
        </div>
      ` : ''}
      ${isEdit ? `
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--fin-surface-2)">
          <button class="btn btn-danger btn-sm w-full" id="gf-delete-btn">Eliminar grupo</button>
        </div>
      ` : ''}
    `,
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const name = body.querySelector('#gf-name').value.trim();
      if (!name) throw new Error('El nombre es obligatorio');

      if (isEdit) {
        await api.categories.updateGroup(group.id, { name });
        toast.success('Grupo actualizado');
      } else {
        const is_income = body.querySelector('#gf-income').value === 'true';
        await api.categories.createGroup({ name, is_income });
        toast.success('Grupo creado');
      }
      await loadAndRender(container);
    },
  });

  if (isEdit) {
    modal.body.querySelector('#gf-delete-btn')?.addEventListener('click', async () => {
      const catCount = (group.categories ?? []).length;
      const msg = catCount > 0
        ? `El grupo "${group.name}" tiene ${catCount} categoría(s).\n\n¿Eliminar el grupo y todas sus categorías? Las transacciones quedarán sin categoría.`
        : `¿Eliminar el grupo "${group.name}"?`;
      if (!confirm(msg)) return;
      try {
        await api.categories.deleteGroup(group.id, catCount > 0);
        modal.close();
        toast.success('Grupo eliminado');
        await loadAndRender(container);
      } catch (err) {
        toast.error(err.message);
      }
    });
  }
}
