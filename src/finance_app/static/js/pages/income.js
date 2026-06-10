import * as api from '../api/client.js';
import { sanitize, todayISO, optional } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Ingresos';

const MONTH_NAMES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                     'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
const FREQ_LABELS = { daily:'Diaria', weekly:'Semanal', biweekly:'Quincenal', monthly:'Mensual', yearly:'Anual' };

function fmt(v, code = 'COP') {
  return new Intl.NumberFormat('es-CO', { style:'currency', currency:code, maximumFractionDigits:0 }).format(v ?? 0);
}

// Module-level meta cache (accounts, categories, currencies)
let _accounts = [], _categories = [], _currencies = [], _incomeCats = [];

async function loadMeta() {
  [_accounts, _categories, _currencies] = await Promise.all([
    optional(api.accounts.list(), [], 'Cuentas'),
    optional(api.categories.list(), [], 'Categorías'),
    optional(api.currencies.list(), [], 'Monedas'),
  ]);
  // Income categories: prefer is_income flag, fall back to group name heuristic
  _incomeCats = _categories.filter(c =>
    c.is_income || c.category_group_is_income ||
    (c.category_group_name ?? '').toLowerCase().includes('ingreso') ||
    (c.category_group_name ?? '').toLowerCase().includes('income')
  );
  if (_incomeCats.length === 0) _incomeCats = _categories; // last resort
}

export async function mount(container) {
  const today = new Date();
  let year  = today.getFullYear();
  let month = today.getMonth() + 1;

  async function load() {
    container.innerHTML = skeleton();
    const monthStr = `${year}-${String(month).padStart(2, '0')}`;

    try {
      if (_accounts.length === 0) await loadMeta();

      const [incomeData, trendData, recurring, savingsRate] = await Promise.all([
        api.reports.income({ month: monthStr }),
        api.reports.budgetIncomeExpenses({ months: 6 }),
        optional(api.recurring.list(), [], 'Recurrentes'),
        optional(api.reports.savingsRate({ months: 12 }), null, 'Tasa de Ahorro'),
      ]);

      const incomeSources = (Array.isArray(recurring) ? recurring : [])
        .filter(r => r.transaction_type === 'income');

      container.innerHTML = renderPage(incomeData, trendData, incomeSources, year, month, savingsRate);
      renderChart(container, trendData);
      renderSavingsRateChart(container, savingsRate);
      bindEvents(container, incomeSources);
    } catch (err) {
      container.innerHTML = `<div class="alert alert-danger">Error: ${sanitize(err.message)}</div>`;
    }
  }

  function bindEvents(el, incomeSources) {
    el.querySelector('#inc-prev')?.addEventListener('click', () => {
      month--; if (month < 1) { month = 12; year--; }
      load();
    });
    el.querySelector('#inc-next')?.addEventListener('click', () => {
      month++; if (month > 12) { month = 1; year++; }
      load();
    });

    el.querySelector('#btn-add-income')?.addEventListener('click', () => openAddIncomeModal(load));
    el.querySelector('#btn-add-recurring')?.addEventListener('click', () => openRecurringModal(null, load));

    el.querySelectorAll('[data-rec-edit]').forEach(btn => {
      const rec = incomeSources.find(r => r.id === parseInt(btn.dataset.recEdit));
      btn.addEventListener('click', () => openRecurringModal(rec, load));
    });

    el.querySelectorAll('[data-rec-toggle]').forEach(btn => {
      const id = parseInt(btn.dataset.recToggle);
      const isActive = btn.dataset.recActive === 'true';
      btn.addEventListener('click', async () => {
        try {
          await api.recurring.update(id, { is_active: !isActive });
          toast.success(isActive ? 'Fuente desactivada' : 'Fuente activada');
          load();
        } catch (err) { toast.error(err.message); }
      });
    });

    el.querySelectorAll('[data-rec-delete]').forEach(btn => {
      const id = parseInt(btn.dataset.recDelete);
      btn.addEventListener('click', async () => {
        if (!confirm('¿Eliminar esta fuente recurrente?')) return;
        try {
          await api.recurring.delete(id);
          toast.success('Fuente eliminada');
          load();
        } catch (err) { toast.error(err.message); }
      });
    });
  }

  load();
}

