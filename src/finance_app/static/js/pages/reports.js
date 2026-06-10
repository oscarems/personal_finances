import * as api from '../api/client.js';
import { fmtCurrency, fmtNumber, sanitize, currentMonth, prevMonth, fmtMonthLabel, optional } from '../utils.js';

// Use shared palette when available, fall back to local list
function chartPalette(n) {
  const p = window.CHART_PALETTE;
  if (Array.isArray(p) && p.length) {
    const out = [];
    for (let i = 0; i < n; i++) out.push(p[i % p.length]);
    return out;
  }
  return LOCAL_COLORS.slice(0, n);
}

export const title = 'Reportes';

let _month = currentMonth();
let _chart = null;
let _incomeChart = null;
let _overtimeChart = null;
let _currencyId = 1;
let _currencyCode = 'COP';
let _currencies = [];
let _granularity = 'monthly';
let _otStartDate = '';
let _otEndDate = '';
let _selectedCategories = null; // null = top_n, Set = manual selection
let _availableCategories = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  _currencies = await optional(api.currencies.list(), [{ id: 1, code: 'COP' }, { id: 2, code: 'USD' }], 'Monedas');
  renderShell(container);
  await loadData(container);
}

export function cleanup() {
  _chart?.destroy();
  _chart = null;
  _incomeChart?.destroy();
  _incomeChart = null;
  _overtimeChart?.destroy();
  _overtimeChart = null;
  // Clean up the dropdown close listener if it was registered
  const filterEl = document.querySelector('#otCategoryFilter');
  if (filterEl?._closeMenuHandler) {
    document.removeEventListener('click', filterEl._closeMenuHandler);
  }
}

function renderShell(container) {
  const currencyOptions = _currencies.map(c =>
    `<option value="${c.id}" ${c.id === _currencyId ? 'selected' : ''}>${c.code}</option>`
  ).join('');

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text"><h1>Reportes</h1></div>
      <div class="page-header-actions flex items-center gap-3">
        <div class="flex items-center gap-1">
          <label class="text-muted" style="font-size:0.8rem">Moneda</label>
          <select id="rptCurrency" class="input-field" style="min-width:72px;padding:4px 8px;height:32px;font-size:0.8125rem">
            ${currencyOptions}
          </select>
        </div>
        <div class="month-nav">
          <button class="btn btn-ghost btn-sm" id="rptPrev">‹</button>
          <span class="month-nav-label" id="rptMonthLabel">${fmtMonthLabel(_month)}</span>
          <button class="btn btn-ghost btn-sm" id="rptNext">›</button>
        </div>
      </div>
    </div>
    <div class="kpi-grid" id="rpt-kpis"></div>
    <div class="section-grid cols-2 mb-4">
      <div class="card">
        <div class="card-header"><span class="card-title">Gasto por Categoría</span></div>
        <div class="card-body" style="height:280px;position:relative">
          <canvas id="spendChart"></canvas>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Ingresos vs Gastos</span></div>
        <div class="card-body" style="height:280px;position:relative">
          <canvas id="incomeChart"></canvas>
        </div>
      </div>
    </div>
    <div class="card" id="rpt-detail-card">
      <div class="card-header"><span class="card-title">Detalle por Categoría</span></div>
      <div class="card-body" id="rpt-detail"></div>
    </div>

    <div class="card mt-4">
      <div class="card-header" style="flex-wrap:wrap;gap:12px">
        <span class="card-title">Gasto por Categoría en el Tiempo</span>
        <div class="flex items-center gap-2" style="flex-wrap:wrap;margin-left:auto">
          <div class="tab-pills" id="granTabs">
            <button class="tab-pill ${_granularity === 'daily' ? 'active' : ''}" data-gran="daily">Diario</button>
            <button class="tab-pill ${_granularity === 'weekly' ? 'active' : ''}" data-gran="weekly">Semanal</button>
            <button class="tab-pill ${_granularity === 'monthly' ? 'active' : ''}" data-gran="monthly">Mensual</button>
          </div>
          <div class="flex items-center gap-1">
            <input type="date" id="otStartDate" class="input-field" style="height:32px;font-size:0.8125rem;padding:4px 8px" value="${_otStartDate}">
            <span class="text-muted" style="font-size:0.8rem">→</span>
            <input type="date" id="otEndDate" class="input-field" style="height:32px;font-size:0.8125rem;padding:4px 8px" value="${_otEndDate}">
          </div>
        </div>
      </div>
      <div class="card-body" style="padding-top:0;padding-bottom:0" id="otCategoryFilter"></div>
      <div class="card-body" style="height:320px;position:relative">
        <canvas id="overtimeChart"></canvas>
        <div id="overtimeEmpty" class="empty-state" style="display:none;position:absolute;inset:0"><p>Sin datos para el período</p></div>
        <div id="overtimeLoading" style="display:none;position:absolute;inset:0;align-items:center;justify-content:center;background:var(--fin-surface);opacity:0.7;border-radius:8px"><div class="spinner"></div></div>
      </div>
      <div class="card-body" style="padding-top:0" id="overtimeLegend"></div>
    </div>
  `;

  container.querySelector('#rptPrev').addEventListener('click', async () => {
    _month = prevMonth(_month);
    container.querySelector('#rptMonthLabel').textContent = fmtMonthLabel(_month);
    await loadData(container);
  });
  container.querySelector('#rptNext').addEventListener('click', async () => {
    const [y, m] = _month.split('-').map(Number);
    const next = new Date(y, m);
    _month = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`;
    container.querySelector('#rptMonthLabel').textContent = fmtMonthLabel(_month);
    await loadData(container);
  });
  container.querySelector('#rptCurrency').addEventListener('change', async (e) => {
    const selected = _currencies.find(c => c.id === parseInt(e.target.value));
    if (selected) {
      _currencyId = selected.id;
      _currencyCode = selected.code;
    }
    await loadData(container);
    await loadOvertimeData(container);
  });

  // Default overtime date range: current month
  if (!_otStartDate || !_otEndDate) {
    const [y, m] = _month.split('-').map(Number);
    _otStartDate = `${y}-${String(m).padStart(2, '0')}-01`;
    const lastDay = new Date(y, m, 0).getDate();
    _otEndDate = `${y}-${String(m).padStart(2, '0')}-${lastDay}`;
  }
  container.querySelector('#otStartDate').value = _otStartDate;
  container.querySelector('#otEndDate').value = _otEndDate;

  container.querySelector('#granTabs').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-gran]');
    if (!btn) return;
    _granularity = btn.dataset.gran;
    container.querySelectorAll('#granTabs .tab-pill').forEach(b => b.classList.toggle('active', b === btn));
    await loadOvertimeData(container);
  });

  container.querySelector('#otStartDate').addEventListener('change', async (e) => {
    _otStartDate = e.target.value;
    await loadOvertimeData(container);
  });
  container.querySelector('#otEndDate').addEventListener('change', async (e) => {
    _otEndDate = e.target.value;
    await loadOvertimeData(container);
  });

  loadOvertimeData(container);
}

