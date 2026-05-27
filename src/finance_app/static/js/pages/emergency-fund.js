import * as api from '../api/client.js';
import { fmtCurrency, fmtNumber, sanitize } from '../utils.js';
import { toast } from '../components/toast.js';

export const title = 'Fondo de Emergencia';

let allCategories = [];
let coverageData  = null;

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    const [coverage, cats] = await Promise.all([
      api.emergencyFund.coverage(),
      api.emergencyFund.categories(),
    ]);
    coverageData  = coverage;
    allCategories = Array.isArray(cats) ? cats : [];
    render(container);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container) {
  const months       = coverageData?.months_coverage ?? 0;
  const totalFund    = coverageData?.emergency_funds_total ?? 0;
  const monthlyExp   = coverageData?.essential_expenses_total ?? 0;
  const currency     = coverageData?.currency_code ?? 'COP';
  const totalFund2   = coverageData?.emergency_funds_total_secondary ?? null;
  const monthlyExp2  = coverageData?.essential_expenses_total_secondary ?? null;
  const currency2    = coverageData?.secondary_currency_code ?? null;
  const target       = 6;
  const isGood       = months >= target;

  const expenseCats = allCategories.filter(c => !c.is_income && c.rollover_type !== 'accumulate');
  const savingsCats = allCategories.filter(c => !c.is_income && c.rollover_type === 'accumulate');

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Fondo de Emergencia</h1>
        <p>Recomendación: ${target} meses de gastos esenciales cubiertos.</p>
      </div>
    </div>

    <div id="ef-summary" style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">
      ${renderSummary(months, totalFund, monthlyExp, currency, totalFund2, monthlyExp2, currency2, target, isGood)}
    </div>

    <div class="section-grid cols-2">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Gastos Esenciales</span>
          <span style="font-size:0.75rem;color:var(--text-soft)">¿Cuánto necesitas cada mes?</span>
        </div>
        <div class="card-body" style="padding-top:0">
          ${renderCategoryList(expenseCats, 'is_essential')}
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Fondos de Emergencia</span>
          <span style="font-size:0.75rem;color:var(--text-soft)">¿Qué ahorros cubren emergencias?</span>
        </div>
        <div class="card-body" style="padding-top:0">
          ${renderCategoryList(savingsCats, 'is_emergency_fund')}
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll('[data-ef-toggle]').forEach(el => {
    el.addEventListener('change', handleToggle.bind(null, container));
  });
}

function renderDualCurrency(primary, primaryCurrency, secondary, secondaryCurrency) {
  if (secondary === null || secondaryCurrency === null) return '';
  return `<div style="font-size:0.78rem;color:var(--text-soft);margin-top:2px">${fmtCurrency(secondary, secondaryCurrency)}</div>`;
}