// ─── Page render ─────────────────────────────────────────────────────────────

function renderPage(incomeData, trendData, incomeSources, year, month, savingsRateData) {
  const totalActual    = incomeData?.total_income ?? 0;
  const bySource       = incomeData?.by_source ?? [];
  const monthlyData    = trendData?.months ?? [];
  const thisMonth      = monthlyData.find(m => m.month === `${year}-${String(month).padStart(2,'0')}`);

  const totalExpenses  = thisMonth?.expenses ?? 0;
  const savings        = totalActual - totalExpenses;
  const savingsRate    = totalActual > 0 ? (savings / totalActual * 100) : 0;

  const active   = incomeSources.filter(r => r.is_active !== false);
  const inactive = incomeSources.filter(r => r.is_active === false);
  const totalProjected = active.reduce((s, r) => s + (r.amount ?? 0), 0);
  const diffProjected  = totalActual - totalProjected;

  const isCurrentMonth = new Date().getFullYear() === year && (new Date().getMonth() + 1) === month;

  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1 class="page-title">Ingresos</h1>
        <p class="page-subtitle">Seguimiento y gestión de ingresos</p>
      </div>
      <div class="page-header-actions">
        <button id="btn-add-income" class="btn btn-primary btn-sm">+ Registrar ingreso</button>
      </div>
    </div>

    <div class="flex items-center gap-3 mb-3">
      <button id="inc-prev" class="btn btn-ghost btn-sm">←</button>
      <h2 style="margin:0;font-size:18px;font-weight:600">${MONTH_NAMES[month-1]} ${year}</h2>
      <button id="inc-next" class="btn btn-ghost btn-sm" ${isCurrentMonth ? 'disabled' : ''}>→</button>
    </div>

    <div class="kpi-grid mb-4">
      <div class="kpi-card">
        <div class="kpi-label">Proyectado</div>
        <div class="kpi-value">${fmt(totalProjected)}</div>
        <div class="kpi-sub">${active.length} fuente${active.length !== 1 ? 's' : ''} activa${active.length !== 1 ? 's' : ''}</div>
      </div>
      <div class="kpi-card ${totalActual > 0 ? 'positive' : ''}">
        <div class="kpi-label">Recibido</div>
        <div class="kpi-value">${fmt(totalActual)}</div>
        <div class="kpi-sub" style="color:${diffProjected >= 0 ? 'var(--fin-success)' : 'var(--fin-danger)'}">
          ${diffProjected >= 0 ? '▲' : '▼'} ${fmt(Math.abs(diffProjected))} vs proyectado
        </div>
      </div>
      <div class="kpi-card ${savings >= 0 ? 'positive' : 'danger'}">
        <div class="kpi-label">Ahorro del mes</div>
        <div class="kpi-value">${fmt(savings)}</div>
        <div class="kpi-sub">Ingresos menos gastos</div>
      </div>
      <div class="kpi-card ${savingsRate >= 20 ? 'positive' : savingsRate >= 10 ? '' : 'danger'}">
        <div class="kpi-label">Tasa de ahorro</div>
        <div class="kpi-value">${savingsRate.toFixed(1)}%</div>
        <div class="kpi-sub">${savingsRate >= 20 ? '✓ Excelente' : savingsRate >= 10 ? '~ Aceptable' : '⚠ Por mejorar'}</div>
      </div>
    </div>

    <div class="section-grid cols-2 mb-4">
      <div class="card">
        <div class="card-header"><h3 class="card-title">Ingresos del mes por categoría</h3></div>
        ${bySource.length === 0
          ? `<div class="empty-state"><p>Sin ingresos registrados este mes</p></div>`
          : `<div style="overflow-x:auto"><table class="fin-table">
              <thead><tr><th>Categoría</th><th class="td-right">Monto</th><th class="td-right">%</th></tr></thead>
              <tbody>
                ${bySource.map(row => `
                  <tr>
                    <td>${sanitize(row.category_name)}</td>
                    <td class="td-right text-success"><span class="amount">${fmt(row.amount)}</span></td>
                    <td class="td-right text-muted" style="font-size:12px">
                      ${totalActual > 0 ? (row.amount / totalActual * 100).toFixed(1) + '%' : '—'}
                    </td>
                  </tr>`).join('')}
              </tbody>
            </table></div>`
        }
      </div>

      <div class="card">
        <div class="card-header flex items-center justify-between">
          <h3 class="card-title">Fuentes recurrentes</h3>
          <button id="btn-add-recurring" class="btn btn-primary btn-sm">+ Agregar fuente</button>
        </div>
        ${active.length === 0
          ? `<div class="empty-state"><p>No hay fuentes activas. Agrega nómina, freelance u otras.</p></div>`
          : `<div style="overflow-x:auto"><table class="fin-table">
              <thead><tr><th>Fuente</th><th>Frecuencia</th><th class="td-right">Monto</th><th style="width:80px"></th></tr></thead>
              <tbody>${active.map(r => recurringRow(r, true)).join('')}</tbody>
            </table></div>`
        }
        ${inactive.length > 0 ? `
          <details style="border-top:1px solid var(--fin-border);padding:8px 16px 12px">
            <summary class="text-muted" style="cursor:pointer;font-size:0.75rem">
              Inactivas (${inactive.length})
            </summary>
            <table class="fin-table mt-2">
              <tbody>${inactive.map(r => recurringRow(r, false)).join('')}</tbody>
            </table>
          </details>` : ''}
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header"><h3 class="card-title">Últimos 6 meses — Ingresos vs Gastos</h3></div>
      <div class="card-body"><canvas id="incomeChart" style="width:100%;height:260px"></canvas></div>
    </div>

    ${savingsRateSection(savingsRateData)}
  `;
}

function recurringRow(r, isActive) {
  const code = r.currency?.code ?? 'COP';
  return `
    <tr style="${isActive ? '' : 'opacity:0.5'}">
      <td class="text-soft" style="font-weight:500">${sanitize(r.description ?? r.name ?? '—')}</td>
      <td class="text-muted" style="font-size:0.78rem">${FREQ_LABELS[r.frequency] ?? r.frequency ?? '—'}</td>
      <td class="td-right text-success"><span class="amount">+${fmt(r.amount ?? 0, code)}</span></td>
      <td class="td-right" style="white-space:nowrap">
        <button class="btn btn-ghost btn-xs" data-rec-edit="${r.id}" title="Editar">✏</button>
        <button class="btn btn-ghost btn-xs" data-rec-toggle="${r.id}" data-rec-active="${isActive}"
          title="${isActive ? 'Desactivar' : 'Activar'}"
          style="color:${isActive ? 'var(--fin-ink-3)' : 'var(--fin-success)'}">${isActive ? '⏸' : '▶'}</button>
        <button class="btn btn-ghost btn-xs text-danger" data-rec-delete="${r.id}" title="Eliminar">✕</button>
      </td>
    </tr>`;
}

// ─── Modals ───────────────────────────────────────────────────────────────────

function openAddIncomeModal(reload) {
  const catOptions = buildIncomeCatOptions();
  const accOptions = _accounts.map(a =>
    `<option value="${a.id}">${sanitize(a.name)}</option>`
  ).join('');
  const curOptions = _currencies.map(c =>
    `<option value="${c.id}" ${c.code === 'COP' ? 'selected' : ''}>${c.code}</option>`
  ).join('');

  openModal({
    title: 'Registrar ingreso',
    content: `
      <div class="form-group" style="margin-bottom:14px">
        <label class="form-label required">Fecha</label>
        <input type="date" id="ai-date" value="${todayISO()}">
      </div>
      <div class="form-row cols-2" style="margin-bottom:14px">
        <div class="form-group">
          <label class="form-label required">Monto</label>
          <input type="number" id="ai-amount" placeholder="0" step="0.01" min="0">
        </div>
        <div class="form-group">
          <label class="form-label">Moneda</label>
          <select id="ai-currency">${curOptions}</select>
        </div>
      </div>
      <div class="form-group" style="margin-bottom:14px">
        <label class="form-label required">Cuenta</label>
        <select id="ai-account">
          <option value="">— seleccionar —</option>
          ${accOptions}
        </select>
      </div>
      <div class="form-group" style="margin-bottom:14px">
        <label class="form-label required">Categoría de ingreso</label>
        <select id="ai-category">
          <option value="">— seleccionar —</option>
          ${catOptions}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Descripción (opcional)</label>
        <input type="text" id="ai-desc" placeholder="Ej: Nómina mayo, Freelance proyecto X">
      </div>
    `,
    submitLabel: 'Registrar',
    onSubmit: async (body) => {
      const date_val  = body.querySelector('#ai-date').value;
      const amount    = parseFloat(body.querySelector('#ai-amount').value);
      const accountId = parseInt(body.querySelector('#ai-account').value);
      const catId     = parseInt(body.querySelector('#ai-category').value);
      const currId    = parseInt(body.querySelector('#ai-currency').value) || undefined;
      const desc      = body.querySelector('#ai-desc').value.trim();

      if (!date_val)         throw new Error('La fecha es obligatoria');
      if (!amount || amount <= 0) throw new Error('El monto debe ser mayor a 0');
      if (!accountId)        throw new Error('La cuenta es obligatoria');
      if (!catId)            throw new Error('La categoría es obligatoria');

      await api.transactions.create({
        date:        date_val,
        amount,
        account_id:  accountId,
        category_id: catId,
        currency_id: currId,
        description: desc || undefined,
      });

      toast.success('Ingreso registrado');
      reload();
    },
  });
}

function openRecurringModal(rec, reload) {
  const isEdit = !!rec;
  const catOptions = buildIncomeCatOptions(rec?.category_id);
  const accOptions = _accounts.map(a =>
    `<option value="${a.id}" ${rec?.account_id == a.id ? 'selected' : ''}>${sanitize(a.name)}</option>`
  ).join('');
  const curOptions = _currencies.map(c =>
    `<option value="${c.id}" ${(rec?.currency?.id == c.id) || (!rec?.currency && c.code === 'COP') ? 'selected' : ''}>${c.code}</option>`
  ).join('');

  const freqs = ['daily','weekly','biweekly','monthly','yearly'];

  openModal({
    title: isEdit ? `Editar: ${rec.description ?? rec.name}` : 'Nueva fuente de ingreso',
    content: `
      <div class="form-group" style="margin-bottom:14px">
        <label class="form-label required">Nombre</label>
        <input type="text" id="rf-name" value="${sanitize(rec?.description ?? rec?.name ?? '')}"
          placeholder="Ej: Nómina, Freelance, Arriendo">
      </div>
      <div class="form-row cols-2" style="margin-bottom:14px">
        <div class="form-group">
          <label class="form-label required">Monto</label>
          <input type="number" id="rf-amount" value="${rec?.amount ?? ''}" step="0.01" min="0">
        </div>
        <div class="form-group">
          <label class="form-label">Moneda</label>
          <select id="rf-currency">${curOptions}</select>
        </div>
      </div>
      <div class="form-row cols-2" style="margin-bottom:14px">
        <div class="form-group">
          <label class="form-label required">Cuenta</label>
          <select id="rf-account">
            <option value="">— seleccionar —</option>
            ${accOptions}
          </select>
        </div>
        <div class="form-group">
          <label class="form-label required">Frecuencia</label>
          <select id="rf-freq">
            ${freqs.map(f => `<option value="${f}" ${rec?.frequency === f ? 'selected' : ''}>${FREQ_LABELS[f]}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-group" style="margin-bottom:14px">
        <label class="form-label required">Categoría de ingreso</label>
        <select id="rf-category">
          <option value="">— seleccionar —</option>
          ${catOptions}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">${isEdit ? 'Fecha de inicio' : 'Primera ocurrencia'}</label>
        <input type="date" id="rf-next" value="${rec?.next_occurrence_date ?? rec?.start_date ?? todayISO()}">
      </div>
    `,
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const data = {
        description:      body.querySelector('#rf-name').value.trim(),
        transaction_type: 'income',
        frequency:        body.querySelector('#rf-freq').value,
        amount:           parseFloat(body.querySelector('#rf-amount').value),
        currency_id:      parseInt(body.querySelector('#rf-currency').value) || undefined,
        account_id:       parseInt(body.querySelector('#rf-account').value) || undefined,
        category_id:      parseInt(body.querySelector('#rf-category').value) || undefined,
        start_date:       body.querySelector('#rf-next').value || undefined,
      };

      if (!data.description)            throw new Error('El nombre es obligatorio');
      if (!data.amount || data.amount <= 0) throw new Error('El monto debe ser mayor a 0');
      if (!data.account_id)             throw new Error('La cuenta es obligatoria');
      if (!data.category_id)            throw new Error('La categoría es obligatoria');

      if (isEdit) {
        await api.recurring.update(rec.id, data);
        toast.success('Fuente actualizada');
      } else {
        await api.recurring.create(data);
        toast.success('Fuente creada');
      }
      reload();
    },
  });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildIncomeCatOptions(selectedId) {
  const cats = _incomeCats.length > 0 ? _incomeCats : _categories;
  const groups = {};
  cats.forEach(c => {
    const k = c.category_group_name || 'Ingresos';
    if (!groups[k]) groups[k] = [];
    groups[k].push(c);
  });
  return Object.entries(groups).map(([k, cs]) =>
    `<optgroup label="${sanitize(k)}">${cs.map(c =>
      `<option value="${c.id}" ${selectedId == c.id ? 'selected' : ''}>${sanitize(c.name)}</option>`
    ).join('')}</optgroup>`
  ).join('');
}

