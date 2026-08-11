import * as api from '../api/client.js';
import { fmtCurrency, sanitize, currentMonth, prevMonth, nextMonth, fmtMonthLabel, optional, progressBar, progressPct } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';
import { loadingState, showError } from '../components/pageState.js';

export const title = 'Presupuesto';

let _month = currentMonth();
let _data  = null;
let _cats  = [];
let _accounts = [];
let _rate  = 4200; // COP per 1 USD
let _loadToken = 0; // ignore stale responses when switching months quickly

const DEBT_ACCOUNT_TYPES = new Set(['credit_card', 'credit_loan', 'mortgage']);

export async function mount(container) {
  container.innerHTML = loadingState();
  await loadAndRender(container);
}

async function loadAndRender(container) {
  const token = ++_loadToken;
  const monthRequested = _month;
  try {
    const [budgetData, cats, rateData, accounts] = await Promise.all([
      api.budgets.month(monthRequested),
      api.categories.list(),
      optional(api.exchangeRates.current(), null, 'Tasa de Cambio'),
      optional(api.accounts.list(), [], 'Cuentas'),
    ]);
    // Stale response: user already navigated to another month
    if (token !== _loadToken) return;
    _data = budgetData;
    _cats = cats;
    if (rateData?.rate) _rate = rateData.rate;
    _accounts = accounts ?? [];
    renderPage(container);
  } catch (err) {
    if (token !== _loadToken) return;
    showError(container, {
      title: 'Presupuesto',
      message: err.message,
      onRetry: () => {
        container.innerHTML = loadingState();
        loadAndRender(container);
      },
    });
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

// Accounts that count as "money in accounts" for Listo para asignar:
// open, is_budget=True, and not a debt account (credit card / loan / mortgage).
function budgetAccounts() {
  return (_accounts ?? []).filter(a =>
    a.is_budget && !a.is_closed && !DEBT_ACCOUNT_TYPES.has(a.type)
  );
}

function accountsDiagram() {
  const accs = budgetAccounts();
  if (!accs.length) return '';

  const byCurrency = {};
  for (const a of accs) {
    const code = a.currency?.code ?? 'COP';
    (byCurrency[code] ??= []).push(a);
  }
  const codes = Object.keys(byCurrency).sort((a, b) => (a === 'COP' ? -1 : b === 'COP' ? 1 : a.localeCompare(b)));

  const columns = codes.map(code => {
    const list = byCurrency[code];
    const subtotal = list.reduce((s, a) => s + (a.balance ?? 0), 0);
    const rows = list.map(a => `
      <div class="account-list-row">
        <span class="account-list-name">${sanitize(a.name)}</span>
        <span class="account-list-balance ${a.balance < 0 ? 'text-danger' : ''}">${fmtCurrency(a.balance ?? 0, code)}</span>
      </div>
    `).join('');
    return `
      <div class="account-list-col">
        <div class="account-list-col-header">Cuentas en ${code}</div>
        ${rows}
        <div class="account-list-row account-list-subtotal">
          <span class="account-list-name">Subtotal ${code}</span>
          <span class="account-list-balance">${fmtCurrency(subtotal, code)}</span>
        </div>
      </div>
    `;
  }).join('');

  const totalCop = accs.reduce((s, a) => {
    const code = a.currency?.code ?? 'COP';
    const bal = a.balance ?? 0;
    return s + (code === 'USD' ? bal * _rate : bal);
  }, 0);

  return `
    <div class="account-state-group">
      <div class="account-state-group-label">
        Cuentas de presupuesto
        <span class="info-tooltip" tabindex="0" aria-label="Explicación de Cuentas de presupuesto">
          &#9432;
          <span class="tooltip-text">
            Cuentas que suman en "Listo para asignar": abiertas, incluidas en presupuesto, sin contar tarjetas de crédito, préstamos ni hipoteca. Separadas por moneda porque cada una vive en su propia cuenta (COP o USD).
          </span>
        </span>
      </div>
      <div class="account-list-columns">${columns}</div>
      <div class="account-list-row account-list-total">
        <span class="account-list-name">Total (equivalente COP)</span>
        <span class="account-list-balance">${fmtCurrency(totalCop, 'COP')}</span>
      </div>
      <div class="account-list-row account-list-total">
        <span class="account-list-name">Total (equivalente USD)</span>
        <span class="account-list-balance">${fmtCurrency(totalCop / _rate, 'USD')}</span>
      </div>
    </div>
  `;
}

function renderPage(container) {
  const cats = flattenBudgetCats(_data);
  const expCats    = cats.filter(c => c.category_type !== 'income');
  const savCats    = cats.filter(c => c.category_type === 'savings');
  const incomeCats = cats.filter(c => c.category_type === 'income');

  const totalIncome      = incomeCats.reduce((s, c) => s + (c.spent ?? 0), 0);
  const totalAssigned    = expCats.reduce((s, c) => s + (c.assigned ?? 0), 0);
  const totalSpent       = expCats.reduce((s, c) => s + (c.spent    ?? 0), 0);
  const totalAvailable   = expCats.reduce((s, c) => s + (c.available ?? 0), 0);
  const totalSavings     = savCats.reduce((s, c) => s + (c.available ?? 0), 0);
  const readyToAssign    = _data?.ready_to_assign ?? 0;
  const monthLeftover    = totalAssigned - totalSpent;   // este mes: asignado - gastado
  const unassignedIncome = totalIncome - totalAssigned;  // este mes: ingresos sin destino todavía

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

    <div class="money-tree mb-4">
      <div class="tree-tier">
        <div class="tree-node tree-node-root">
          <span class="tree-node-label">
            Ingresos de este mes
            <span class="info-tooltip" tabindex="0" aria-label="Explicación de Ingresos">
              &#9432;
              <span class="tooltip-text">
                Suma de las <strong>transacciones reales</strong> registradas en ${fmtMonthLabel(_month).toLowerCase()} en categorías de tipo ingreso.<br><br>
                No es lo que "definiste" o planeaste ganar (eso es el <em>asignado</em> de la categoría ingreso) — es lo que realmente entró y quedó registrado como transacción este mes.
              </span>
            </span>
          </span>
          <span class="tree-node-value text-success">${fmtCurrency(totalIncome, 'COP')}</span>
          <span class="tree-node-sub">${fmtCurrency(totalIncome / _rate, 'USD')}</span>
        </div>
      </div>

      <div class="tree-connector">
        <div class="tree-connector-line"></div>
      </div>

      <div class="tree-branch tree-branch-wide">
        <div class="tree-branch-hline"></div>
        <div class="tree-branch-children">

          <div class="tree-child">
            <div class="tree-vline"></div>
            <div class="tree-node tree-node-primary tree-node-assigned">
              <span class="tree-node-label">
                Asignado
                <span class="info-tooltip" tabindex="0" aria-label="Explicación de Asignado">
                  &#9432;
                  <span class="tooltip-text">Cuánto de tus ingresos ya tiene un destino (categoría) este mes.</span>
                </span>
              </span>
              <span class="tree-node-value">${fmtCurrency(totalAssigned, 'COP')}</span>
              <span class="tree-node-sub">${fmtCurrency(totalAssigned / _rate, 'USD')}</span>
            </div>

            <div class="tree-connector tree-connector-sm">
              <div class="tree-connector-line"></div>
            </div>

            <div class="tree-branch">
              <div class="tree-branch-hline"></div>
              <div class="tree-branch-children">
                <div class="tree-child">
                  <div class="tree-vline"></div>
                  <div class="tree-node tree-node-leaf tree-node-spent">
                    <span class="tree-node-label">
                      Gastado
                      <span class="info-tooltip" tabindex="0" aria-label="Explicación de Gastado">
                        &#9432;
                        <span class="tooltip-text">De lo asignado, cuánto ya se gastó este mes.</span>
                      </span>
                    </span>
                    <span class="tree-node-value text-danger">${fmtCurrency(totalSpent, 'COP')}</span>
                    <span class="tree-node-sub">${fmtCurrency(totalSpent / _rate, 'USD')}</span>
                  </div>
                </div>
                <div class="tree-child">
                  <div class="tree-vline"></div>
                  <div class="tree-node tree-node-leaf tree-node-remaining">
                    <span class="tree-node-label">
                      Falta por gastar
                      <span class="info-tooltip" tabindex="0" aria-label="Explicación de Falta por gastar">
                        &#9432;
                        <span class="tooltip-text">
                          Lo que queda de lo asignado este mes, sin gastar todavía.<br><br>
                          <strong>= Asignado − Gastado</strong>
                        </span>
                      </span>
                    </span>
                    <span class="tree-node-value ${monthLeftover >= 0 ? 'text-success' : 'text-danger'}">${fmtCurrency(monthLeftover, 'COP')}</span>
                    <span class="tree-node-sub">${fmtCurrency(monthLeftover / _rate, 'USD')}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="tree-child">
            <div class="tree-vline"></div>
            <div class="tree-node tree-node-primary ${unassignedIncome < 0 ? 'tree-node-overassigned' : 'tree-node-unassigned'}">
              <span class="tree-node-label">
                Sin asignar (este mes)
                <span class="info-tooltip" tabindex="0" aria-label="Explicación de Sin asignar">
                  &#9432;
                  <span class="tooltip-text">
                    De los ingresos de ${fmtMonthLabel(_month).toLowerCase()}, cuánto todavía no tiene una categoría destino.<br><br>
                    <strong>= Ingresos de este mes − Asignado este mes</strong><br><br>
                    Es distinto de <em>"Listo para asignar"</em> (abajo): este número solo mira el flujo del mes; "Listo para asignar" mira el saldo acumulado de todas tus cuentas de presupuesto contra todo lo disponible acumulado en el presupuesto. Pueden dar valores diferentes.
                  </span>
                </span>
              </span>
              <span class="tree-node-value ${unassignedIncome < 0 ? 'text-danger' : ''}">${fmtCurrency(unassignedIncome, 'COP')}</span>
              <span class="tree-node-sub">
                ${unassignedIncome < 0
                  ? `Asignaste ${fmtCurrency(Math.abs(unassignedIncome), 'COP')} de más`
                  : fmtCurrency(unassignedIncome / _rate, 'USD')}
              </span>
              ${unassignedIncome > readyToAssign
                ? `<span class="tree-node-note text-warning" style="display:block;font-size:0.72rem;margin-top:4px">
                    ⚠ Sin asignar supera a "Listo para asignar": hay categorías en rojo que se deben cubrir con este dinero.
                  </span>`
                : ''}
            </div>
          </div>

        </div>
      </div>
    </div>

    <div class="account-state mb-4">
      <div class="account-state-label">
        Estado acumulado (todos los meses, no solo ${fmtMonthLabel(_month).toLowerCase()})
      </div>

      <div class="account-state-group">
        <div class="account-state-group-label">
          Dinero ya asignado a una categoría
          <span class="info-tooltip" tabindex="0" aria-label="Explicación">
            &#9432;
            <span class="tooltip-text">
              Este dinero ya tiene un destino. No es lo mismo que "Listo para asignar" →, que es dinero sin destino todavía.
            </span>
          </span>
        </div>
        <div class="account-state-row">
          <div class="stat-chip">
            <span class="stat-chip-label">
              Disponible acumulado
              <span class="info-tooltip" tabindex="0" aria-label="Explicación de Disponible acumulado">
                &#9432;
                <span class="tooltip-text">
                  Suma del disponible de todas las categorías (gasto y ahorro), incluyendo lo que quedó de meses anteriores. Es la versión acumulada de "Disponible este mes" ↑, sumando también meses pasados.
                </span>
              </span>
            </span>
            <span class="stat-chip-value amount ${totalAvailable >= 0 ? 'text-success' : 'text-danger'}">
              ${fmtCurrency(totalAvailable, 'COP')}
            </span>
            <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(totalAvailable / _rate, 'USD')}</span>
          </div>
          <div class="stat-chip">
            <span class="stat-chip-label">
              Ahorros acumulados
              <span class="info-tooltip" tabindex="0" aria-label="Explicación de Ahorros acumulados">
                &#9432;
                <span class="tooltip-text">Parte del "Disponible acumulado" que está en categorías de tipo ahorro (dinero guardado, no de gasto mensual).</span>
              </span>
            </span>
            <span class="stat-chip-value amount" style="color:var(--fin-accent)">${fmtCurrency(totalSavings, 'COP')}</span>
            <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(totalSavings / _rate, 'USD')}</span>
          </div>
        </div>
      </div>

      <div class="account-state-group account-state-group-alert">
        <div class="account-state-group-label">
          Dinero SIN asignar a ninguna categoría
          <span class="info-tooltip" tabindex="0" aria-label="Explicación">
            &#9432;
            <span class="tooltip-text">
              Este dinero está en tus cuentas pero no está dentro de ninguna categoría — a diferencia de "Disponible acumulado" ←, que sí está categorizado.
            </span>
          </span>
        </div>
        <div class="account-state-row">
          <div class="stat-chip stat-chip-highlight" style="border-color:${readyToAssign >= 0 ? 'var(--fin-success)' : 'var(--fin-danger)'}">
            <span class="stat-chip-label">
              Listo para asignar
              <span class="info-tooltip" tabindex="0" aria-label="Explicación de Listo para asignar">
                &#9432;
                <span class="tooltip-text">
                  Dinero que tienes pero aún no has asignado a ninguna categoría.<br><br>
                  <strong>= Saldo en cuentas de presupuesto (hoy) − Disponible acumulado en presupuesto (a hoy, incluye ahorros y lo no gastado)</strong><br><br>
                  Siempre se calcula contra el mes actual real, aunque estés navegando otro mes en esta pantalla.<br><br>
                  Positivo: hay dinero sin categorizar, puedes asignarlo.<br>
                  Negativo: asignaste más de lo que tienes en cuentas.<br>
                  Ideal: $0 (cada peso tiene un destino).<br><br>
                  Es distinto de <em>"Sin asignar (este mes)"</em> ↑ arriba: ese número solo compara ingresos vs. asignado dentro del mes que estás viendo; este compara el saldo total de tus cuentas contra el disponible acumulado de hoy.
                </span>
              </span>
            </span>
            <span class="stat-chip-value amount ${readyToAssign >= 0 ? 'text-success' : 'text-danger'}">
              ${fmtCurrency(readyToAssign, 'COP')}
            </span>
            <span class="text-soft" style="font-size:0.75rem">${fmtCurrency(readyToAssign / _rate, 'USD')}</span>
          </div>
        </div>
      </div>

      ${accountsDiagram()}
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width:21%">Categoría</th>
            <th class="td-right" style="width:12%">Asignado<br><small class="text-soft" style="font-weight:400">COP / USD</small></th>
            <th class="td-right" style="width:8%">% del ingreso</th>
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
          ${Object.entries(groups).map(([grp, list]) => groupRows(grp, list, totalIncome)).join('')}
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

  // Edit/delete "Cubierto" movements
  container.querySelectorAll('[data-edit-covered]').forEach(el => {
    const cat = cats.find(c => c.category_id === parseInt(el.dataset.editCovered));
    el.addEventListener('click', () => openCoveredModal(cat, cats, container));
  });

  // Drag & drop category rows onto a group header to move them
  let draggedCatId = null;
  container.querySelectorAll('[data-drag-cat]').forEach(row => {
    row.addEventListener('dragstart', (e) => {
      draggedCatId = parseInt(row.dataset.dragCat);
      e.dataTransfer.effectAllowed = 'move';
      row.style.opacity = '0.4';
    });
    row.addEventListener('dragend', () => {
      row.style.opacity = '';
      draggedCatId = null;
    });
  });
  container.querySelectorAll('[data-drop-group]').forEach(header => {
    header.addEventListener('dragover', (e) => {
      if (draggedCatId == null) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      header.style.outline = '2px dashed var(--fin-accent)';
      header.style.outlineOffset = '-2px';
    });
    header.addEventListener('dragleave', () => {
      header.style.outline = '';
    });
    header.addEventListener('drop', async (e) => {
      e.preventDefault();
      header.style.outline = '';
      const groupId = parseInt(header.dataset.dropGroup);
      const cat = cats.find(c => c.category_id === draggedCatId);
      if (!cat || !groupId || cat.group_id === groupId) return;
      try {
        await api.categories.update(draggedCatId, { category_group_id: groupId });
        toast.success('Categoría movida de grupo');
        await loadAndRender(container);
      } catch (err) {
        toast.error(err.message);
      }
    });
  });
}

