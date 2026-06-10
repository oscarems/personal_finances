import * as api from '../api/client.js';
import { fmtCurrency, fmtPercent, sanitize, currentMonth, fmtMonthLabel, prevMonth, nextMonth } from '../utils.js';

export const title = 'Salud Financiera';

let _month = currentMonth();
let _chart = null;

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  await load(container);
}

export function cleanup() { _chart?.destroy(); _chart = null; }

async function load(container) {
  try {
    const data = await api.reports.financialHealth({ month: _month });
    render(container, data);
  } catch (err) {
    container.innerHTML = `
      <div class="page-header"><div class="page-header-text"><h1>Salud Financiera</h1></div></div>
      <div class="alert alert-danger">${sanitize(err.message)}</div>
      <div class="fh-retry-wrap">
        <button class="btn btn-ghost btn-sm fh-retry">Reintentar</button>
      </div>`;
  }
}

function render(container, data) {
  const scores   = data.scores ?? {};
  const buckets  = data.buckets ?? {};
  const targets  = data.targets ?? { needs: 50, wants: 30, savings: 20 };
  const insights = data.insights ?? [];
  const overBudget = data.over_budget_categories ?? [];
  const income   = data.income_analysis ?? {};
  const currency = data.currency?.code ?? 'COP';

  const overall = scores.overall ?? null;
  const grade   = scores.grade ?? '—';
  const adherence = scores.adherence ?? 0;
  const rule      = scores.rule ?? 0;

  const gradeInfo = getGradeInfo(overall);

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Salud Financiera</h1>
        <p>Regla ${targets.needs}/${targets.wants}/${targets.savings} · ${fmtMonthLabel(_month)}</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-ghost btn-sm" id="fhPrev">‹ Anterior</button>
        <button class="btn btn-ghost btn-sm" id="fhNext">Siguiente ›</button>
      </div>
    </div>

    <!-- ── SCORE HERO ──────────────────────────────────────────────────── -->
    <div class="fh-hero-grid mb-4">

      <!-- Overall score -->
      <div class="card fh-score-hero flex flex-col fh-no-gap">
        <div class="fh-card-top">
          <div class="fh-label-chip">Puntaje General</div>
          ${overall != null ? `
            <div class="flex gap-2 mt-2 fh-score-row">
              <div class="fh-big-score" style="color:${gradeInfo.color}">${overall.toFixed(0)}</div>
              <div class="fh-grade-info">
                <div class="fh-grade-badge" style="background:${gradeInfo.bg};color:${gradeInfo.color}">Grado ${grade}</div>
                <div class="fh-sub-note mt-1">${gradeInfo.label}</div>
              </div>
            </div>
            ${scoreGauge(overall, gradeInfo.color)}
          ` : '<div class="text-soft fh-no-data">Sin datos suficientes este mes</div>'}
        </div>
        <!-- How is it calculated -->
        <div class="fh-explain-box fh-explain-box--no-top fh-explain-box--spaced">
          <div class="fh-explain-title">¿Cómo se calcula?</div>
          <p class="fh-explain-text">El puntaje general es el <strong>promedio de dos sub-puntajes</strong>, cada uno de 0 a 100:</p>
          <div class="flex flex-col gap-2 mt-2">
            ${miniScoreExplain('Cumplimiento', adherence, 'Qué tan bien ejecutaste el presupuesto asignado (gastado vs. asignado por categoría).')}
            ${miniScoreExplain('Distribución', rule, `Qué tan cerca está tu gasto de la regla ${targets.needs}/${targets.wants}/${targets.savings}.`)}
          </div>
        </div>
      </div>

      <!-- Adherence explanation -->
      <div class="card flex flex-col">
        <div class="fh-card-top">
          <div class="fh-label-chip fh-label-chip--indigo">Sub-puntaje 1</div>
          <div class="flex items-center gap-2 mt-2 mb-1">
            <span class="fh-sub-heading">Cumplimiento</span>
            ${scorePill(adherence)}
          </div>
          <div class="fh-mini-gauge mb-0">
            <div style="height:100%;width:${adherence}%;background:${scoreColor(adherence)};border-radius:inherit;transition:width .5s"></div>
          </div>
        </div>
        <div class="fh-explain-box fh-explain-box--spaced">
          <div class="fh-explain-title">¿Qué mide?</div>
          <p class="fh-explain-text">Evalúa si <strong>gastaste dentro de lo que planeaste</strong>. Para cada categoría compara el gasto real contra el monto asignado en el presupuesto.</p>
          <div class="fh-formula-box">
            <code>Por categoría: min(1, asignado / gastado)</code><br>
            <code>Puntaje = promedio × 100</code>
          </div>
          <div class="fh-scale">
            <span class="text-success">≥ 80 Excelente</span>
            <span class="text-warning">60–79 Regular</span>
            <span class="text-danger">< 60 Crítico</span>
          </div>
        </div>
      </div>

      <!-- Rule explanation -->
      <div class="card flex flex-col">
        <div class="fh-card-top">
          <div class="fh-label-chip fh-label-chip--green">Sub-puntaje 2</div>
          <div class="flex items-center gap-2 mt-2 mb-1">
            <span class="fh-sub-heading">Distribución</span>
            ${scorePill(rule)}
          </div>
          <div class="fh-mini-gauge mb-0">
            <div style="height:100%;width:${rule}%;background:${scoreColor(rule)};border-radius:inherit;transition:width .5s"></div>
          </div>
        </div>
        <div class="fh-explain-box fh-explain-box--spaced">
          <div class="fh-explain-title">¿Qué mide?</div>
          <p class="fh-explain-text">Evalúa si tu <strong>distribución del gasto sigue la regla ${targets.needs}/${targets.wants}/${targets.savings}</strong>. Penaliza cuando una categoría se aleja mucho de su objetivo.</p>
          <div class="fh-formula-box">
            <code>Desviación = |real% − objetivo%| / objetivo%</code><br>
            <code>Puntaje = (1 − desviación) × 100</code>
          </div>
          <div class="fh-scale">
            <span class="text-success">≥ 80 En meta</span>
            <span class="text-warning">60–79 Cerca</span>
            <span class="text-danger">< 60 Lejos</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── REGLA 50/30/20 EXPLANATION ──────────────────────────────────── -->
    <div class="fh-rule-banner mb-4">
      <div class="fh-rule-banner-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        ¿Qué es la Regla ${targets.needs}/${targets.wants}/${targets.savings}?
      </div>
      <p class="fh-rule-banner-text">Una guía de distribución del ingreso mensual. Divide tu sueldo en tres grandes grupos según su propósito:</p>
      <div class="fh-rule-pills">
        <div class="fh-rule-pill fh-rule-pill--cyan">
          <span class="fh-rule-pill-pct fh-rule-pill-pct--cyan">${targets.needs}%</span>
          <span class="fh-rule-pill-label">Necesidades</span>
          <span class="fh-rule-pill-desc">Gastos fijos e ineludibles: vivienda, comida, transporte, servicios públicos.</span>
        </div>
        <div class="fh-rule-pill fh-rule-pill--amber">
          <span class="fh-rule-pill-pct fh-rule-pill-pct--amber">${targets.wants}%</span>
          <span class="fh-rule-pill-label">Deseos</span>
          <span class="fh-rule-pill-desc">Gastos opcionales: entretenimiento, salidas, suscripciones, ropa no esencial.</span>
        </div>
        <div class="fh-rule-pill fh-rule-pill--green">
          <span class="fh-rule-pill-pct fh-rule-pill-pct--green">${targets.savings}%</span>
          <span class="fh-rule-pill-label">Ahorro / Deudas</span>
          <span class="fh-rule-pill-desc">Fondo de emergencia, inversión y pago de deudas por encima del mínimo.</span>
        </div>
      </div>
    </div>

    <!-- ── BUCKET CARDS ────────────────────────────────────────────────── -->
    <div class="grid-3 mb-4">
      ${bucketCard('Necesidades', 'needs', buckets.needs, targets.needs, currency,
        '#22d3ee', 'rgba(8,145,178,0.8)',
        'Vivienda, servicios, comida, transporte y cualquier gasto que no puedas eliminar.')}
      ${bucketCard('Deseos', 'wants', buckets.wants, targets.wants, currency,
        '#fbbf24', 'rgba(217,119,6,0.8)',
        'Entretenimiento, restaurantes, ropa extra, suscripciones opcionales y hobbies.')}
      ${bucketCard('Ahorro', 'savings', buckets.savings, targets.savings, currency,
        '#34d399', 'rgba(5,150,105,0.8)',
        'Ahorros, inversiones, pago de deudas y fondo de emergencia.')}
    </div>

    <!-- ── INCOME SECTION ──────────────────────────────────────────────── -->
    ${income.total_income > 0 ? incomeSection(income, targets, currency) : ''}

    <!-- ── INSIGHTS ────────────────────────────────────────────────────── -->
    ${insights.length ? insightsSection(insights) : ''}

    <!-- ── OVER-BUDGET ─────────────────────────────────────────────────── -->
    ${overBudget.length ? overBudgetSection(overBudget, currency) : ''}

    <!-- ── SEMÁFORO POR CATEGORÍA ────────────────────────────────────── -->
    ${semaphoreSection(buckets, currency)}

    <!-- ── CHART ───────────────────────────────────────────────────────── -->
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title">${income.total_income > 0 ? 'Distribución Real vs. Objetivo (% del ingreso)' : 'Distribución del Presupuesto Asignado'}</span>
        <span class="fh-chart-note">Barras claras = objetivo</span>
      </div>
      <div class="card-body fh-chart-container">
        <canvas id="fhChart"></canvas>
      </div>
    </div>

    <style>
      .fh-hero-grid { display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px }
      .fh-no-gap { gap:0 }
      .fh-score-row { align-items:flex-end }
      .fh-grade-info { padding-bottom:8px }
      .fh-retry-wrap { text-align:center;margin-top:16px }
      .fh-explain-box--spaced { margin:16px }
      .fh-explain-box--overbudget { margin:0 20px 16px;margin-top:-4px }
      .fh-progress-track { height:6px;background:var(--border-muted);border-radius:3px;overflow:hidden }
      .fh-progress-track--sm { height:5px }
      .fh-bucket-def--spaced { margin:12px 20px 16px }
      .fh-card-body--flush { padding-top:0 }
      .fh-td-bold { font-weight:600 }
      .fh-card-top { padding:20px 20px 0 }
      .fh-big-score { font-family:var(--font-display);font-size:3.75rem;font-weight:800;line-height:1;letter-spacing:-0.03em }
      .fh-grade-badge { display:inline-block;font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:20px }
      .fh-label-chip { display:inline-block;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;padding:3px 8px;border-radius:20px;background:rgba(255,255,255,0.07);color:var(--text-soft) }
      .fh-label-chip--indigo { background:rgba(99,102,241,0.15);color:#818cf8 }
      .fh-label-chip--green  { background:rgba(16,185,129,0.15);color:#34d399 }
      .fh-sub-heading { font-size:1.0625rem;font-weight:700;color:var(--text-primary) }
      .fh-sub-note { font-size:0.7rem;color:var(--text-soft) }
      .fh-no-data { font-size:0.875rem;padding:16px 0 }
      .fh-explain-box { background:rgba(255,255,255,0.03);border:1px solid var(--border-muted);border-radius:10px;padding:12px 14px }
      .fh-explain-box--no-top { border-top:none }
      .fh-explain-title { font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-soft);margin-bottom:6px }
      .fh-explain-text { font-size:0.7875rem;color:var(--text-secondary);line-height:1.5;margin:0 }
      .fh-explain-text strong { color:var(--text-primary);font-weight:600 }
      .fh-formula-box { background:rgba(0,0,0,0.25);border-radius:6px;padding:8px 10px;margin-top:8px;font-size:0.7rem;color:var(--text-soft);line-height:1.7 }
      .fh-formula-box code { font-family:var(--font-mono);color:var(--text-secondary) }
      .fh-scale { display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;font-size:0.65rem;font-weight:600 }
      .fh-mini-gauge { height:5px;background:var(--border-muted);border-radius:3px;overflow:hidden;margin-top:8px;margin-bottom:16px }
      .fh-rule-banner { background:rgba(255,255,255,0.03);border:1px solid var(--border-muted);border-radius:12px;padding:16px 20px }
      .fh-rule-banner-title { display:flex;align-items:center;gap:6px;font-size:0.8125rem;font-weight:700;color:var(--text-primary);margin-bottom:6px }
      .fh-rule-banner-text { font-size:0.7875rem;color:var(--text-secondary);margin:0 0 12px }
      .fh-rule-pills { display:grid;grid-template-columns:repeat(3,1fr);gap:12px }
      .fh-rule-pill { border:1px solid;border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:3px }
      .fh-rule-pill--cyan  { border-color:rgba(8,145,178,0.4);background:rgba(8,145,178,0.08) }
      .fh-rule-pill--amber { border-color:rgba(217,119,6,0.4);background:rgba(217,119,6,0.08) }
      .fh-rule-pill--green { border-color:rgba(5,150,105,0.4);background:rgba(5,150,105,0.08) }
      .fh-rule-pill-pct { font-family:var(--font-mono);font-size:1.5rem;font-weight:800;line-height:1 }
      .fh-rule-pill-pct--cyan  { color:#22d3ee }
      .fh-rule-pill-pct--amber { color:#fbbf24 }
      .fh-rule-pill-pct--green { color:#34d399 }
      .fh-rule-pill-label { font-size:0.75rem;font-weight:700;color:var(--text-primary) }
      .fh-rule-pill-desc { font-size:0.7rem;color:var(--text-soft);line-height:1.45;margin-top:2px }
      .fh-bucket-def { margin-top:10px;padding-top:10px;border-top:1px solid var(--border-muted) }
      .fh-bucket-def-text { font-size:0.7rem;color:var(--text-soft);line-height:1.45 }
      .fh-insights-grid { display:flex;flex-direction:column;gap:10px }
      .fh-insight-row { display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:8px;border:1px solid }
      .fh-insight-row--good { background:rgba(5,150,105,0.06);border-color:rgba(5,150,105,0.2) }
      .fh-insight-row--warn { background:rgba(217,119,6,0.06);border-color:rgba(217,119,6,0.2) }
      .fh-insight-row--bad  { background:rgba(220,38,38,0.06);border-color:rgba(220,38,38,0.2) }
      .fh-insight-icon { width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:800;flex-shrink:0;margin-top:1px }
      .fh-insight-icon--good { background:rgba(5,150,105,0.15);color:var(--color-success) }
      .fh-insight-icon--warn { background:rgba(217,119,6,0.15);color:var(--color-warning) }
      .fh-insight-icon--bad  { background:rgba(220,38,38,0.15);color:var(--color-danger) }
      .fh-insight-msg  { font-size:0.8125rem;font-weight:600;color:var(--text-primary) }
      .fh-insight-detail { font-size:0.75rem;color:var(--text-soft);margin-top:2px;line-height:1.4 }
      .fh-stat-box { text-align:center;padding:10px;background:rgba(255,255,255,0.03);border-radius:8px;border:1px solid var(--border-muted) }
      .fh-stat-label { font-size:0.65rem;color:var(--text-soft);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em }
      .fh-stat-value { font-family:var(--font-mono);font-size:0.9375rem;font-weight:700 }
      .fh-score-box { text-align:center }
      .fh-score-box-label { font-size:0.65rem;color:var(--text-soft);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em }
      .fh-score-box-grade { font-size:0.65rem;color:var(--text-soft) }
      .fh-income-bucket { background:rgba(255,255,255,0.03);border:1px solid var(--border-muted);border-radius:10px;padding:12px 14px }
      .fh-income-bucket-label { font-size:0.8125rem;font-weight:600 }
      .fh-income-bucket-footer { font-size:0.7rem;color:var(--text-soft);margin-top:4px }
      .fh-sema-row { display:grid;grid-template-columns:1.2rem 1fr auto;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border-muted) }
      .fh-sema-icon { font-size:0.85rem }
      .fh-sema-name { font-size:0.8rem;font-weight:500 }
      .fh-sema-bar-track { height:4px;background:var(--border-muted);border-radius:2px;margin-top:4px }
      .fh-sema-right { text-align:right;min-width:110px }
      .fh-sema-amount { font-size:0.75rem;font-family:var(--font-mono);color:var(--text-secondary) }
      .fh-sema-pct { font-size:0.68rem;color:var(--text-soft) }
      .fh-semaphore-note { font-size:0.72rem;color:var(--text-soft) }
      .fh-chart-note { font-size:0.75rem;color:var(--text-soft) }
      .fh-chart-container { height:260px;position:relative }
      .fh-cat-list { border-top:1px solid var(--border-muted);padding:10px 20px 16px;display:flex;flex-direction:column;gap:5px }
      .fh-cat-row { display:flex;justify-content:space-between;align-items:center }
      .fh-cat-name { font-size:0.75rem;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:60% }
      .fh-cat-amount { font-family:var(--font-mono);font-size:0.75rem;color:var(--text-secondary) }
      .fh-cat-more { font-size:0.65rem;color:var(--text-soft);text-align:right;margin-top:2px }
      .fh-bucket-header { display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px }
      .fh-bucket-pct { font-family:var(--font-mono);font-size:2rem;font-weight:800;line-height:1 }
      .fh-bucket-pct-unit { font-size:1rem;opacity:0.7 }
      .fh-bucket-note { font-size:0.7rem;color:var(--text-soft);margin-top:2px }
      .fh-bucket-right { text-align:right }
      .fh-bucket-obj { font-size:0.65rem;color:var(--text-soft);margin-top:4px }
      .fh-bucket-score { font-size:0.7rem;font-family:var(--font-mono);font-weight:700;margin-top:2px }
      .fh-progress-labels { display:flex;justify-content:space-between;font-size:0.65rem;color:var(--text-soft);margin-top:3px }
      .fh-gauge-labels { display:flex;justify-content:space-between;font-size:0.65rem;color:var(--text-soft);margin-top:4px }
      .fh-mini-block { padding:8px 10px;background:rgba(0,0,0,0.2);border-radius:8px }
      .fh-mini-block-header { display:flex;justify-content:space-between;align-items:center;margin-bottom:4px }
      .fh-mini-block-label { font-size:0.7875rem;font-weight:600;color:var(--text-primary) }
      .fh-mini-block-desc { font-size:0.7rem;color:var(--text-soft);line-height:1.4 }
      .fh-mini-block-bar { margin-top:5px;height:3px;background:var(--border-muted);border-radius:2px;overflow:hidden }
      .fh-gauge-track { height:8px;background:var(--border-muted);border-radius:4px;overflow:hidden }
      .fh-gauge-wrap { margin:12px 0 6px }
      .fh-badge-font { font-size:0.65rem }
      .fh-overbudget-title { color:var(--color-danger) }
      .fh-td-sm { font-size:0.8rem }
      .fh-td-name { font-size:0.8125rem;font-weight:500 }
      .fh-td-group { font-size:0.75rem;color:var(--text-soft) }
      .fh-score-pill-value { font-family:var(--font-mono);font-size:1.25rem;font-weight:700 }
      .fh-score-pill-denom { font-size:0.75rem;opacity:0.6 }
      @media (max-width:768px) {
        .fh-hero-grid { grid-template-columns:1fr }
        .fh-rule-pills { grid-template-columns:1fr }
      }
    </style>
  `;

  container.querySelector('#fhPrev')?.addEventListener('click', async () => {
    _month = prevMonth(_month);
    await load(container);
  });
  container.querySelector('#fhNext')?.addEventListener('click', async () => {
    _month = nextMonth(_month);
    await load(container);
  });

  // Reintentar button wiring (for error state)
  container.querySelector('.fh-retry')?.addEventListener('click', () => load(container));

  const ctx = container.querySelector('#fhChart');
  if (ctx) {
    _chart?.destroy();
    // Bucket colors are semantic (not positional) — using defined palette per bucket type
    const cNeedsBar = 'rgba(8,145,178,0.85)';
    const cWantsBar = 'rgba(217,119,6,0.85)';
    const cSavBar   = 'rgba(5,150,105,0.85)';
    const cNeedsObj = 'rgba(8,145,178,0.15)';
    const cWantsObj = 'rgba(217,119,6,0.15)';
    const cSavObj   = 'rgba(5,150,105,0.15)';
    const cNeedsBdr = 'rgba(8,145,178,0.5)';
    const cWantsBdr = 'rgba(217,119,6,0.5)';
    const cSavBdr   = 'rgba(5,150,105,0.5)';

    if (income.total_income > 0) {
      const ib = income.buckets ?? {};
      _chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['Necesidades', 'Deseos', 'Ahorro'],
          datasets: [
            {
              label: 'Real (%)',
              data: [ib.needs?.pct_of_income ?? 0, ib.wants?.pct_of_income ?? 0, ib.savings?.pct_of_income ?? 0],
              backgroundColor: [cNeedsBar, cWantsBar, cSavBar],
              borderRadius: 6,
            },
            {
              label: 'Objetivo (%)',
              data: [targets.needs, targets.wants, targets.savings],
              backgroundColor: [cNeedsObj, cWantsObj, cSavObj],
              borderColor:     [cNeedsBdr, cWantsBdr, cSavBdr],
              borderWidth: 1.5,
              borderRadius: 6,
            },
          ],
        },
        options: chartOptions(),
      });
    } else {
      _chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['Necesidades', 'Deseos', 'Ahorro'],
          datasets: [
            {
              label: '% del presupuesto asignado',
              data: [
                buckets.needs?.pct_of_assigned ?? 0,
                buckets.wants?.pct_of_assigned ?? 0,
                buckets.savings?.pct_of_assigned ?? 0,
              ],
              backgroundColor: [cNeedsBar, cWantsBar, cSavBar],
              borderRadius: 6,
            },
            {
              label: 'Objetivo (%)',
              data: [targets.needs, targets.wants, targets.savings],
              backgroundColor: [cNeedsObj, cWantsObj, cSavObj],
              borderColor:     [cNeedsBdr, cWantsBdr, cSavBdr],
              borderWidth: 1.5,
              borderRadius: 6,
            },
          ],
        },
        options: chartOptions(),
      });
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getGradeInfo(score) {
  if (score == null) return { color: 'var(--text-soft)', bg: 'rgba(255,255,255,0.07)', label: '—' };
  if (score >= 90) return { color: '#34d399', bg: 'rgba(5,150,105,0.15)', label: 'Excelente' };
  if (score >= 80) return { color: '#4ade80', bg: 'rgba(74,222,128,0.12)', label: 'Muy bien' };
  if (score >= 70) return { color: '#fbbf24', bg: 'rgba(217,119,6,0.15)', label: 'Bien' };
  if (score >= 60) return { color: '#fb923c', bg: 'rgba(234,88,12,0.15)', label: 'Regular' };
  return { color: '#f87171', bg: 'rgba(220,38,38,0.12)', label: 'Crítico' };
}

function scoreColor(v) {
  return v >= 80 ? 'var(--color-success)' : v >= 60 ? 'var(--color-warning)' : 'var(--color-danger)';
}

function scorePill(v) {
  const color = scoreColor(v);
  return `<span class="fh-score-pill-value" style="color:${color}">${(v ?? 0).toFixed(0)}<span class="fh-score-pill-denom">/100</span></span>`;
}

function scoreGauge(value, color) {
  const pct = Math.min(100, Math.max(0, value));
  return `
    <div class="fh-gauge-wrap">
      <div class="fh-gauge-track">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:inherit;transition:width .6s cubic-bezier(.4,0,.2,1)"></div>
      </div>
      <div class="fh-gauge-labels">
        <span>0</span><span>Crítico</span><span>Regular</span><span>Excelente</span><span>100</span>
      </div>
    </div>`;
}

function miniScoreExplain(label, value, description) {
  const v = value ?? 0;
  const color = scoreColor(v);
  return `
    <div class="fh-mini-block">
      <div class="fh-mini-block-header">
        <span class="fh-mini-block-label">${label}</span>
        <span class="fh-score-pill-value" style="font-size:0.875rem;color:${color}">${v.toFixed(0)}</span>
      </div>
      <div class="fh-mini-block-desc">${description}</div>
      <div class="fh-mini-block-bar">
        <div style="height:100%;width:${v}%;background:${color};border-radius:inherit"></div>
      </div>
    </div>`;
}

function bucketCard(label, key, b, targetPct, currency, accentColor, barColor, description) {
  if (!b) return '';
  const actual    = b.pct_of_assigned ?? 0;
  const diff      = actual - targetPct;
  const isGood    = Math.abs(diff) <= 5;
  const isWarning = !isGood && Math.abs(diff) <= 15;
  const badgeClass = isGood ? 'badge-success' : isWarning ? 'badge-warning' : 'badge-danger';
  const badgeLabel = isGood ? '✓ En meta' : (diff > 0 ? `+${diff.toFixed(1)}% exceso` : `${diff.toFixed(1)}% bajo`);
  const ruleScore  = b.rule_score ?? 0;
  const fillPct    = Math.min(100, actual / (targetPct || 1) * 100);
  const ruleScoreColor = scoreColor(ruleScore);

  return `
    <div class="card flex flex-col">
      <div class="fh-card-top">
        <div class="fh-bucket-header">
          <div>
            <div class="fh-label-chip mb-2" style="background:${barColor.replace('0.8', '0.15')};color:${accentColor}">${label}</div>
            <div class="fh-bucket-pct" style="color:${accentColor}">${actual.toFixed(1)}<span class="fh-bucket-pct-unit">%</span></div>
            <div class="fh-bucket-note">del presupuesto asignado</div>
          </div>
          <div class="fh-bucket-right">
            <span class="badge ${badgeClass} fh-badge-font">${badgeLabel}</span>
            <div class="fh-bucket-obj">Objetivo: ${targetPct}%</div>
            <div class="fh-bucket-score" style="color:${ruleScoreColor}">${ruleScore}/100</div>
          </div>
        </div>

        <!-- Progress -->
        <div class="mb-2">
          <div class="fh-progress-track">
            <div style="height:100%;width:${fillPct}%;background:${barColor};border-radius:inherit;transition:width .5s"></div>
          </div>
          <div class="fh-progress-labels">
            <span>Gastado: <span class="amount">${fmtCurrency(b.spent, currency)}</span></span>
            <span>Asignado: <span class="amount">${fmtCurrency(b.assigned, currency)}</span></span>
          </div>
        </div>
      </div>

      <!-- Definition box -->
      <div class="fh-bucket-def fh-bucket-def--spaced">
        <div class="fh-explain-title">¿Qué incluye?</div>
        <p class="fh-bucket-def-text">${description}</p>
      </div>

      <!-- Category breakdown -->
      ${b.categories?.length ? categoriesList(b.categories, currency, accentColor) : ''}
    </div>`;
}

function categoriesList(cats, currency, accentColor) {
  return `
    <div class="fh-cat-list">
      <div class="fh-explain-title mb-1">Detalle por categoría</div>
      ${cats.slice(0, 6).map(c => `
        <div class="fh-cat-row">
          <span class="fh-cat-name">${sanitize(c.category_name ?? '—')}</span>
          <span class="fh-cat-amount">${fmtCurrency(c.spent, currency)}</span>
        </div>`).join('')}
      ${cats.length > 6 ? `<div class="fh-cat-more">+${cats.length - 6} más</div>` : ''}
    </div>`;
}

function insightsSection(insights) {
  const good = insights.filter(i => i.kind === 'good');
  const warn = insights.filter(i => i.kind === 'warn');
  const bad  = insights.filter(i => i.kind === 'bad');

  return `
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title">Señales del mes</span>
        <span class="fh-chart-note">${insights.length} observación${insights.length !== 1 ? 'es' : ''}</span>
      </div>
      <div class="card-body">
        <div class="fh-insights-grid">
          ${[...bad, ...warn, ...good].map(ins => insightRow(ins)).join('')}
        </div>
      </div>
    </div>`;
}

function insightRow(ins) {
  const isGood = ins.kind === 'good';
  const isWarn = ins.kind === 'warn';
  const rowCls  = isGood ? 'fh-insight-row--good' : isWarn ? 'fh-insight-row--warn' : 'fh-insight-row--bad';
  const iconCls = isGood ? 'fh-insight-icon--good' : isWarn ? 'fh-insight-icon--warn' : 'fh-insight-icon--bad';
  const icon    = isGood ? '✓' : isWarn ? '!' : '✗';
  return `
    <div class="fh-insight-row ${rowCls}">
      <div class="fh-insight-icon ${iconCls}">${icon}</div>
      <div>
        <div class="fh-insight-msg">${sanitize(ins.message)}</div>
        ${ins.detail ? `<div class="fh-insight-detail">${sanitize(ins.detail)}</div>` : ''}
      </div>
    </div>`;
}

function incomeSection(income, targets, currency) {
  const ib    = income.buckets ?? {};
  const score = income.score ?? 0;
  const gradeColor = scoreColor(score);

  return `
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title">Análisis por Ingreso Real</span>
        <span class="fh-chart-note">Ingreso total: <span class="amount">${fmtCurrency(income.total_income, currency)}</span></span>
      </div>
      <div class="card-body">
        <div class="fh-explain-box mb-4">
          <div class="fh-explain-title">¿Cómo se lee esta sección?</div>
          <p class="fh-explain-text">Aquí el análisis usa tu <strong>ingreso real del mes</strong> (en lugar del presupuesto asignado) para medir qué porcentaje de tu sueldo fue a cada grupo. Esto permite comparar contra la regla ${targets.needs}/${targets.wants}/${targets.savings} de forma más precisa.</p>
        </div>
        <div class="grid-4 mb-4">
          ${incomeStatBox('Ingreso', income.total_income, currency, 'var(--color-success)')}
          ${incomeStatBox('Gastado', income.total_spent, currency, 'var(--color-danger)')}
          ${incomeStatBox('Sin usar', income.total_income - income.total_spent, currency,
            (income.total_income - income.total_spent) >= 0 ? 'var(--color-success)' : 'var(--color-danger)')}
          <div class="fh-score-box">
            <div class="fh-score-box-label">Puntaje regla</div>
            <div class="amount fh-big-score" style="font-size:1.75rem;color:${gradeColor}">${score.toFixed(0)}</div>
            <div class="fh-score-box-grade">Grado ${income.grade ?? '—'}</div>
          </div>
        </div>
        <div class="grid-3">
          ${incomeBucketRow('Necesidades', ib.needs, targets.needs, 'rgba(8,145,178,0.8)', '#22d3ee')}
          ${incomeBucketRow('Deseos', ib.wants, targets.wants, 'rgba(217,119,6,0.8)', '#fbbf24')}
          ${incomeBucketRow('Ahorro', ib.savings, targets.savings, 'rgba(5,150,105,0.8)', '#34d399')}
        </div>
      </div>
    </div>`;
}

function incomeStatBox(label, value, currency, color) {
  return `
    <div class="fh-stat-box">
      <div class="fh-stat-label">${label}</div>
      <div class="fh-stat-value" style="color:${color}">${fmtCurrency(value, currency)}</div>
    </div>`;
}

function incomeBucketRow(label, b, targetPct, barColor, accentColor) {
  if (!b) return '';
  const pct  = b.pct_of_income ?? 0;
  const diff = pct - targetPct;
  const isGood = Math.abs(diff) <= 5;
  const isWarn = !isGood && Math.abs(diff) <= 15;
  return `
    <div class="fh-income-bucket">
      <div class="flex justify-between items-center mb-2">
        <span class="fh-income-bucket-label" style="color:${accentColor}">${label}</span>
        <span class="badge ${isGood ? 'badge-success' : isWarn ? 'badge-warning' : 'badge-danger'} fh-badge-font">
          ${pct.toFixed(1)}% / ${targetPct}%
        </span>
      </div>
      <div class="fh-progress-track fh-progress-track--sm">
        <div style="height:100%;width:${Math.min(100, pct / (targetPct || 1) * 100)}%;background:${barColor};border-radius:inherit;transition:width .4s"></div>
      </div>
      <div class="fh-income-bucket-footer"><span class="amount">${fmtCurrency(b.amount ?? 0, 'COP')}</span> este mes</div>
    </div>`;
}

function overBudgetSection(items, currency) {
  return `
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title fh-overbudget-title">⚠ Categorías Excedidas</span>
        <span class="badge badge-danger">${items.length}</span>
      </div>
      <div class="fh-explain-box fh-explain-box--overbudget">
        <p class="fh-explain-text">Estas categorías gastaron <strong>más de lo asignado</strong> este mes. Cada una resta puntos al puntaje de Cumplimiento.</p>
      </div>
      <div class="card-body fh-card-body--flush">
        <table class="fin-table">
          <thead>
            <tr>
              <th>Categoría</th>
              <th>Grupo</th>
              <th class="amount">Asignado</th>
              <th class="amount">Gastado</th>
              <th class="amount">Exceso</th>
              <th class="amount">%</th>
            </tr>
          </thead>
          <tbody>
            ${items.map(c => `
              <tr>
                <td class="fh-td-name">${sanitize(c.category_name ?? '—')}</td>
                <td class="fh-td-group">${sanitize(c.group_name ?? '—')}</td>
                <td class="amount fh-td-sm">${fmtCurrency(c.assigned, currency)}</td>
                <td class="amount fh-td-sm">${fmtCurrency(c.spent, currency)}</td>
                <td class="amount fh-td-sm text-danger fh-td-bold">${fmtCurrency(c.overspend, currency)}</td>
                <td class="amount fh-td-sm text-danger">${c.overspend_pct?.toFixed(1) ?? '—'}%</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>`;
}

function semaphoreSection(buckets, currency) {
  const bucketDefs = [
    { key: 'needs',   label: 'Necesidades', color: '#22d3ee' },
    { key: 'wants',   label: 'Deseos',      color: '#fbbf24' },
    { key: 'savings', label: 'Ahorro',      color: '#34d399' },
  ];

  const allCats = [];
  for (const { key, label, color } of bucketDefs) {
    const cats = (buckets[key]?.categories ?? []).filter(c => (c.assigned ?? 0) > 0 || (c.spent ?? 0) > 0);
    cats.forEach(c => allCats.push({ ...c, bucket: label, bucketColor: color, isSavings: key === 'savings' }));
  }

  if (allCats.length === 0) return '';

  const rows = allCats.map(c => {
    const assigned = c.assigned ?? 0;
    const spent    = c.spent ?? 0;
    const pct      = assigned > 0 ? (spent / assigned) * 100 : 0;

    let light, status;
    if (c.isSavings) {
      const available = c.available ?? 0;
      if (available >= 0) { light = '🟢'; status = 'ok'; }
      else { light = '🔴'; status = 'danger'; }
    } else {
      if (pct <= 80)      { light = '🟢'; status = 'ok'; }
      else if (pct <= 100){ light = '🟡'; status = 'warning'; }
      else                { light = '🔴'; status = 'danger'; }
    }

    const barWidth = Math.min(100, pct);
    const barColor = status === 'ok' ? 'var(--color-success)' : status === 'warning' ? 'var(--color-warning)' : 'var(--color-danger)';

    return `
      <div class="fh-sema-row">
        <span class="fh-sema-icon">${light}</span>
        <div>
          <div class="fh-sema-name">${sanitize(c.category_name)}</div>
          <div class="fh-sema-bar-track">
            <div style="height:100%;width:${barWidth}%;background:${barColor};border-radius:2px;transition:width .3s"></div>
          </div>
        </div>
        <div class="fh-sema-right">
          <div class="fh-sema-amount">${fmtCurrency(spent, currency)}</div>
          <div class="fh-sema-pct">${assigned > 0 ? pct.toFixed(0) + '% de ' + fmtCurrency(assigned, currency) : 'sin asignar'}</div>
        </div>
      </div>`;
  }).join('');

  return `
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title">Semáforo por Categoría</span>
        <span class="fh-semaphore-note">🟢 OK · 🟡 Precaución · 🔴 Excedido</span>
      </div>
      <div class="card-body fh-card-body--flush">${rows}</div>
    </div>`;
}

function chartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { font: { size: 11 }, color: 'var(--text-secondary)', padding: 16 } },
      tooltip: {
        callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` },
      },
    },
    scales: {
      y: {
        grid: { color: 'var(--border-muted)' },
        ticks: { callback: v => v + '%', color: 'var(--text-soft)', font: { size: 10 } },
        beginAtZero: true,
      },
      x: {
        grid: { display: false },
        ticks: { color: 'var(--text-secondary)', font: { size: 12 } },
      },
    },
  };
}