// ─── Charts ───────────────────────────────────────────────────────────────────

function renderChart(container, trendData) {
  const canvas = container.querySelector('#incomeChart');
  if (!canvas || !trendData?.months?.length) return;

  const months  = trendData.months.slice(-6);
  const labels  = months.map(m => m.month_name ?? m.month);
  const income  = months.map(m => m.income ?? 0);
  const expense = months.map(m => m.expenses ?? 0);
  const fmtCOP  = v => new Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', maximumFractionDigits:0 }).format(v);

  loadChart(Chart => new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label:'Ingresos', data:income,  backgroundColor:'var(--fin-success)', borderRadius:4 },
        { label:'Gastos',   data:expense, backgroundColor:'var(--fin-danger)', borderRadius:4 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode:'index', intersect:false },
      plugins: {
        legend: { labels:{ color:'var(--fin-ink-2)', font:{ size:12 } } },
        tooltip: { callbacks:{ label: ctx => `${ctx.dataset.label}: ${fmtCOP(ctx.raw)}` } },
      },
      scales: {
        x: { ticks:{ color:'var(--fin-ink-2)', font:{ size:11 } }, grid:{ display:false } },
        y: {
          ticks: {
            color:'var(--fin-ink-2)', font:{ size:11 },
            callback: v => new Intl.NumberFormat('es-CO', { notation:'compact', currency:'COP', style:'currency', maximumFractionDigits:0 }).format(v),
          },
          grid: { color:'var(--fin-border)' },
        },
      },
    },
  }));
}