const GROUP_ACCENTS = ['#316342','#BA1A1A','#735142','#3B5B66','#6B4226','#4C6B3F','#8A5A44','#7A6A53'];
let _isFirstGroup = true;
let _groupIndex   = 0;

function groupRows(group, cats, totalIncomeAll) {
  const grpId       = cats[0]?.group_id ?? '';
  const grpName     = sanitize(group || 'Sin grupo');
  const isIncomeGroup = cats[0]?.category_type === 'income';
  const totAssigned  = cats.reduce((s, c) => s + (c.assigned  ?? 0), 0);
  const totSpent     = cats.reduce((s, c) => s + (c.spent     ?? 0), 0);
  const totAvailable = cats.reduce((s, c) => s + (c.available ?? 0), 0);
  const totCovered   = cats.reduce((s, c) => s + (c.covered   ?? 0), 0);

  const accent      = GROUP_ACCENTS[_groupIndex % GROUP_ACCENTS.length];
  _groupIndex++;

  if (isIncomeGroup) {
    const spacer = _isFirstGroup ? '' : `<tr><td colspan="8" style="height:20px;padding:0;border:none;background:transparent"></td></tr>`;
    _isFirstGroup = false;
    const header = `
      ${spacer}
      <tr class="budget-group-header" data-drop-group="${grpId}" style="background:var(--fin-surface-2)">
        <td colspan="8" style="padding:0;border:none">
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
            <span style="font-size:0.72rem;font-weight:800;text-transform:uppercase;letter-spacing:0.09em;color:${accent};${grpId ? 'cursor:pointer' : ''}"
              ${grpId ? `data-edit-group="${grpId}" title="Editar grupo"` : ''}>${grpName}</span>
            <span style="font-size:0.72rem;font-weight:700;color:var(--fin-ink-3);font-variant-numeric:tabular-nums">${fmtCurrency(totAssigned,'COP')}</span>
          </div>
        </td>
      </tr>`;
    const rows = cats.map(c => incomeCategoryRow(c, accent)).join('');
    return header + rows;
  }

  const pct         = progressPct(totSpent, totAssigned);
  const pctColor    = pct >= 100 ? '#BA1A1A' : pct >= 80 ? '#735142' : '#2F6B4F';
  const pctLabel    = totAssigned > 0 ? `${Math.round(pct)}%` : '—';
  const availSign   = totAvailable >= 0 ? '+' : '';
  const availColor  = totAvailable >= 0 ? '#2F6B4F' : '#BA1A1A';

  const coveredSign  = totCovered >= 0 ? '+' : '';
  const coveredColor = totCovered > 0 ? '#3B5B66' : totCovered < 0 ? '#735142' : 'var(--fin-ink-3)';

  const spacer = _isFirstGroup ? '' : `<tr><td colspan="8" style="height:20px;padding:0;border:none;background:transparent"></td></tr>`;
  _isFirstGroup = false;

  const groupPct = totalIncomeAll > 0 ? (totAssigned / totalIncomeAll) * 100 : 0;
  const groupPctLabel = totalIncomeAll > 0 ? `${groupPct.toFixed(1)}%` : '—';

  const header = `
    ${spacer}
    <tr class="budget-group-header" data-drop-group="${grpId}" style="background:var(--fin-surface-2)">
      <td colspan="8" style="padding:0;border:none">
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
            ${totalIncomeAll > 0 ? `<span style="font-size:0.72rem;font-weight:700;color:var(--fin-ink-3);font-variant-numeric:tabular-nums" title="% de los ingresos de este mes">${groupPctLabel} del ingreso</span>` : ''}
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
  const rows = cats.map(c => categoryRow(c, accent, totalIncomeAll)).join('');
  return header + rows;
}

function incomeCategoryRow(c, groupAccent = 'var(--fin-border)') {
  const assigned        = c.assigned        ?? 0;
  const assigned_native = c.assigned_native ?? null;
  const currency_code   = c.currency_code   ?? 'COP';

  return `
    <tr draggable="true" data-drag-cat="${c.category_id}" style="cursor:grab">
      <td style="font-size:0.8125rem;font-weight:500;padding-left:28px;border-left:3px solid ${groupAccent}33">
        <span style="opacity:0.35;margin-right:6px;font-size:0.7rem" title="Arrastra para mover de grupo">⠿</span>${sanitize(c.category_name)}
      </td>
      <td class="td-right td-mono" style="cursor:pointer;font-size:0.8125rem;line-height:1.4" data-edit-assigned="${c.category_id}" data-month="${_month}">
        ${fmtDual(assigned, currency_code, assigned_native)}
      </td>
      <td colspan="5"></td>
      <td style="white-space:nowrap">
        <button class="btn btn-ghost btn-xs" data-edit-cat="${c.category_id}" title="Editar categoría (nombre, grupo, tipo)">✎ Editar</button>
      </td>
    </tr>`;
}

function categoryRow(c, groupAccent = 'var(--fin-border)', totalIncomeAll = 0) {
  const assigned        = c.assigned        ?? 0;
  const assigned_native = c.assigned_native ?? null;
  const currency_code   = c.currency_code   ?? 'COP';
  const spent           = c.spent           ?? 0;
  const available       = c.available       ?? 0;
  const covered         = c.covered         ?? 0;
  const initial_amount  = c.initial_amount  ?? 0;
  const isSavings       = c.category_type   === 'savings';

  const shareOfTotal    = totalIncomeAll > 0 ? (assigned / totalIncomeAll) * 100 : 0;
  const shareLabel      = totalIncomeAll > 0 && assigned > 0 ? `${shareOfTotal.toFixed(1)}%` : '—';

  const assignedHtml = isSavings && initial_amount > 0
    ? `${fmtDual(assigned, currency_code, assigned_native)}<br><small class="amount" style="color:var(--fin-accent);font-size:0.68rem;white-space:nowrap">+ ${fmtCurrency(initial_amount, 'COP')} guardado</small>`
    : fmtDual(assigned, currency_code, assigned_native);

  const availClass = available >= 0 ? 'text-success' : 'text-danger';

  const pct      = progressPct(spent, assigned);
  const pctColor = pct >= 100 ? '#BA1A1A' : pct >= 80 ? '#735142' : '#2F6B4F';
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
    ? `<span style="color:${covered > 0 ? '#3B5B66' : '#735142'};font-weight:600">${coveredSign}${fmtDual(covered)}</span>`
    : `<span class="td-soft">—</span>`;

  return `
    <tr draggable="true" data-drag-cat="${c.category_id}" style="cursor:grab">
      <td style="font-size:0.8125rem;font-weight:500;padding-left:28px;border-left:3px solid ${groupAccent}33">
        <span style="opacity:0.35;margin-right:6px;font-size:0.7rem" title="Arrastra para mover de grupo">⠿</span>${sanitize(c.category_name)}
        ${isSavings ? '<span class="badge badge-accent" style="margin-left:6px;font-size:0.6rem">Ahorro</span>' : ''}
      </td>
      <td class="td-right td-mono" style="cursor:pointer;font-size:0.8125rem;line-height:1.4" data-edit-assigned="${c.category_id}" data-month="${_month}">
        ${assignedHtml}
      </td>
      <td class="td-right td-mono td-soft" style="font-size:0.75rem;line-height:1.4" title="% de los ingresos de este mes">${shareLabel}</td>
      <td class="td-right td-mono td-soft" style="font-size:0.8125rem;line-height:1.4">${fmtDual(spent)}</td>
      <td class="td-right td-mono" style="font-size:0.8125rem;line-height:1.4${covered !== 0 ? ';cursor:pointer' : ''}" ${covered !== 0 ? `data-edit-covered="${c.category_id}"` : ''}>${coveredHtml}</td>
      <td class="td-right td-mono ${availClass}" style="font-size:0.8125rem;line-height:1.4">
        ${fmtDual(available)}
      </td>
      <td style="padding-right:12px">${usoCel}</td>
      <td style="white-space:nowrap">
        ${coverBtn}<button class="btn btn-ghost btn-xs" data-edit-cat="${c.category_id}" title="Editar categoría (nombre, grupo, tipo)">✎ Editar</button>
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
            <input type="number" id="ma-initial" value="${currentCurrency === 'USD' ? initialNative.toFixed(2) : Math.round(initialNative)}" step="${currentCurrency === 'USD' ? '0.01' : '1000'}">
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
        if (isNaN(initial)) throw new Error('Monto acumulado inválido');
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

  const initialInput   = isSavings ? modal.body.querySelector('#ma-initial') : null;
  const initialPreview = isSavings ? modal.body.querySelector('#ma-initial-preview') : null;
  const initialLabel   = isSavings ? modal.body.querySelector('#ma-initial')?.closest('.form-group')?.querySelector('.form-label') : null;

  function updateInitialPreview() {
    if (!initialInput || !initialPreview) return;
    const amt = parseFloat(initialInput.value) || 0;
    initialPreview.textContent = curSelect.value === 'COP'
      ? `≈ ${fmtCurrency(amt / _rate, 'USD')}`
      : `≈ ${fmtCurrency(amt * _rate, 'COP')}`;
  }
  if (initialInput && initialPreview) {
    updateInitialPreview();
    initialInput.addEventListener('input', updateInitialPreview);
  }

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

    if (initialInput) {
      const initialAmt = parseFloat(initialInput.value) || 0;
      if (curSelect.value === 'USD') {
        initialInput.value = (initialAmt / _rate).toFixed(2);
        initialInput.step  = '0.01';
      } else {
        initialInput.value = Math.round(initialAmt * _rate);
        initialInput.step  = '1000';
      }
      if (initialLabel) initialLabel.textContent = `Monto (${curSelect.value})`;
      updateInitialPreview();
    }
  });
}

