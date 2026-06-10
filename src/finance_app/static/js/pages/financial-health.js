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
      <div class="alert alert-danger">${sanitize(err.message)}</div>`;
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
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:24px">

      <!-- Overall score -->
      <div class="card fh-score-hero" style="grid-column:1;display:flex;flex-direction:column;gap:0">
        <div style="padding:20px 20px 0">
          <div class="fh-label-chip">Puntaje General</div>
          ${overall != null ? `
            <div style="display:flex;align-items:flex-end;gap:10px;margin-top:8px">
              <div class="fh-big-score" style="color:${gradeInfo.color}">${overall.toFixed(0)}</div>
              <div style="padding-bottom:8px">
                <div class="fh-grade-badge" style="background:${gradeInfo.bg};color:${gradeInfo.color}">Grado ${grade}</div>
                <div style="font-size:0.7rem;color:var(--text-soft);margin-top:3px">${gradeInfo.label}</div>
              </div>
            </div>
            ${scoreGauge(overall, gradeInfo.color)}
          ` : '<div style="color:var(--text-soft);font-size:0.875rem;padding:16px 0">Sin datos suficientes este mes</div>'}
        </div>
        <!-- How is it calculated -->
        <div class="fh-explain-box" style="margin:16px;border-top:none">
          <div class="fh-explain-title">¿Cómo se calcula?</div>
          <p class="fh-explain-text">El puntaje general es el <strong>promedio de dos sub-puntajes</strong>, cada uno de 0 a 100:</p>
          <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">
            ${miniScoreExplain('Cumplimiento', adherence, 'Qué tan bien ejecutaste el presupuesto asignado (gastado vs. asignado por categoría).')}
            ${miniScoreExplain('Distribución', rule, `Qué tan cerca está tu gasto de la regla ${targets.needs}/${targets.wants}/${targets.savings}.`)}
          </div>
        </div>
      </div>

      <!-- Adherence explanation -->
      <div class="card" style="display:flex;flex-direction:column">
        <div style="padding:20px 20px 0">
          <div class="fh-label-chip" style="background:rgba(99,102,241,0.15);color:#818cf8">Sub-puntaje 1</div>
          <div style="display:flex;align-items:center;gap:10px;margin-top:8px;margin-bottom:4px">
            <span style="font-size:1.0625rem;font-weight:700;color:var(--text-primary)">Cumplimiento</span>
            ${scorePill(adherence)}
          </div>
          <div class="fh-mini-gauge" style="margin-bottom:0">
            <div style="height:100%;width:${adherence}%;background:${scoreColor(adherence)};border-radius:inherit;transition:width .5s"></div>
          </div>
        </div>
        <div class="fh-explain-box" style="margin:16px">
          <div class="fh-explain-title">¿Qué mide?</div>
          <p class="fh-explain-text">Evalúa si <strong>gastaste dentro de lo que planeaste</strong>. Para cada categoría compara el gasto real contra el monto asignado en el presupuesto.</p>
          <div class="fh-formula-box">
            <code>Por categoría: min(1, asignado / gastado)</code><br>
            <code>Puntaje = promedio × 100</code>
          </div>
          <div class="fh-scale">
            <span style="color:var(--color-success)">≥ 80 Excelente</span>
            <span style="color:var(--color-warning)">60–79 Regular</span>
            <span style="color:var(--color-danger)">< 60 Crítico</span>
          </div>
        </div>
      </div>

      <!-- Rule explanation -->
      <div class="card" style="display:flex;flex-direction:column">
        <div style="padding:20px 20px 0">
          <div class="fh-label-chip" style="background:rgba(16,185,129,0.15);color:#34d399">Sub-puntaje 2</div>
          <div style="display:flex;align-items:center;gap:10px;margin-top:8px;margin-bottom:4px">
            <span style="font-size:1.0625rem;font-weight:700;color:var(--text-primary)">Distribución</span>
            ${scorePill(rule)}
          </div>
          <div class="fh-mini-gauge" style="margin-bottom:0">
            <div style="height:100%;width:${rule}%;background:${scoreColor(rule)};border-radius:inherit;transition:width .5s"></div>
          </div>
        </div>
        <div class="fh-explain-box" style="margin:16px">
          <div class="fh-explain-title">¿Qué mide?</div>
          <p class="fh-explain-text">Evalúa si tu <strong>distribución del gasto sigue la regla ${targets.needs}/${targets.wants}/${targets.savings}</strong>. Penaliza cuando una categoría se aleja mucho de su objetivo.</p>
          <div class="fh-formula-box">
            <code>Desviación = |real% − objetivo%| / objetivo%</code><br>
            <code>Puntaje = (1 − desviación) × 100</code>
          </div>
          <div class="fh-scale">
            <span style="color:var(--color-success)">≥ 80 En meta</span>
            <span style="color:var(--color-warning)">60–79 Cerca</span>
            <span style="color:var(--color-danger)">< 60 Lejos</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── REGLA 50/30/20 EXPLANATION ──────────────────────────────────── -->
    <div class="fh-rule-banner" style="margin-bottom:24px">
      <div class="fh-rule-banner-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        ¿Qué es la Regla ${targets.needs}/${targets.wants}/${targets.savings}?
      </div>
      <p class="fh-rule-banner-text">Una guía de distribución del ingreso mensual. Divide tu sueldo en tres grandes grupos según su propósito:</p>
      <div class="fh-rule-pills">
        <div class="fh-rule-pill" style="border-color:rgba(8,145,178,0.4);background:rgba(8,145,178,0.08)">
          <span class="fh-rule-pill-pct" style="color:#22d3ee">${targets.needs}%</span>
          <span class="fh-rule-pill-label">Necesidades</span>
          <span class="fh-rule-pill-desc">Gastos fijos e ineludibles: vivienda, comida, transporte, servicios públicos.</span>
        </div>
        <div class="fh-rule-pill" style="border-color:rgba(217,119,6,0.4);background:rgba(217,119,6,0.08)">
          <span class="fh-rule-pill-pct" style="color:#fbbf24">${targets.wants}%</span>
          <span class="fh-rule-pill-label">Deseos</span>
          <span class="fh-rule-pill-desc">Gastos opcionales: entretenimiento, salidas, suscripciones, ropa no esencial.</span>
        </div>
        <div class="fh-rule-pill" style="border-color:rgba(5,150,105,0.4);background:rgba(5,150,105,0.08)">
          <span class="fh-rule-pill-pct" style="color:#34d399">${targets.savings}%</span>
          <span class="fh-rule-pill-label">Ahorro / Deudas</span>
          <span class="fh-rule-pill-desc">Fondo de emergencia, inversión y pago de deudas por encima del mínimo.</span>
        </div>
      </div>
    </div>

    <!-- ── BUCKET CARDS ────────────────────────────────────────────────── -->
    <div class="section-grid cols-3" style="margin-bottom:24px">
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
    <div class="card" style="margin-bottom:24px">
      <div class="card-header">
        <span class="card-title">${income.total_income > 0 ? 'Distribución Real vs. Objetivo (% del ingreso)' : 'Distribución del Presupuesto Asignado'}</span>
        <span style="font-size:0.75rem;color:var(--text-soft)">Barras claras = objetivo</span>
      </div>
      <div class="card-body" style="height:260px;position:relative">
        <canvas id="fhChart"></canvas>
      </div>
    </div>

    <style>
      .fh-big-score { font-family:var(--font-display);font-size:3.75rem;font-weight:800;line-height:1;letter-spacing:-0.03em }
      .fh-grade-badge { display:inline-block;font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:20px }
      .fh-label-chip { display:inline-block;font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;padding:3px 8px;border-radius:20px;background:rgba(255,255,255,0.07);color:var(--text-soft) }
      .fh-explain-box { background:rgba(255,255,255,0.03);border:1px solid var(--border-muted);border-radius:10px;padding:12px 14px }
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
      .fh-rule-pill-pct { font-family:var(--font-mono);font-size:1.5rem;font-weight:800;line-height:1 }
      .fh-rule-pill-label { font-size:0.75rem;font-weight:700;color:var(--text-primary) }
      .fh-rule-pill-desc { font-size:0.7rem;color:var(--text-soft);line-height:1.45;margin-top:2px }
      .fh-bucket-def { margin-top:10px;padding-top:10px;border-top:1px solid var(--border-muted) }
      .fh-bucket-def-text { font-size:0.7rem;color:var(--text-soft);line-height:1.45 }
      .fh-insights-grid { display:flex;flex-direction:column;gap:10px }
      .fh-insight-row { display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:8px;border:1px solid }
      .fh-insight-icon { width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:800;flex-shrink:0;margin-top:1px }
      @media (max-width:768px) {
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

  const ctx = container.querySelector('#fhChart');
  if (ctx) {
    _chart?.destroy();
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
              backgroundColor: ['rgba(8,145,178,0.85)', 'rgba(217,119,6,0.85)', 'rgba(5,150,105,0.85)'],
              borderRadius: 6,
            },
            {
              label: 'Objetivo (%)',
              data: [targets.needs, targets.wants, targets.savings],
              backgroundColor: ['rgba(8,145,178,0.15)', 'rgba(217,119,6,0.15)', 'rgba(5,150,105,0.15)'],
              borderColor:     ['rgba(8,145,178,0.5)', 'rgba(217,119,6,0.5)', 'rgba(5,150,105,0.5)'],
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
              backgroundColor: ['rgba(8,145,178,0.85)', 'rgba(217,119,6,0.85)', 'rgba(5,150,105,0.85)'],
              borderRadius: 6,
            },
            {
              label: 'Objetivo (%)',
              data: [targets.needs, targets.wants, targets.savings],
              backgroundColor: ['rgba(8,145,178,0.15)', 'rgba(217,119,6,0.15)', 'rgba(5,150,105,0.15)'],
              borderColor:     ['rgba(8,145,178,0.5)', 'rgba(217,119,6,0.5)', 'rgba(5,150,105,0.5)'],
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
  return `<span style="font-family:var(--font-mono);font-size:1.25rem;font-weight:700;color:${color}">${(v ?? 0).toFixed(0)}<span style="font-size:0.75rem;opacity:0.6">/100</span></span>`;
}

function scoreGauge(value, color) {
  const pct = Math.min(100, Math.max(0, value));
  return `
    <div style="margin:12px 0 6px">
      <div style="height:8px;background:var(--border-muted);border-radius:4px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:inherit;transition:width .6s cubic-bezier(.4,0,.2,1)"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--text-soft);margin-top:4px">
        <span>0</span><span>Crítico</span><span>Regular</span><span>Excelente</span><span>100</span>
      </div>
    </div>`;
}

function miniScoreExplain(label, value, description) {
  const v = value ?? 0;
  const color = scoreColor(v);
  return `
    <div style="padding:8px 10px;background:rgba(0,0,0,0.2);border-radius:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span style="font-size:0.7875rem;font-weight:600;color:var(--text-primary)">${label}</span>
        <span style="font-family:var(--font-mono);font-size:0.875rem;font-weight:700;color:${color}">${v.toFixed(0)}</span>
      </div>
      <div style="font-size:0.7rem;color:var(--text-soft);line-height:1.4">${description}</div>
      <div style="margin-top:5px;height:3px;background:var(--border-muted);border-radius:2px;overflow:hidden">
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

  return `
    <div class="card" style="display:flex;flex-direction:column">
      <div style="padding:18px 20px 0">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
          <div>
            <div class="fh-label-chip" style="background:${barColor.replace('0.8', '0.15')};color:${accentColor};margin-bottom:6px">${label}</div>
            <div style="font-family:var(--font-mono);font-size:2rem;font-weight:800;color:${accentColor};line-height:1">${actual.toFixed(1)}<span style="font-size:1rem;opacity:0.7">%</span></div>
            <div style="font-size:0.7rem;color:var(--text-soft);margin-top:2px">del presupuesto asignado</div>
          </div>
          <div style="text-align:right">
            <span class="badge ${badgeClass}" style="font-size:0.65rem">${badgeLabel}</span>
            <div style="font-size:0.65rem;color:var(--text-soft);margin-top:4px">Objetivo: ${targetPct}%</div>
            <div style="font-size:0.7rem;color:${scoreColor(ruleScore)};font-family:var(--font-mono);font-weight:700;margin-top:2px">${ruleScore}/100</div>
          </div>
        </div>

        <!-- Progress -->
        <div style="margin-bottom:6px">
          <div style="height:6px;background:var(--border-muted);border-radius:3px;overflow:hidden">
            <div style="height:100%;width:${fillPct}%;background:${barColor};border-radius:inherit;transition:width .5s"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--text-soft);margin-top:3px">
            <span>Gastado: <span style="font-family:var(--font-mono)">${fmtCurrency(b.spent, currency)}</span></span>
            <span>Asignado: <span style="font-family:var(--font-mono)">${fmtCurrency(b.assigned, currency)}</span></span>
          </div>
        </div>
      </div>

      <!-- Definition box -->
      <div class="fh-bucket-def" style="margin:12px 20px 16px;padding-top:10px">
        <div class="fh-explain-title">¿Qué incluye?</div>
        <p class="fh-bucket-def-text">${description}</p>
      </div>

      <!-- Category breakdown -->
      ${b.categories?.length ? categoriesList(b.categories, currency, accentColor) : ''}
    </div>`;
}

