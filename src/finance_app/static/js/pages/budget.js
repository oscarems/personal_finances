import * as api from '../api/client.js';
import { fmtCurrency, sanitize, currentMonth, prevMonth, nextMonth, fmtMonthLabel } from '../utils.js';
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
      api.exchangeRates.current().catch(() => null),
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
    return `${fmtCurrency(usdVal, 'USD')}<br><small style="color:var(--text-soft);font-size:0.7rem">≈ ${fmtCurrency(amount_cop, 'COP')}</small>`;
  }
  const usd = amount_cop / _rate;
  return `${fmtCurrency(amount_cop, 'COP')}<br><small style="color:var(--text-soft);font-size:0.7rem">≈ ${fmtCurrency(usd, 'USD')}</small>`;
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

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Presupuesto</h1>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-ghost btn-sm" id="btnAddGroup">+ Grupo</button>
        <button class="btn btn-secondary btn-sm" id="btnAddCategory">+ Categoría</button>
        <button class="btn btn-primary btn-sm" id="btnInitMonth">Inicializar mes</button>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
      <div class="month-nav">
        <button class="btn btn-ghost btn-sm" id="btnPrevMonth">‹ Anterior</button>
        <span class="month-nav-label">${fmtMonthLabel(_month)}</span>
        <button class="btn btn-ghost btn-sm" id="btnNextMonth">Siguiente ›</button>
      </div>
    </div>

    <div class="stat-row" style="margin-bottom:20px">
      <div class="stat-chip">
        <span class="stat-chip-label">Asignado</span>
        <span class="stat-chip-value">${fmtCurrency(totalAssigned, 'COP')}</span>
        <span style="color:var(--text-soft)" style="font-size:0.75rem">${fmtCurrency(totalAssigned / _rate, 'USD')}</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip-label">Gastado</span>
        <span class="stat-chip-value" style="color:var(--color-danger)">${fmtCurrency(totalSpent, 'COP')}</span>
        <span style="color:var(--text-soft)" style="font-size:0.75rem">${fmtCurrency(totalSpent / _rate, 'USD')}</span>
      </div>
      <div class="stat-chip">
        <span class="stat-chip-label">Disponible</span>
        <span class="stat-chip-value" style="color:${totalAvailable >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}">
          ${fmtCurrency(totalAvailable, 'COP')}
        </span>
        <span style="color:var(--text-soft)" style="font-size:0.75rem">${fmtCurrency(totalAvailable / _rate, 'USD')}</span>
      </div>
      ${totalSavings > 0 ? `
        <div class="stat-chip">
          <span class="stat-chip-label">Ahorros acumulados</span>
          <span class="stat-chip-value" style="color:var(--color-accent)">${fmtCurrency(totalSavings, 'COP')}</span>
          <span style="color:var(--text-soft)" style="font-size:0.75rem">${fmtCurrency(totalSavings / _rate, 'USD')}</span>
        </div>` : ''}
      <div class="stat-chip" style="border-color:${readyToAssign >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}">
        <span class="stat-chip-label">Listo para asignar</span>
        <span class="stat-chip-value" style="color:${readyToAssign >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}">
          ${fmtCurrency(readyToAssign, 'COP')}
        </span>
        <span style="color:var(--text-soft);font-size:0.75rem">${fmtCurrency(readyToAssign / _rate, 'USD')}</span>
      </div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width:34%">Categoría</th>
            <th style="text-align:right;width:16%">Asignado<br><small style="color:var(--text-soft)" style="font-weight:400">COP / USD</small></th>
            <th style="text-align:right;width:16%">Gastado<br><small style="color:var(--text-soft)" style="font-weight:400">COP / USD</small></th>
            <th style="text-align:right;width:16%">Disponible<br><small style="color:var(--text-soft)" style="font-weight:400">COP / USD</small></th>
            <th style="width:13%">Uso</th>
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
}