function openCategoryModal(cat, container) {
  const isEdit = !!cat;
  const c = cat ?? {};
  const allGroups = _data?.groups ?? [];
  const expenseGroups = allGroups.filter(g => !g.is_income);
  const incomeGroups  = allGroups.filter(g => g.is_income);
  const initialType = c.category_type === 'income' ? 'income' : (c.category_type === 'savings' ? 'savings' : 'expense');

  const groupOptionsFor = (type) => {
    const list = type === 'income' ? incomeGroups : expenseGroups;
    if (!list.length) return '<option value="">(crea primero un grupo)</option>';
    return list.map(g => `<option value="${g.id}" ${g.id === c.group_id ? 'selected' : ''}>${sanitize(g.name)}</option>`).join('');
  };

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
            <option value="expense" ${initialType === 'expense' ? 'selected' : ''}>Gasto</option>
            <option value="savings" ${initialType === 'savings' ? 'selected' : ''}>Ahorro (acumula)</option>
            <option value="income" ${initialType === 'income' ? 'selected' : ''}>Ingreso</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Grupo</label>
          <select id="cf-group">
            ${groupOptionsFor(initialType)}
          </select>
        </div>
      </div>
      <div class="form-group mt-3" id="cf-essential-wrap" ${initialType === 'income' ? 'style="display:none"' : ''}>
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
      if (isNaN(groupId)) throw new Error('Selecciona un grupo (crea uno de tipo ingreso primero si vas a crear una categoría de ingreso)');

      if (isEdit) {
        await api.categories.update(c.category_id, {
          name,
          rollover_type: type === 'savings' ? 'accumulate' : 'reset',
          category_group_id: groupId,
          is_essential: type === 'income' ? false : isEssential,
        });
        toast.success('Categoría actualizada');
      } else {
        await api.categories.create({
          name,
          category_group_id: groupId,
          rollover_type: type === 'savings' ? 'accumulate' : 'reset',
          is_essential: type === 'income' ? false : isEssential,
        });
        toast.success('Categoría creada');
      }
      await loadAndRender(container);
    },
  });

  const typeSelect = modal.body.querySelector('#cf-type');
  const groupSelect = modal.body.querySelector('#cf-group');
  const essentialWrap = modal.body.querySelector('#cf-essential-wrap');
  typeSelect.addEventListener('change', () => {
    const type = typeSelect.value;
    groupSelect.innerHTML = groupOptionsFor(type);
    essentialWrap.style.display = type === 'income' ? 'none' : '';
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
  const currency  = cat.currency_code ?? 'COP';
  // cat.available is always COP-equivalent; cat.available_native is in the
  // category's own currency and must be used for USD categories.
  const deficit   = Math.abs(currency === 'USD' ? (cat.available_native ?? (cat.available ?? 0) / _rate) : (cat.available ?? 0));
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

async function openCoveredModal(cat, allCats, container) {
  const [year, month] = _month.split('-').map(Number);
  const startDate = `${_month}-01`;
  const lastDay = new Date(year, month, 0).getDate();
  const endDate = `${_month}-${String(lastDay).padStart(2, '0')}`;

  let txs = [];
  try {
    const all = await api.transactions.list({ category_id: cat.category_id, start_date: startDate, end_date: endDate });
    txs = (all ?? []).filter(t => t.is_adjustment && t.memo &&
      (t.memo.startsWith('Cubrir exceso:') || t.memo.startsWith('Cubierto desde:')));
  } catch (err) {
    toast.error(err.message);
    return;
  }

  if (txs.length === 0) {
    toast.error('No se encontraron movimientos de cobertura para este mes');
    return;
  }

  const rowsHtml = txs.map(t => {
    const isReceived = t.memo.startsWith('Cubierto desde:');
    const counterpart = t.memo.slice(t.memo.indexOf(':') + 1).trim();
    const currencyCode = t.currency?.code ?? t.currency_code ?? 'COP';
    const sentence = isReceived
      ? `Recibió <strong>${fmtCurrency(Math.abs(t.amount), currencyCode)}</strong> de <strong>${sanitize(counterpart)}</strong> para cubrir su déficit`
      : `Envió <strong>${fmtCurrency(Math.abs(t.amount), currencyCode)}</strong> a <strong>${sanitize(counterpart)}</strong> para cubrir su déficit`;
    return `
    <div class="flex-row" style="justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--fin-border)">
      <div>
        <div style="font-size:0.8125rem">${sentence}</div>
        <div class="text-soft" style="font-size:0.7rem">${sanitize(t.date)}</div>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
        <button class="btn btn-xs" data-cv-edit="${t.id}" title="Editar monto">✎</button>
        <button class="btn btn-xs" data-cv-delete="${t.id}" title="Eliminar movimiento" style="background:var(--fin-danger);color:#fff;opacity:0.85">✕</button>
      </div>
    </div>`;
  }).join('');

  const modal = openModal({
    title: `Cobertura: ${sanitize(cat.category_name)}`,
    size: 'sm',
    content: `<div id="cv-list">${rowsHtml}</div>`,
  });

  const root = modal.body;

  root.querySelectorAll('[data-cv-edit]').forEach(btn => {
    btn.addEventListener('click', () => {
      const tx = txs.find(t => t.id === parseInt(btn.dataset.cvEdit));
      openEditCoverModal(cat, tx, allCats, container, modal);
    });
  });

  root.querySelectorAll('[data-cv-delete]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('¿Eliminar este movimiento de cobertura? Se eliminará también su contraparte.')) return;
      try {
        await api.transactions.delete(parseInt(btn.dataset.cvDelete), { delete_pair: true });
        toast.success('Movimiento eliminado');
        modal.close?.();
        await loadAndRender(container);
      } catch (err) {
        toast.error(err.message);
      }
    });
  });
}