function renderSummary(months, totalFund, monthlyExp, currency, totalFund2, monthlyExp2, currency2, target, isGood) {
  const pct = Math.min(100, (months / target) * 100);
  const barClass = isGood ? 'ok' : months >= target * 0.5 ? 'warning' : 'danger';
  const valueColor = isGood
    ? 'var(--color-success)'
    : months >= target * 0.5 ? 'var(--color-warning)' : 'var(--color-danger)';

  const missing       = Math.max(0, monthlyExp * target - totalFund);
  const missing2      = monthlyExp2 !== null ? Math.max(0, monthlyExp2 * target - totalFund2) : null;

  return `
    <div class="card">
      <div class="card-body" style="text-align:center;padding:32px 20px">
        <div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);margin-bottom:12px">Cobertura</div>
        <div style="font-family:var(--font-display);font-size:4rem;font-weight:700;line-height:1;color:${valueColor}">
          ${fmtNumber(months === 999.99 ? 0 : months, 1)}
        </div>
        <div style="font-size:1rem;color:var(--text-secondary);margin-bottom:16px">meses cubiertos</div>
        <div class="progress-wrap" style="margin:0 auto;max-width:240px;height:8px">
          <div class="progress-fill ${barClass}" style="width:${pct}%"></div>
        </div>
        <div style="font-size:0.8rem;color:var(--text-soft);margin-top:8px">
          Meta: ${target} meses ${isGood ? '✓' : `(faltan ${fmtNumber(Math.max(0, target - months), 1)})`}
        </div>
      </div>
    </div>

    <div class="section-grid" style="grid-template-columns:1fr;gap:12px">
      <div class="kpi-card">
        <div class="kpi-label">Total Fondo de Emergencia</div>
        <div class="kpi-value positive">${fmtCurrency(totalFund, currency)}</div>
        ${renderDualCurrency(totalFund, currency, totalFund2, currency2)}
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Gasto Mensual Esencial</div>
        <div class="kpi-value">${fmtCurrency(monthlyExp, currency)}</div>
        ${renderDualCurrency(monthlyExp, currency, monthlyExp2, currency2)}
      </div>
      ${!isGood
        ? `<div class="kpi-card">
            <div class="kpi-label">Falta para meta</div>
            <div class="kpi-value negative">${fmtCurrency(missing, currency)}</div>
            ${renderDualCurrency(missing, currency, missing2, currency2)}
          </div>`
        : `<div class="kpi-card">
            <div class="kpi-label">Estado</div>
            <div class="kpi-value positive" style="font-size:1rem">¡Fondo completo!</div>
          </div>`}
    </div>
  `;
}

function renderCategoryList(cats, flag) {
  if (!cats.length) {
    return '<div class="empty-state"><p>No hay categorías disponibles</p></div>';
  }

  const byGroup = {};
  for (const cat of cats) {
    const group = cat.category_group_name || 'Sin grupo';
    if (!byGroup[group]) byGroup[group] = [];
    byGroup[group].push(cat);
  }

  return Object.entries(byGroup).map(([group, groupCats]) => `
    <div style="margin-bottom:16px">
      <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--text-soft);padding:10px 0 6px">${sanitize(group)}</div>
      ${groupCats.map(cat => `
        <label style="display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:background 0.15s"
               onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background=''">
          <input type="checkbox"
                 data-ef-toggle
                 data-category-id="${cat.id}"
                 data-flag="${flag}"
                 ${cat[flag] ? 'checked' : ''}
                 style="width:16px;height:16px;accent-color:var(--color-primary);cursor:pointer;flex-shrink:0">
          <span style="font-size:0.875rem;color:var(--text-primary)">${sanitize(cat.name)}</span>
        </label>
      `).join('')}
    </div>
  `).join('');
}

async function handleToggle(container, e) {
  const { categoryId, flag } = e.target.dataset;
  const checked = e.target.checked;
  e.target.disabled = true;

  try {
    await api.emergencyFund.updateCategory(parseInt(categoryId), { [flag]: checked });

    const cat = allCategories.find(c => c.id === parseInt(categoryId));
    if (cat) cat[flag] = checked;

    coverageData = await api.emergencyFund.coverage();

    const months      = coverageData?.months_coverage ?? 0;
    const totalFund   = coverageData?.emergency_funds_total ?? 0;
    const monthlyExp  = coverageData?.essential_expenses_total ?? 0;
    const currency    = coverageData?.currency_code ?? 'COP';
    const totalFund2  = coverageData?.emergency_funds_total_secondary ?? null;
    const monthlyExp2 = coverageData?.essential_expenses_total_secondary ?? null;
    const currency2   = coverageData?.secondary_currency_code ?? null;
    const target      = 6;
    const isGood      = months >= target;

    const summary = container.querySelector('#ef-summary');
    if (summary) summary.innerHTML = renderSummary(months, totalFund, monthlyExp, currency, totalFund2, monthlyExp2, currency2, target, isGood);
  } catch (err) {
    e.target.checked = !checked;
    toast.error('Error al actualizar categoría: ' + err.message);
  } finally {
    e.target.disabled = false;
  }
}