async function loadData(container) {
  const kpisEl  = container.querySelector('#rpt-kpis');
  const detailEl= container.querySelector('#rpt-detail');
  if (kpisEl) kpisEl.innerHTML = '<div class="skeleton" style="height:80px;grid-column:1/-1"></div>';
  if (detailEl) detailEl.innerHTML = '<div class="page-loading" style="min-height:100px"><div class="spinner"></div></div>';

  try {
    const [spending, income] = await Promise.all([
      optional(api.reports.spending({ month: _month, currency_id: _currencyId }), null, 'Reporte de Gastos'),
      optional(api.reports.income({ month: _month, currency_id: _currencyId }), null, 'Reporte de Ingresos'),
    ]);

    const cats      = spending?.categories ?? spending?.by_category ?? [];
    const totalExp  = spending?.total ?? cats.reduce((s, c) => s + (c.spent ?? c.amount ?? 0), 0);
    const totalInc  = income?.total_income ?? income?.income ?? 0;
    const netFlow   = totalInc - totalExp;
    const saveRate  = totalInc > 0 ? (netFlow / totalInc) * 100 : 0;
    const fmt       = v => fmtCurrency(v, _currencyCode);

    if (kpisEl) {
      kpisEl.innerHTML = `
        <div class="kpi-card">
          <div class="kpi-label">Ingresos</div>
          <div class="kpi-value positive">${fmt(totalInc)}</div>
          <div class="kpi-sub">${_currencyCode} · ${fmtMonthLabel(_month)}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Gastos</div>
          <div class="kpi-value negative">${fmt(totalExp)}</div>
          <div class="kpi-sub">${_currencyCode} · ${fmtMonthLabel(_month)}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Flujo Neto</div>
          <div class="kpi-value ${netFlow >= 0 ? 'positive' : 'negative'}">${fmt(netFlow)}</div>
          <div class="kpi-sub">${_currencyCode} · ${fmtMonthLabel(_month)}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Tasa de Ahorro</div>
          <div class="kpi-value ${saveRate >= 20 ? 'positive' : saveRate >= 10 ? 'warning' : 'negative'}">${saveRate.toFixed(1)}%</div>
          <div class="kpi-sub">ingreso − gasto / ingreso</div>
        </div>
      `;
    }

    // Spending donut chart
    _chart?.destroy();
    const spendCtx = container.querySelector('#spendChart');
    if (spendCtx && cats.length) {
      const sorted = [...cats].sort((a, b) => (b.spent ?? b.amount ?? 0) - (a.spent ?? a.amount ?? 0)).slice(0, 10);
      const COLORS = chartPalette(sorted.length);
      _chart = new Chart(spendCtx, {
        type: 'doughnut',
        data: {
          labels: sorted.map(c => c.category_name ?? c.name),
          datasets: [{ data: sorted.map(c => c.spent ?? c.amount ?? 0), backgroundColor: COLORS, borderWidth: 2, borderColor: 'var(--fin-surface)' }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { position: 'right', labels: { font: { size: 11 }, color: 'var(--fin-ink-2)', padding: 12 } },
            tooltip: { callbacks: { label: (ctx) => ` ${fmt(ctx.raw)}` } },
          },
        },
      });
    }

    // Income vs Expenses bar chart
    _incomeChart?.destroy();
    const incomeCtx = container.querySelector('#incomeChart');
    if (incomeCtx) {
      _incomeChart = new Chart(incomeCtx, {
        type: 'bar',
        data: {
          labels: ['Ingresos', 'Gastos'],
          datasets: [{
            data: [totalInc, totalExp],
            backgroundColor: ['var(--fin-success)', 'var(--fin-danger)'],
            borderRadius: 6,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: 'var(--fin-border)' }, ticks: { callback: v => fmt(v), font: { size: 10 }, color: 'var(--fin-ink-3)' } },
            x: { grid: { display: false }, ticks: { color: 'var(--fin-ink-2)' } },
          },
        },
      });
    }

    if (detailEl) {
      const sorted = [...cats].sort((a, b) => (b.spent ?? b.amount ?? 0) - (a.spent ?? a.amount ?? 0));
      detailEl.innerHTML = sorted.length ? `
        <table class="fin-table">
          <thead>
            <tr>
              <th>Categoría</th>
              <th class="td-right">Gastado (${_currencyCode})</th>
              <th class="td-right">% del Total</th>
              <th style="width:25%">Distribución</th>
            </tr>
          </thead>
          <tbody>
            ${sorted.map(c => {
              const amt = c.spent ?? c.amount ?? 0;
              const pct = totalExp > 0 ? (amt / totalExp) * 100 : 0;
              return `
                <tr>
                  <td class="text-soft" style="font-weight:500">${sanitize(c.category_name ?? c.name ?? '—')}</td>
                  <td class="td-right"><span class="amount">${fmt(amt)}</span></td>
                  <td class="td-right text-muted">${pct.toFixed(1)}%</td>
                  <td>
                    <div class="progress-wrap" style="min-width:80px">
                      <div class="progress-fill ok" style="width:${pct}%"></div>
                    </div>
                  </td>
                </tr>`;
            }).join('')}
          </tbody>
        </table>
      ` : '<div class="empty-state"><p>Sin datos de gasto para este mes</p></div>';
    }
  } catch (err) {
    if (kpisEl) kpisEl.innerHTML = `<div class="alert alert-danger" style="grid-column:1/-1">${sanitize(err.message)}</div>`;
  }
}