function groupRows(group, cats) {
  const grpId      = cats[0]?.group_id ?? '';
  const grpName    = sanitize(group || 'Sin grupo');
  const totAssigned  = cats.reduce((s, c) => s + (c.assigned  ?? 0), 0);
  const totSpent     = cats.reduce((s, c) => s + (c.spent     ?? 0), 0);
  const totAvailable = cats.reduce((s, c) => s + (c.available ?? 0), 0);

  const availColor = totAvailable >= 0 ? 'var(--color-success)' : 'var(--color-danger)';

  const header = `
    <tr style="background:var(--bg-surface-muted)">
      <td style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);padding:8px 16px">
        <span ${grpId ? `data-edit-group="${grpId}" style="cursor:pointer;border-bottom:1px dashed var(--border-subtle)" title="Editar grupo"` : ''}>${grpName}</span>
      </td>
      <td class="td-right td-mono" style="font-size:0.72rem;font-weight:700;color:var(--text-soft);padding:8px 4px">${fmtCurrency(totAssigned, 'COP')}</td>
      <td class="td-right td-mono" style="font-size:0.72rem;font-weight:700;color:var(--text-soft);padding:8px 4px">${fmtCurrency(totSpent, 'COP')}</td>
      <td class="td-right td-mono" style="font-size:0.72rem;font-weight:700;color:${availColor};padding:8px 4px">${fmtCurrency(totAvailable, 'COP')}</td>
      <td colspan="2"></td>
    </tr>`;
  const rows = cats.map(c => categoryRow(c)).join('');
  return header + rows;
}