function categoriesList(cats, currency, accentColor) {
  return `
    <div style="border-top:1px solid var(--border-muted);padding:10px 20px 16px;display:flex;flex-direction:column;gap:5px">
      <div class="fh-explain-title" style="margin-bottom:4px">Detalle por categoría</div>
      ${cats.slice(0, 6).map(c => `
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:0.75rem;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:60%">${sanitize(c.category_name ?? '—')}</span>
          <span style="font-family:var(--font-mono);font-size:0.75rem;color:var(--text-secondary)">${fmtCurrency(c.spent, currency)}</span>
        </div>`).join('')}
      ${cats.length > 6 ? `<div style="font-size:0.65rem;color:var(--text-soft);text-align:right;margin-top:2px">+${cats.length - 6} más</div>` : ''}
    </div>`;
}

function insightsSection(insights) {
  const good = insights.filter(i => i.kind === 'good');
  const warn = insights.filter(i => i.kind === 'warn');
  const bad  = insights.filter(i => i.kind === 'bad');

  return `
    <div class="card" style="margin-bottom:24px">
      <div class="card-header">
        <span class="card-title">Señales del mes</span>
        <span style="font-size:0.75rem;color:var(--text-soft)">${insights.length} observación${insights.length !== 1 ? 'es' : ''}</span>
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
  const color  = isGood ? 'var(--color-success)' : isWarn ? 'var(--color-warning)' : 'var(--color-danger)';
  const bg     = isGood ? 'rgba(5,150,105,0.06)' : isWarn ? 'rgba(217,119,6,0.06)' : 'rgba(220,38,38,0.06)';
  const border = isGood ? 'rgba(5,150,105,0.2)' : isWarn ? 'rgba(217,119,6,0.2)' : 'rgba(220,38,38,0.2)';
  const icon   = isGood ? '✓' : isWarn ? '!' : '✗';
  return `
    <div class="fh-insight-row" style="background:${bg};border-color:${border}">
      <div class="fh-insight-icon" style="background:${bg.replace('0.06', '0.15')};color:${color}">${icon}</div>
      <div>
        <div style="font-size:0.8125rem;font-weight:600;color:var(--text-primary)">${sanitize(ins.message)}</div>
        ${ins.detail ? `<div style="font-size:0.75rem;color:var(--text-soft);margin-top:2px;line-height:1.4">${sanitize(ins.detail)}</div>` : ''}
      </div>
    </div>`;
}

function incomeSection(income, targets, currency) {
  const ib    = income.buckets ?? {};
  const score = income.score ?? 0;
  const gradeColor = scoreColor(score);

  return `
    <div class="card" style="margin-bottom:24px">
      <div class="card-header">
        <span class="card-title">Análisis por Ingreso Real</span>
        <span style="font-size:0.75rem;color:var(--text-soft)">Ingreso total: ${fmtCurrency(income.total_income, currency)}</span>
      </div>
      <div class="card-body">
        <div class="fh-explain-box" style="margin-bottom:16px">
          <div class="fh-explain-title">¿Cómo se lee esta sección?</div>
          <p class="fh-explain-text">Aquí el análisis usa tu <strong>ingreso real del mes</strong> (en lugar del presupuesto asignado) para medir qué porcentaje de tu sueldo fue a cada grupo. Esto permite comparar contra la regla ${targets.needs}/${targets.wants}/${targets.savings} de forma más precisa.</p>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px">
          ${incomeStatBox('Ingreso', income.total_income, currency, 'var(--color-success)')}
          ${incomeStatBox('Gastado', income.total_spent, currency, 'var(--color-danger)')}
          ${incomeStatBox('Sin usar', income.total_income - income.total_spent, currency,
            (income.total_income - income.total_spent) >= 0 ? 'var(--color-success)' : 'var(--color-danger)')}
          <div style="text-align:center">
            <div style="font-size:0.65rem;color:var(--text-soft);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em">Puntaje regla</div>
            <div style="font-family:var(--font-mono);font-size:1.75rem;font-weight:800;color:${gradeColor}">${score.toFixed(0)}</div>
            <div style="font-size:0.65rem;color:var(--text-soft)">Grado ${income.grade ?? '—'}</div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
          ${incomeBucketRow('Necesidades', ib.needs, targets.needs, 'rgba(8,145,178,0.8)', '#22d3ee')}
          ${incomeBucketRow('Deseos', ib.wants, targets.wants, 'rgba(217,119,6,0.8)', '#fbbf24')}
          ${incomeBucketRow('Ahorro', ib.savings, targets.savings, 'rgba(5,150,105,0.8)', '#34d399')}
        </div>
      </div>
    </div>`;
}

function incomeStatBox(label, value, currency, color) {
  return `
    <div style="text-align:center;padding:10px;background:rgba(255,255,255,0.03);border-radius:8px;border:1px solid var(--border-muted)">
      <div style="font-size:0.65rem;color:var(--text-soft);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em">${label}</div>
      <div style="font-family:var(--font-mono);font-size:0.9375rem;font-weight:700;color:${color}">${fmtCurrency(value, currency)}</div>
    </div>`;
}

function incomeBucketRow(label, b, targetPct, barColor, accentColor) {
  if (!b) return '';
  const pct  = b.pct_of_income ?? 0;
  const diff = pct - targetPct;
  const isGood = Math.abs(diff) <= 5;
  const isWarn = !isGood && Math.abs(diff) <= 15;
  return `
    <div style="background:rgba(255,255,255,0.03);border:1px solid var(--border-muted);border-radius:10px;padding:12px 14px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:0.8125rem;font-weight:600;color:${accentColor}">${label}</span>
        <span class="badge ${isGood ? 'badge-success' : isWarn ? 'badge-warning' : 'badge-danger'}" style="font-size:0.65rem">
          ${pct.toFixed(1)}% / ${targetPct}%
        </span>
      </div>
      <div style="height:5px;background:var(--border-muted);border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${Math.min(100, pct / (targetPct || 1) * 100)}%;background:${barColor};border-radius:inherit;transition:width .4s"></div>
      </div>
      <div style="font-size:0.7rem;color:var(--text-soft);margin-top:4px">${fmtCurrency(b.amount ?? 0, 'COP')} este mes</div>
    </div>`;
}

function overBudgetSection(items, currency) {
  return `
    <div class="card" style="margin-bottom:24px">
      <div class="card-header">
        <span class="card-title" style="color:var(--color-danger)">⚠ Categorías Excedidas</span>
        <span class="badge badge-danger">${items.length}</span>
      </div>
      <div class="fh-explain-box" style="margin:0 20px 16px;margin-top:-4px">
        <p class="fh-explain-text">Estas categorías gastaron <strong>más de lo asignado</strong> este mes. Cada una resta puntos al puntaje de Cumplimiento.</p>
      </div>
      <div class="card-body" style="padding-top:0">
        <table>
          <thead>
            <tr>
              <th>Categoría</th>
              <th>Grupo</th>
              <th class="td-right">Asignado</th>
              <th class="td-right">Gastado</th>
              <th class="td-right">Exceso</th>
              <th class="td-right">%</th>
            </tr>
          </thead>
          <tbody>
            ${items.map(c => `
              <tr>
                <td style="font-size:0.8125rem;font-weight:500">${sanitize(c.category_name ?? '—')}</td>
                <td style="font-size:0.75rem;color:var(--text-soft)">${sanitize(c.group_name ?? '—')}</td>
                <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(c.assigned, currency)}</td>
                <td class="td-right td-mono" style="font-size:0.8rem">${fmtCurrency(c.spent, currency)}</td>
                <td class="td-right td-mono" style="font-size:0.8rem;color:var(--color-danger);font-weight:600">${fmtCurrency(c.overspend, currency)}</td>
                <td class="td-right" style="font-size:0.8rem;color:var(--color-danger)">${c.overspend_pct?.toFixed(1) ?? '—'}%</td>
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
      <div style="display:grid;grid-template-columns:1.2rem 1fr auto;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border-muted)">
        <span style="font-size:0.85rem">${light}</span>
        <div>
          <div style="font-size:0.8rem;font-weight:500">${sanitize(c.category_name)}</div>
          <div style="height:4px;background:var(--border-muted);border-radius:2px;margin-top:4px">
            <div style="height:100%;width:${barWidth}%;background:${barColor};border-radius:2px;transition:width .3s"></div>
          </div>
        </div>
        <div style="text-align:right;min-width:110px">
          <div style="font-size:0.75rem;font-family:var(--font-mono);color:var(--text-secondary)">${fmtCurrency(spent, currency)}</div>
          <div style="font-size:0.68rem;color:var(--text-soft)">${assigned > 0 ? pct.toFixed(0) + '% de ' + fmtCurrency(assigned, currency) : 'sin asignar'}</div>
        </div>
      </div>`;
  }).join('');

  return `
    <div class="card" style="margin-bottom:24px">
      <div class="card-header">
        <span class="card-title">Semáforo por Categoría</span>
        <span style="font-size:0.72rem;color:var(--text-soft)">🟢 OK · 🟡 Precaución · 🔴 Excedido</span>
      </div>
      <div class="card-body" style="padding-top:0">${rows}</div>
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