function savingsRateSection(sr) {
  if (!sr?.monthly?.length) return '';
  const savedTarget = parseInt(localStorage.getItem('savings_rate_target') ?? '20', 10);
  const avg = sr.average_savings_rate ?? 0;

  return `
    <div class="card mt-4">
      <div class="card-header">
        <h3 class="card-title">Tasa de Ahorro — Histórico</h3>
        <div class="flex items-center gap-1">
          <label class="text-muted" style="font-size:0.78rem">Meta:</label>
          <input type="number" id="sr-target" value="${savedTarget}" min="0" max="100" step="1"
            class="input-field" style="width:60px;padding:3px 6px;font-size:0.78rem">
          <span class="text-muted" style="font-size:0.78rem">%</span>
        </div>
      </div>
      <div class="card-body"><canvas id="savingsRateChart" style="width:100%;height:220px"></canvas></div>
      <div class="card-body flex" style="flex-wrap:wrap;gap:12px;padding-top:0">
        <div class="text-muted" style="font-size:0.8rem">
          Promedio (${sr.monthly.length} meses):
          <strong class="${avg >= savedTarget ? 'amount text-success' : 'amount text-danger'}" style="margin-left:4px">${avg.toFixed(1)}%</strong>
        </div>
        <div class="text-muted" style="font-size:0.8rem">
          Meta: <strong style="margin-left:4px">${savedTarget}%</strong>
          ${avg >= savedTarget
            ? '<span class="text-success" style="font-size:0.75rem;margin-left:4px">✓ Cumplida</span>'
            : '<span class="text-danger" style="font-size:0.75rem;margin-left:4px">⚠ Por debajo</span>'}
        </div>
      </div>
    </div>`;
}