function categoryRow(c) {
  const assigned        = c.assigned        ?? 0;
  const assigned_native = c.assigned_native ?? null;
  const currency_code   = c.currency_code   ?? 'COP';
  const spent           = c.spent           ?? 0;
  const available       = c.available       ?? 0;
  const initial_amount  = c.initial_amount  ?? 0;
  const isSavings       = c.category_type   === 'savings';

  const pct = assigned > 0 ? Math.min(100, (spent / assigned) * 100) : 0;
  const fillClass = pct >= 100 ? 'danger' : pct >= 80 ? 'warning' : 'ok';

  const assignedHtml = isSavings && initial_amount > 0
    ? `${fmtDual(assigned, currency_code, assigned_native)}<br><small style="color:var(--color-accent);font-size:0.68rem;white-space:nowrap">+ ${fmtCurrency(initial_amount, 'COP')} guardado</small>`
    : fmtDual(assigned, currency_code, assigned_native);

  return `
    <tr>
      <td style="font-size:0.8125rem;font-weight:500">
        ${sanitize(c.category_name)}
        ${isSavings ? '<span class="badge badge-accent" style="margin-left:6px;font-size:0.6rem">Ahorro</span>' : ''}
      </td>
      <td class="td-right td-mono" style="cursor:pointer;font-size:0.8125rem;line-height:1.4" data-edit-assigned="${c.category_id}" data-month="${_month}">
        ${assignedHtml}
      </td>
      <td class="td-right td-mono td-soft" style="font-size:0.8125rem;line-height:1.4">${fmtDual(spent)}</td>
      <td class="td-right td-mono" style="font-size:0.8125rem;line-height:1.4;color:${available >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}">
        ${fmtDual(available)}
      </td>
      <td>
        <div class="progress-wrap" style="min-width:60px">
          <div class="progress-fill ${fillClass}" style="width:${pct}%"></div>
        </div>
      </td>
      <td>
        <button class="btn btn-ghost btn-xs" data-edit-cat="${c.category_id}" title="Editar categoría">⋯</button>
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
  const initialCOP      = cat.initial_amount ?? 0;
  const spentCOP        = cat.spent ?? 0;
  const spentUSD        = spentCOP / _rate;

  const modal = openModal({
    title: `Asignar: ${cat.category_name}`,
    size: 'sm',
    content: `
      <p style="font-size:0.875rem;color:var(--text-secondary);margin-bottom:16px">
        Gastado: <strong>${fmtCurrency(spentCOP, 'COP')}</strong>
        <span style="color:var(--text-soft)">(≈ ${fmtCurrency(spentUSD, 'USD')})</span>
      </p>
      <div class="form-row cols-2" style="gap:12px">
        <div class="form-group" style="flex:2">
          <label class="form-label required">Asignado este mes</label>
          <input type="number" id="ma-amount" value="${currentCurrency === 'USD' ? currentAmount.toFixed(2) : Math.round(currentAmount)}" step="${currentCurrency === 'USD' ? '0.01' : '1000'}" autofocus>
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">Moneda</label>
          <select id="ma-currency">
            <option value="COP" ${currentCurrency === 'COP' ? 'selected' : ''}>COP</option>
            <option value="USD" ${currentCurrency === 'USD' ? 'selected' : ''}>USD</option>
          </select>
        </div>
      </div>
      <p id="ma-preview" style="font-size:0.8rem;color:var(--text-soft);margin-top:4px"></p>
      ${isSavings ? `
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border-subtle)">
          <p style="font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-soft);margin-bottom:10px">Ya ahorrado (acumulado anterior)</p>
          <div class="form-row cols-2" style="gap:12px">
            <div class="form-group" style="flex:2">
              <label class="form-label">Monto</label>
              <input type="number" id="ma-initial" value="${Math.round(initialCOP)}" step="1000" min="0">
            </div>
            <div class="form-group" style="flex:1">
              <label class="form-label">Moneda</label>
              <select id="ma-initial-currency">
                <option value="COP">COP</option>
                <option value="USD">USD</option>
              </select>
            </div>
          </div>
          <p id="ma-initial-preview" style="font-size:0.8rem;color:var(--text-soft);margin-top:4px"></p>
        </div>
      ` : ''}
    `,
    submitLabel: 'Guardar',
    onSubmit: async (body) => {
      const amount = parseFloat(body.querySelector('#ma-amount').value);
      const currency_code = body.querySelector('#ma-currency').value;
      if (isNaN(amount) || amount < 0) throw new Error('Monto inválido');

      if (isSavings) {
        const initial          = parseFloat(body.querySelector('#ma-initial').value);
        const initial_currency = body.querySelector('#ma-initial-currency').value;
        if (isNaN(initial) || initial < 0) throw new Error('Monto acumulado inválido');

        if (initial_currency === currency_code) {
          await api.budgets.update(_month, catId, { assigned: amount, currency_code, initial_amount: initial });
        } else {
          await api.budgets.update(_month, catId, { assigned: amount, currency_code });
          await api.budgets.setInitial(_month, catId, { initial_amount: initial, currency_code: initial_currency });
        }
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
    const initialCurSel  = modal.body.querySelector('#ma-initial-currency');
    const initialPreview = modal.body.querySelector('#ma-initial-preview');
    if (initialInput && initialCurSel && initialPreview) {
      const updateInitialPreview = () => {
        const amt = parseFloat(initialInput.value) || 0;
        initialPreview.textContent = initialCurSel.value === 'COP'
          ? `≈ ${fmtCurrency(amt / _rate, 'USD')}`
          : `≈ ${fmtCurrency(amt * _rate, 'COP')}`;
      };
      updateInitialPreview();
      initialInput.addEventListener('input', updateInitialPreview);
      initialCurSel.addEventListener('change', () => {
        const amt = parseFloat(initialInput.value) || 0;
        if (initialCurSel.value === 'USD') {
          initialInput.value = (amt / _rate).toFixed(2);
          initialInput.step  = '0.01';
        } else {
          initialInput.value = Math.round(amt * _rate);
          initialInput.step  = '1000';
        }
        updateInitialPreview();
      });
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
      <div class="form-group" style="margin-bottom:16px">
        <label class="form-label required">Nombre</label>
        <input type="text" id="cf-name" value="${sanitize(c.category_name ?? '')}" placeholder="Ej: Alimentación" autofocus>
      </div>
      <div class="form-row cols-2" style="gap:12px">
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
      ${isEdit ? `
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-subtle)">
          <button class="btn btn-danger btn-sm" id="cf-delete-btn" style="width:100%">Eliminar categoría</button>
        </div>
      ` : ''}
    `,
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const name = body.querySelector('#cf-name').value.trim();
      const type = body.querySelector('#cf-type').value;
      const groupId = parseInt(body.querySelector('#cf-group').value);
      if (!name) throw new Error('El nombre es obligatorio');
      if (isNaN(groupId)) throw new Error('Selecciona un grupo');

      if (isEdit) {
        await api.categories.update(c.category_id, {
          name,
          rollover_type: type === 'savings' ? 'accumulate' : 'reset',
          category_group_id: groupId,
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

function openGroupModal(group, container) {
  const isEdit = !!group;

  const modal = openModal({
    title: isEdit ? `Editar grupo: ${group.name}` : 'Nuevo Grupo',
    size: 'sm',
    content: `
      <div class="form-group" style="margin-bottom:16px">
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
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-subtle)">
          <button class="btn btn-danger btn-sm" id="gf-delete-btn" style="width:100%">Eliminar grupo</button>
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