const LOCAL_COLORS = [
  '#D97706','#059669','#0891B2','#7C3AED','#DB2777',
  '#EA580C','#65A30D','#0284C7','#9333EA','#E11D48',
  '#F59E0B','#10B981','#06B6D4','#8B5CF6','#EC4899',
];

function getColor(idx) {
  const p = window.CHART_PALETTE;
  const src = (Array.isArray(p) && p.length) ? p : LOCAL_COLORS;
  return src[idx % src.length];
}

function renderCategoryDropdown(container) {
  const el = container.querySelector('#otCategoryFilter');
  if (!el) return;

  if (!_availableCategories.length) {
    el.innerHTML = '';
    return;
  }

  const allSelected = _selectedCategories === null;
  const count = allSelected ? _availableCategories.length : _selectedCategories.size;
  const label = allSelected ? 'Todas las categorías' : `${count} categoría${count !== 1 ? 's' : ''} seleccionada${count !== 1 ? 's' : ''}`;

  el.innerHTML = `
    <div id="catDropdownWrap" style="position:relative;display:inline-block;padding:8px 0 4px">
      <button id="catDropdownBtn" class="btn btn-ghost btn-sm flex items-center gap-1" style="font-size:0.8rem">
        <span id="catDropdownLabel">${label}</span>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style="opacity:0.6;flex-shrink:0">
          <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <div id="catDropdownMenu" style="display:none;position:absolute;top:calc(100% + 4px);left:0;z-index:200;
           min-width:220px;max-height:280px;overflow-y:auto;
           background:var(--fin-surface-2);border:1px solid var(--fin-border);
           border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.4);padding:6px 0">
        <label class="flex items-center gap-2 text-muted"
               style="padding:7px 14px;cursor:pointer;font-size:0.8125rem;border-bottom:1px solid var(--fin-border);margin-bottom:4px"
               id="catSelectAll">
          <input type="checkbox" ${allSelected ? 'checked' : ''} style="accent-color:var(--fin-accent);width:14px;height:14px">
          <span class="text-soft" style="font-weight:500">Todas</span>
        </label>
        ${_availableCategories.map((cat, idx) => {
          const checked = !allSelected && _selectedCategories.has(cat);
          const color = getColor(idx);
          return `
            <label class="flex items-center gap-2 text-muted cat-dd-item"
                   style="padding:6px 14px;cursor:pointer;font-size:0.8125rem;transition:background 0.1s"
                   data-cat="${sanitize(cat)}"
                   onmouseover="this.style.background='var(--fin-surface)'" onmouseout="this.style.background=''">
              <input type="checkbox" ${checked ? 'checked' : ''} data-cat="${sanitize(cat)}"
                     style="accent-color:${color};width:14px;height:14px;flex-shrink:0">
              <span class="flex items-center gap-1">
                <span style="width:8px;height:8px;border-radius:2px;background:${color};flex-shrink:0"></span>
                ${sanitize(cat)}
              </span>
            </label>`;
        }).join('')}
      </div>
    </div>
  `;

  const btn = el.querySelector('#catDropdownBtn');
  const menu = el.querySelector('#catDropdownMenu');

  // Remove any previous close listener to avoid accumulation
  if (el._closeMenuHandler) {
    document.removeEventListener('click', el._closeMenuHandler);
  }

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = menu.style.display !== 'none';
    menu.style.display = open ? 'none' : 'block';
  });

  el._closeMenuHandler = (e) => {
    if (!el.contains(e.target)) {
      menu.style.display = 'none';
    }
  };
  document.addEventListener('click', el._closeMenuHandler);

  el.querySelector('#catSelectAll').querySelector('input').addEventListener('change', async () => {
    _selectedCategories = null;
    renderCategoryDropdown(container);
    await loadOvertimeChart(container);
  });

  el.querySelectorAll('.cat-dd-item input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', async () => {
      const cat = cb.dataset.cat;
      if (_selectedCategories === null) {
        _selectedCategories = new Set(_availableCategories);
      }
      if (cb.checked) {
        _selectedCategories.add(cat);
      } else {
        _selectedCategories.delete(cat);
        if (_selectedCategories.size === 0) _selectedCategories = null;
      }
      // Update label without closing dropdown
      const newCount = _selectedCategories === null ? _availableCategories.length : _selectedCategories.size;
      const newAll = _selectedCategories === null;
      el.querySelector('#catDropdownLabel').textContent = newAll
        ? 'Todas las categorías'
        : `${newCount} categoría${newCount !== 1 ? 's' : ''} seleccionada${newCount !== 1 ? 's' : ''}`;
      el.querySelector('#catSelectAll input').checked = newAll;
      await loadOvertimeChart(container);
    });
  });
}