function openEditCoverModal(cat, tx, allCats, container, parentModal) {
  const isReceived = tx.memo.startsWith('Cubierto desde:');
  const counterpartName = tx.memo.slice(tx.memo.indexOf(':') + 1).trim();
  const counterpart = allCats.find(c => c.category_name === counterpartName);
  const currencyCode = tx.currency?.code ?? tx.currency_code ?? 'COP';

  const otherCats = allCats.filter(c => c.category_id !== cat.category_id);
  const optionsHtml = otherCats.map(c =>
    `<option value="${c.category_id}" ${c.category_id === counterpart?.category_id ? 'selected' : ''}>${sanitize(c.category_name)}</option>`
  ).join('');

  const modal = openModal({
    title: 'Editar cobertura',
    size: 'sm',
    content: `
      <p style="font-size:0.8125rem;margin-bottom:16px" class="text-soft">
        ${isReceived ? 'Categoría que recibe' : 'Categoría que cubre'}: <strong>${sanitize(cat.category_name)}</strong>
      </p>
      <div class="form-group mb-3">
        <label class="form-label required">Monto</label>
        <input type="number" id="ec-amount" value="${Math.abs(tx.amount)}" step="0.01" min="0.01" autofocus>
      </div>
      <div class="form-group mb-3">
        <label class="form-label required">Moneda</label>
        <select id="ec-currency">
          <option value="COP" ${currencyCode === 'COP' ? 'selected' : ''}>COP</option>
          <option value="USD" ${currencyCode === 'USD' ? 'selected' : ''}>USD</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label required">${isReceived ? 'Categoría de origen' : 'Categoría de destino'}</label>
        <select id="ec-counterpart">${optionsHtml}</select>
      </div>
    `,
    submitLabel: 'Guardar',
    onSubmit: async (body) => {
      const amount = parseFloat(body.querySelector('#ec-amount').value);
      const currency_code = body.querySelector('#ec-currency').value;
      const counterpart_category_id = parseInt(body.querySelector('#ec-counterpart').value);
      if (isNaN(amount) || amount <= 0) throw new Error('Monto inválido');

      await api.budgets.updateCoverExcess(tx.id, { counterpart_category_id, amount, currency_code });

      toast.success('Cobertura actualizada');
      parentModal.close();
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