function renderSavingsRateChart(container, sr) {
  if (!sr?.monthly?.length) return;
  const canvas = container.querySelector('#savingsRateChart');
  if (!canvas) return;
  const targetInput = container.querySelector('#sr-target');

  loadChart(Chart => {
    const labels = sr.monthly.map(m => m.month_name ?? m.month);
    const rates  = sr.monthly.map(m => m.savings_rate ?? 0);
    const target = parseInt(targetInput?.value ?? '20', 10);

    const ch = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Tasa de ahorro',
            data: rates,
            borderColor: 'var(--fin-success)',
            backgroundColor: 'rgba(34,197,94,0.1)',
            borderWidth: 2,
            pointRadius: 4,
            fill: true,
            tension: 0.3,
          },
          {
            label: `Meta (${target}%)`,
            data: labels.map(() => target),
            borderColor: 'var(--fin-amber)',
            borderDash: [6, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { labels:{ color:'var(--fin-ink-2)', font:{ size:11 } } },
          tooltip: { callbacks:{ label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } },
        },
        scales: {
          y: { ticks:{ callback: v => v+'%', color:'var(--fin-ink-2)', font:{ size:10 } }, grid:{ color:'var(--fin-border)' }, beginAtZero:true },
          x: { ticks:{ color:'var(--fin-ink-2)', font:{ size:10 } }, grid:{ display:false } },
        },
      },
    });

    targetInput?.addEventListener('change', () => {
      const v = parseInt(targetInput.value, 10);
      localStorage.setItem('savings_rate_target', v);
      ch.data.datasets[1].data  = labels.map(() => v);
      ch.data.datasets[1].label = `Meta (${v}%)`;
      ch.update();
    });
  });
}

function loadChart(cb) {
  if (window.Chart) { cb(window.Chart); return; }
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js';
  s.onload = () => cb(window.Chart);
  document.head.appendChild(s);
}

function skeleton() {
  return `
    <div class="page-header"><div class="skeleton" style="height:26px;width:160px"></div></div>
    <div class="flex gap-2 mb-3">
      <div class="skeleton" style="height:32px;width:80px"></div>
    </div>
    <div class="kpi-grid">
      ${[0,1,2,3].map(() => `<div class="kpi-card"><div class="skeleton" style="height:60px"></div></div>`).join('')}
    </div>
    <div class="card mt-4"><div class="skeleton" style="height:280px;margin:16px"></div></div>
  `;
}