async function loadOvertimeData(container) {
  const canvas = container.querySelector('#overtimeChart');
  if (!canvas) return;

  // First fetch all available categories (no filter) to populate chips
  try {
    const data = await api.reports.spendingOverTime({
      start_date: _otStartDate,
      end_date: _otEndDate,
      currency_id: _currencyId,
      granularity: _granularity,
      top_n: 50,
    });
    _availableCategories = data?.available_categories ?? [];
    // If this is first load or date range changed, reset selection
    if (_selectedCategories !== null) {
      // Keep only cats that still exist in the new range
      _selectedCategories = new Set([..._selectedCategories].filter(c => _availableCategories.includes(c)));
      if (_selectedCategories.size === 0) _selectedCategories = null;
    }
  } catch {
    _availableCategories = [];
  }

  renderCategoryDropdown(container);
  await loadOvertimeChart(container);
}

async function loadOvertimeChart(container) {
  const canvas = container.querySelector('#overtimeChart');
  const legendEl = container.querySelector('#overtimeLegend');
  const emptyEl = container.querySelector('#overtimeEmpty');
  const loadingEl = container.querySelector('#overtimeLoading');
  if (!canvas) return;

  const fmt = v => fmtCurrency(v, _currencyCode);

  if (emptyEl) emptyEl.style.display = 'none';
  if (loadingEl) loadingEl.style.display = 'flex';

  try {
    const params = {
      start_date: _otStartDate,
      end_date: _otEndDate,
      currency_id: _currencyId,
      granularity: _granularity,
    };
    if (_selectedCategories !== null && _selectedCategories.size > 0) {
      params.categories = [..._selectedCategories].join(',');
    } else if (_selectedCategories === null) {
      params.top_n = 8;
    }

    const data = await api.reports.spendingOverTime(params);

    _overtimeChart?.destroy();
    _overtimeChart = null;

    if (loadingEl) loadingEl.style.display = 'none';

    const hasData = data?.series?.some(s => s.data.some(v => v > 0));
    if (!data?.series?.length || !data?.months?.length || !hasData) {
      if (emptyEl) { emptyEl.style.display = 'flex'; }
      if (legendEl) legendEl.innerHTML = '';
      return;
    }

    const isDaily = _granularity === 'daily';

    const datasets = data.series.map((s, i) => {
      const colorIdx = _availableCategories.indexOf(s.category);
      const color = CHART_COLORS[(colorIdx >= 0 ? colorIdx : i) % CHART_COLORS.length];
      return {
        label: s.category,
        data: s.data,
        backgroundColor: color + '22',
        borderColor: color,
        borderWidth: 2,
        pointRadius: isDaily ? 2 : 3,
        pointHoverRadius: 6,
        fill: false,
        tension: 0.3,
      };
    });

    _overtimeChart = new Chart(canvas, {
      type: 'line',
      data: { labels: data.months, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ctx.raw > 0 ? `${ctx.dataset.label}: ${fmt(ctx.raw)}` : null,
            },
            filter: item => item.raw > 0,
          },
        },
        scales: {
          x: {
            stacked: false,
            grid: { display: false },
            ticks: {
              color: 'var(--fin-ink-2)',
              font: { size: 10 },
              maxRotation: isDaily ? 45 : 0,
              autoSkip: true,
              maxTicksLimit: isDaily ? 15 : 20,
            },
          },
          y: {
            stacked: false,
            beginAtZero: true,
            grid: { color: 'var(--fin-border)' },
            ticks: { callback: v => fmt(v), font: { size: 10 }, color: 'var(--fin-ink-3)' },
          },
        },
      },
    });

    if (legendEl) {
      legendEl.innerHTML = `
        <div class="flex" style="flex-wrap:wrap;gap:6px 12px;padding-top:8px;border-top:1px solid var(--fin-border)">
          ${data.series.map((s, i) => {
            const colorIdx = _availableCategories.indexOf(s.category);
            const color = getColor(colorIdx >= 0 ? colorIdx : i);
            return `
              <button data-legend-idx="${i}" class="text-muted flex items-center gap-1"
                style="background:none;border:none;cursor:pointer;padding:3px 6px;border-radius:4px;font-size:0.78rem;transition:background 0.1s"
                onmouseover="this.style.background='var(--fin-surface-2)'" onmouseout="this.style.background=''">
                <span data-legend-dot="${i}" style="width:10px;height:10px;border-radius:2px;background:${color};flex-shrink:0"></span>
                <span>${sanitize(s.category)}</span>
              </button>`;
          }).join('')}
        </div>
      `;
      legendEl.querySelectorAll('[data-legend-idx]').forEach(btn => {
        btn.addEventListener('click', () => {
          const idx = parseInt(btn.dataset.legendIdx);
          const meta = _overtimeChart.getDatasetMeta(idx);
          meta.hidden = !meta.hidden;
          const dot = btn.querySelector('[data-legend-dot]');
          btn.style.opacity = meta.hidden ? '0.35' : '1';
          dot.style.opacity = meta.hidden ? '0.3' : '1';
          _overtimeChart.update();
        });
      });
    }
  } catch (err) {
    if (loadingEl) loadingEl.style.display = 'none';
    if (legendEl) legendEl.innerHTML = `<div class="alert alert-danger text-soft">${sanitize(err.message)}</div>`;
  }
}
