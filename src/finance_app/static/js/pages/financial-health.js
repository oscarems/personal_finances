import * as api from '../api/client.js';
import { fmtCurrency, fmtPercent, sanitize, currentMonth, fmtMonthLabel, prevMonth, nextMonth } from '../utils.js';
import { loadingState, showError } from '../components/pageState.js';

export const title = 'Salud Financiera';

let _month = currentMonth();
let _chart = null;

export async function mount(container) {
  container.innerHTML = loadingState();
  await load(container);
}

export function cleanup() { _chart?.destroy(); _chart = null; }

async function load(container) {
  try {
    const data = await api.reports.financialHealth({ month: _month });
    render(container, data);
  } catch (err) {
    showError(container, {
      title: 'Salud Financiera',
      message: err.message,
      onRetry: () => {
        container.innerHTML = loadingState();
        load(container);
      },
    });
  }
}

function render(container, data) {
  const scores     = data.scores ?? {};
  const buckets    = data.buckets ?? {};
  const targets    = data.targets ?? { needs: 50, wants: 30, savings: 20 };
  const insights   = data.insights ?? [];
  const overBudget = data.over_budget_categories ?? [];
  const income     = data.income_analysis ?? {};
  const totals     = data.totals ?? {};
  const currency   = data.currency?.code ?? 'COP';

  const overall  = scores.overall ?? null;
  const gradeInfo = getGradeInfo(overall);

  const goods    = insights.filter(i => i.kind === 'good');
  const actions  = buildActions(buckets, targets, overBudget, totals, income, currency);

  container.innerHTML = `
    ${fhStyles()}

    <div class="fh-page">

      <!-- NAVEGACIÓN DE MES -->
      <div class="fh-nav">
        <button class="fh-nav-btn" id="fhPrev">‹</button>
        <span class="fh-nav-month">${fmtMonthLabel(_month)}</span>
        <button class="fh-nav-btn" id="fhNext">›</button>
      </div>

      ${overall == null ? emptyState() : `
        <!-- BLOQUE 1: CÓMO ESTÁS -->
        ${heroSection(overall, gradeInfo, totals, income, currency)}

        <!-- BLOQUE 2: QUÉ HACER AHORA -->
        ${actions.length ? actionsSection(actions) : goodJobSection(goods)}

        <!-- BLOQUE 3: TUS 3 BALDES -->
        ${bucketsSection(buckets, targets, income, currency)}

        <!-- BLOQUE 4: CATEGORÍAS PASADAS -->
        ${overBudget.length ? overBudgetSection(overBudget, currency) : ''}

        <!-- BLOQUE 5: LO QUE SÍ ESTÁ BIEN -->
        ${!actions.length && goods.length === 0 ? '' : goods.length ? goodsSection(goods) : ''}

        <!-- BLOQUE 6: DETALLE (colapsado) -->
        ${detailSection(buckets, currency)}
      `}

    </div>
  `;

  container.querySelector('#fhPrev')?.addEventListener('click', async () => {
    _month = prevMonth(_month); await load(container);
  });
  container.querySelector('#fhNext')?.addEventListener('click', async () => {
    _month = nextMonth(_month); await load(container);
  });
  container.querySelector('#fhDetailToggle')?.addEventListener('click', () => {
    const body = container.querySelector('#fhDetailBody');
    const btn  = container.querySelector('#fhDetailToggle');
    const open = body.style.display !== 'none';
    body.style.display = open ? 'none' : 'block';
    btn.textContent = open ? 'Ver todas las categorías ▾' : 'Ocultar ▴';
  });

  if (overall != null) mountBucketsChart(container, buckets, targets, income, currency);
}

// ── GRÁFICO DE TORTA (BLOQUE 3) ─────────────────────────────────────────────

function mountBucketsChart(container, buckets, targets, income, currency) {
  const canvas = container.querySelector('#fhBucketsChart');
  _chart?.destroy();
  _chart = null;
  if (!canvas || typeof Chart === 'undefined') return;

  const hasIncome = (income.total_income ?? 0) > 0;
  const keys = ['needs', 'wants', 'savings'];
  const values = keys.map(k => {
    const b = buckets[k];
    const ib = income.buckets?.[k];
    return hasIncome && ib ? (ib.pct_of_income ?? 0) : (b?.pct_of_assigned ?? 0);
  });
  const labels = keys.map(k => `${BUCKET_META[k].emoji} ${BUCKET_META[k].label}`);
  const colors = keys.map(k => BUCKET_META[k].color);

  const unassignedPct = Math.max(0, 100 - values.reduce((s, v) => s + v, 0));
  if (unassignedPct > 0.5) {
    keys.push('unassigned');
    values.push(unassignedPct);
    labels.push('⬜ No asignado');
    colors.push('#717971');
  }

  const style = getComputedStyle(container);
  const surface = style.getPropertyValue('--fin-surface').trim() || '#FFFFFF';
  const ink     = style.getPropertyValue('--fin-ink').trim() || '#161D19';
  const ink3    = style.getPropertyValue('--fin-ink-3').trim() || '#717971';
  const border  = style.getPropertyValue('--fin-border').trim() || 'rgba(28,27,23,0.15)';

  _chart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderWidth: 0,
        borderRadius: 10,
        spacing: 4,
        hoverOffset: 10,
        hoverBorderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '74%',
      radius: '92%',
      animation: { animateRotate: true, duration: 700, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: surface,
          titleColor: ink,
          bodyColor: ink3,
          borderColor: border,
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
          displayColors: true,
          boxPadding: 4,
          bodyFont: { size: 12 },
          titleFont: { size: 12, weight: '700' },
          callbacks: {
            label: (ctx) => {
              const k = keys[ctx.dataIndex];
              if (k === 'unassigned') {
                return ` ${ctx.parsed.toFixed(1)}% sin asignar a ningún balde`;
              }
              const target = targets[k] ?? 0;
              const b = buckets[k];
              const amount = k === 'savings' ? (b?.assigned ?? 0) : (b?.spent ?? 0);
              return [
                ` ${ctx.parsed.toFixed(1)}% (meta: ${target.toFixed(0)}%)`,
                ` ${fmtCurrency(amount, currency)}`,
              ];
            },
          },
        },
      },
    },
  });
}

// ── EMPTY STATE ───────────────────────────────────────────────────────────────

function emptyState() {
  return `
    <div class="fh-empty">
      <div class="fh-empty-emoji">📊</div>
      <div class="fh-empty-title">No hay datos este mes</div>
      <div class="fh-empty-sub">Registra transacciones o asigna montos en el presupuesto para ver tu diagnóstico.</div>
    </div>`;
}

// ── BLOQUE 1: HERO ────────────────────────────────────────────────────────────

function heroSection(overall, gradeInfo, totals, income, currency) {
  const surplus     = (income.total_income ?? 0) - (income.total_spent ?? 0);
  const hasIncome   = (income.total_income ?? 0) > 0;
  const surplusOk   = surplus >= 0;

  // Gauge SVG en círculo
  const radius = 54;
  const circ   = 2 * Math.PI * radius;
  const fill   = circ * (1 - Math.min(1, overall / 100));

  return `
    <div class="fh-hero">

      <!-- Gauge circular -->
      <div class="fh-gauge-wrap">
        <svg class="fh-gauge-svg" viewBox="0 0 140 140" width="140" height="140">
          <circle cx="70" cy="70" r="${radius}" fill="none" stroke="var(--fin-border)" stroke-width="10"/>
          <circle cx="70" cy="70" r="${radius}" fill="none"
            stroke="${gradeInfo.color}" stroke-width="10"
            stroke-dasharray="${circ}"
            stroke-dashoffset="${fill}"
            stroke-linecap="round"
            transform="rotate(-90 70 70)"
            style="transition: stroke-dashoffset .8s cubic-bezier(.4,0,.2,1)"
          />
          <text x="70" y="62" text-anchor="middle" fill="${gradeInfo.color}"
            font-size="30" font-weight="800" font-family="var(--font-display)">${Math.round(overall)}</text>
          <text x="70" y="80" text-anchor="middle" fill="var(--fin-ink-3)"
            font-size="10">/100</text>
        </svg>
        <div class="fh-gauge-face">${gradeInfo.face}</div>
      </div>

      <!-- Texto del veredicto -->
      <div class="fh-hero-text">
        <div class="fh-hero-label" style="color:${gradeInfo.color}">${gradeInfo.label}</div>
        <div class="fh-hero-msg">${gradeInfo.message}</div>
      </div>

      <!-- KPIs simples -->
      <div class="fh-kpis">
        <div class="fh-kpi">
          <div class="fh-kpi-icon">💸</div>
          <div class="fh-kpi-val">${fmtCurrency(totals.spent ?? 0, currency)}</div>
          <div class="fh-kpi-lbl">Gastado</div>
        </div>
        <div class="fh-kpi">
          <div class="fh-kpi-icon">📋</div>
          <div class="fh-kpi-val">${fmtCurrency(totals.assigned ?? 0, currency)}</div>
          <div class="fh-kpi-lbl">Presupuestado</div>
        </div>
        <div class="fh-kpi">
          <div class="fh-kpi-icon">${(totals.remaining ?? 0) >= 0 ? '✅' : '🚨'}</div>
          <div class="fh-kpi-val" style="color:${(totals.remaining ?? 0) >= 0 ? 'var(--fin-success)' : 'var(--fin-danger)'}">
            ${fmtCurrency(totals.remaining ?? 0, currency)}
          </div>
          <div class="fh-kpi-lbl">Disponible</div>
        </div>
        ${hasIncome ? `
        <div class="fh-kpi">
          <div class="fh-kpi-icon">${surplusOk ? '💰' : '🔴'}</div>
          <div class="fh-kpi-val" style="color:${surplusOk ? 'var(--fin-success)' : 'var(--fin-danger)'}">
            ${fmtCurrency(surplus, currency)}
          </div>
          <div class="fh-kpi-lbl">${surplusOk ? 'Superávit' : 'Déficit'}</div>
        </div>` : ''}
      </div>

    </div>`;
}

// ── BLOQUE 2A: ACCIONES ───────────────────────────────────────────────────────

function buildActions(buckets, targets, overBudget, totals, income, currency) {
  const actions = [];
  const hasIncome = (income.total_income ?? 0) > 0;

  // 1. Déficit del mes: gastaste más de lo que ingresó → lo más urgente posible
  if (hasIncome) {
    const deficit = (income.total_spent ?? 0) - (income.total_income ?? 0);
    if (deficit > 0) {
      actions.push({
        icon: '🆘',
        title: `Cerraste el mes en déficit: gastaste ${fmtCurrency(deficit, currency)} más de lo que ganaste`,
        detail: 'Revisa qué categorías dispararon el gasto y ajusta el presupuesto del próximo mes para que no se repita.',
        urgent: true,
      });
    }
  }

  // 2. Categorías de gasto excedidas → decir cuánto recortar y en qué
  const expenseOver = overBudget.filter(c => !c.is_savings);
  if (expenseOver.length) {
    const top = expenseOver[0];
    const extraTotal = expenseOver.reduce((s, c) => s + (c.overspend ?? 0), 0);
    const rest = expenseOver.length - 1;
    actions.push({
      icon: '✂️',
      title: `Recorta ${fmtCurrency(top.overspend ?? 0, currency)} en "${top.category_name}"`,
      detail: rest > 0
        ? `Te pasaste del presupuesto ahí, y en ${rest} categoría${rest > 1 ? 's' : ''} más — en total ${fmtCurrency(extraTotal, currency)} por encima de lo planeado. Baja el gasto o ajusta lo asignado el próximo mes.`
        : `Te pasaste del presupuesto en esta categoría. Baja el gasto los días que quedan o ajusta lo asignado el próximo mes.`,
      urgent: true,
    });
  }

  // 3. Categorías de ahorro que gastaron más de lo asignado este mes
  const savingsOver = overBudget.filter(c => c.is_savings);
  if (savingsOver.length) {
    const names = savingsOver.slice(0, 2).map(c => c.category_name).join(' y ');
    const extraTotal = savingsOver.reduce((s, c) => s + (c.overspend ?? 0), 0);
    actions.push({
      icon: '🏦',
      title: `Ajusta lo asignado a ${names} — gastaste ${fmtCurrency(extraTotal, currency)} de más este mes`,
      detail: 'Si fue un gasto puntual está bien, pero si se repite sube el monto asignado a esta meta el próximo mes.',
      urgent: true,
    });
  }

  // 4. Ahorro por debajo de la meta → decir cuánto asignar de más
  const sav = buckets.savings;
  const savPct = sav?.pct_of_assigned ?? 0;
  const savTarget = targets.savings ?? 20;
  if (sav && savPct < savTarget - 5 && totals.assigned > 0) {
    const gapAmount = (savTarget - savPct) / 100 * totals.assigned;
    actions.push({
      icon: '💰',
      title: (sav.assigned ?? 0) === 0
        ? `Asigna al menos ${fmtCurrency(gapAmount, currency)} a ahorro este mes`
        : `Sube tu ahorro en unos ${fmtCurrency(gapAmount, currency)} para llegar a tu meta de ${savTarget.toFixed(0)}%`,
      detail: `Ahora mismo estás ahorrando el ${savPct.toFixed(0)}% del presupuesto, y tu meta es ${savTarget.toFixed(0)}%.`,
      urgent: false,
    });
  }

  // 5. Necesidades por encima de la meta
  const needs = buckets.needs;
  const needsPct = needs?.pct_of_assigned ?? 0;
  const needsTarget = targets.needs ?? 50;
  if (needs && needsPct > needsTarget + 5 && totals.assigned > 0) {
    const overAmount = (needsPct - needsTarget) / 100 * totals.assigned;
    actions.push({
      icon: '🏠',
      title: `Tus gastos esenciales están ${fmtCurrency(overAmount, currency)} por encima de tu meta`,
      detail: `Estás en ${needsPct.toFixed(0)}% del presupuesto (meta: ${needsTarget.toFixed(0)}%). Revisa si hay gastos fijos (suscripciones, planes) que puedas renegociar o cancelar.`,
      urgent: false,
    });
  }

  // 6. Deseos por encima de la meta
  const wants = buckets.wants;
  const wantsPct = wants?.pct_of_assigned ?? 0;
  const wantsTarget = targets.wants ?? 30;
  if (wants && wantsPct > wantsTarget + 5 && totals.assigned > 0) {
    const overAmount = (wantsPct - wantsTarget) / 100 * totals.assigned;
    actions.push({
      icon: '🎉',
      title: `Recorta unos ${fmtCurrency(overAmount, currency)} en gastos de deseos este mes`,
      detail: `Estás en ${wantsPct.toFixed(0)}% del presupuesto (meta: ${wantsTarget.toFixed(0)}%). Elige 1-2 categorías de antojo/ocio para bajarle el ritmo.`,
      urgent: false,
    });
  }

  return actions.slice(0, 5);
}

function actionsSection(actions) {
  return `
    <div class="fh-section">
      <div class="fh-section-title">🎯 ¿Qué hacer ahora?</div>
      <div class="fh-actions-list">
        ${actions.map((a, i) => `
          <div class="fh-action ${a.urgent ? 'fh-action--urgent' : 'fh-action--warn'}">
            <div class="fh-action-num">${i + 1}</div>
            <div class="fh-action-icon">${a.icon}</div>
            <div class="fh-action-body">
              <div class="fh-action-title">${sanitize(a.title)}</div>
              ${a.detail ? `<div class="fh-action-detail">${sanitize(a.detail)}</div>` : ''}
            </div>
          </div>`).join('')}
      </div>
    </div>`;
}

function goodJobSection(goods) {
  return `
    <div class="fh-all-good">
      <div class="fh-all-good-emoji">🎉</div>
      <div>
        <div class="fh-all-good-title">¡Todo en orden este mes!</div>
        <div class="fh-all-good-sub">Sigue así. No tienes alertas ni categorías excedidas.</div>
      </div>
    </div>`;
}

// ── BLOQUE 3: BALDES 50/30/20 ─────────────────────────────────────────────────

const BUCKET_META = {
  needs:   { label: 'Necesidades',  emoji: '🏠', color: '#3B5B66', desc: 'Vivienda · Comida · Transporte', target_tip: 'max 50% de tus ingresos' },
  wants:   { label: 'Deseos',       emoji: '🎉', color: '#735142', desc: 'Entretenimiento · Restaurantes', target_tip: 'max 30% de tus ingresos' },
  savings: { label: 'Ahorro',       emoji: '💰', color: '#316342', desc: 'Inversión · Emergencias · Deudas', target_tip: 'mínimo 20% de tus ingresos' },
};

function bucketsSection(buckets, targets, income, currency) {
  const hasIncome = (income.total_income ?? 0) > 0;
  const base = hasIncome ? (income.total_income ?? 0) : null;

  return `
    <div class="fh-section">
      <div class="fh-section-title">📊 ¿Cómo distribuyes tu plata?</div>
      <div class="fh-section-sub">
        La torta muestra en qué se va cada peso ${hasIncome ? 'de tu ingreso' : 'de tu presupuesto'} este mes,
        comparado contra la regla ${targets.needs.toFixed(0)}/${targets.wants.toFixed(0)}/${targets.savings.toFixed(0)}
        (necesidades / deseos / ahorro)${hasIncome ? '. El gris muestra el % de tu ingreso que no asignaste a ningún balde' : ''}.
      </div>

      <div class="fh-pie-wrap">
        <div class="fh-pie-chart">
          <canvas id="fhBucketsChart"></canvas>
          ${base != null ? `
          <div class="fh-pie-center">
            <div class="fh-pie-center-lbl">Ingreso</div>
            <div class="fh-pie-center-val">${fmtCurrency(base, currency)}</div>
          </div>` : ''}
        </div>

        <div class="fh-pie-legend">
          ${['needs', 'wants', 'savings'].map(k => pieLegendRow(k, buckets[k], targets[k], income.buckets?.[k], hasIncome, currency)).join('')}
          ${unassignedLegendRow(buckets, targets, income, hasIncome, currency)}
        </div>
      </div>

      <div class="fh-buckets">
        ${['needs', 'wants', 'savings'].map(k => bucketCard(k, buckets[k], targets[k], income.buckets?.[k], hasIncome, currency)).join('')}
      </div>
    </div>`;
}

function pieLegendRow(key, b, targetPct, ib, hasIncome, currency) {
  const meta = BUCKET_META[key];
  if (!b) return '';

  const actualPct = hasIncome && ib ? (ib.pct_of_income ?? 0) : (b.pct_of_assigned ?? 0);
  const amount    = key === 'savings' ? (b.assigned ?? 0) : (b.spent ?? 0);
  const diff      = actualPct - targetPct;
  const absDiff   = Math.abs(diff);
  const isGood    = absDiff <= 5;
  const isWarn    = !isGood && absDiff <= 15;
  const statusColor = isGood ? 'var(--fin-success)' : isWarn ? 'var(--fin-amber)' : 'var(--fin-danger)';
  const statusText = isGood
    ? 'en meta'
    : `${diff > 0 ? '+' : '-'}${absDiff.toFixed(0)}pp vs meta`;

  return `
    <div class="fh-pie-leg-row">
      <span class="fh-pie-leg-dot" style="background:${meta.color}"></span>
      <div class="fh-pie-leg-body">
        <div class="fh-pie-leg-top">
          <span class="fh-pie-leg-name">${meta.emoji} ${meta.label}</span>
          <span class="fh-pie-leg-pct">${actualPct.toFixed(0)}%</span>
        </div>
        <div class="fh-pie-leg-sub">
          ${fmtCurrency(amount, currency)} · meta ${targetPct.toFixed(0)}% ·
          <span style="color:${statusColor};font-weight:600">${statusText}</span>
        </div>
        <div class="fh-pie-leg-bar">
          <div class="fh-pie-leg-bar-fg" style="width:${Math.min(100, actualPct)}%;background:${meta.color}"></div>
        </div>
      </div>
    </div>`;
}

function unassignedLegendRow(buckets, targets, income, hasIncome, currency) {
  if (!hasIncome) return '';

  const keys = ['needs', 'wants', 'savings'];
  const usedPct = keys.reduce((s, k) => {
    const b = buckets[k];
    const ib = income.buckets?.[k];
    return s + (ib ? (ib.pct_of_income ?? 0) : (b?.pct_of_assigned ?? 0));
  }, 0);
  const unassignedPct = Math.max(0, 100 - usedPct);
  if (unassignedPct <= 0.5) return '';

  const totalIncome = income.total_income ?? 0;
  const amount = totalIncome * (unassignedPct / 100);

  return `
    <div class="fh-pie-leg-row">
      <span class="fh-pie-leg-dot" style="background:#717971"></span>
      <div class="fh-pie-leg-body">
        <div class="fh-pie-leg-top">
          <span class="fh-pie-leg-name">⬜ No asignado</span>
          <span class="fh-pie-leg-pct">${unassignedPct.toFixed(0)}%</span>
        </div>
        <div class="fh-pie-leg-sub">
          ${fmtCurrency(amount, currency)} · ingreso sin asignar a ningún balde de presupuesto
        </div>
        <div class="fh-pie-leg-bar">
          <div class="fh-pie-leg-bar-fg" style="width:${Math.min(100, unassignedPct)}%;background:#717971"></div>
        </div>
      </div>
    </div>`;
}

function bucketCard(key, b, targetPct, ib, hasIncome, currency) {
  const meta = BUCKET_META[key];
  if (!b) return '';

  const actualPct = hasIncome && ib ? (ib.pct_of_income ?? 0) : (b.pct_of_assigned ?? 0);
  const spent     = b.spent ?? 0;
  const assigned  = b.assigned ?? 0;
  const isSaving  = key === 'savings';
  const available = assigned - spent;

  const diff     = actualPct - targetPct;
  const absDiff  = Math.abs(diff);
  const isGood   = absDiff <= 5;
  const isWarn   = !isGood && absDiff <= 15;

  let statusEmoji, statusText, statusColor;
  if (isGood) {
    statusEmoji = '✅'; statusText = 'En meta'; statusColor = 'var(--fin-success)';
  } else if (isWarn) {
    statusEmoji = '⚠️'; statusText = diff > 0 ? `${diff.toFixed(0)}% de más` : `${Math.abs(diff).toFixed(0)}% de menos`; statusColor = 'var(--fin-amber)';
  } else {
    statusEmoji = '🚨'; statusText = diff > 0 ? `${diff.toFixed(0)}% de más` : `${Math.abs(diff).toFixed(0)}% de menos`; statusColor = 'var(--fin-danger)';
  }

  // Barra: qué tan lleno está el balde
  const fillRatio = targetPct > 0 ? Math.min(1.3, actualPct / targetPct) : 0;
  const fillWidth = Math.min(100, fillRatio * 100);
  const isOver    = fillRatio > 1;
  const barColor  = isGood ? meta.color : isWarn ? 'var(--fin-amber)' : 'var(--fin-danger)';

  return `
    <div class="fh-bucket">
      <!-- Encabezado -->
      <div class="fh-bucket-top">
        <span class="fh-bucket-emoji">${meta.emoji}</span>
        <div class="fh-bucket-info">
          <div class="fh-bucket-name">${meta.label}</div>
          <div class="fh-bucket-desc">${meta.desc}</div>
        </div>
        <div class="fh-bucket-badge" style="color:${statusColor}">${statusEmoji} ${statusText}</div>
      </div>

      <!-- Barra de balde con % grande -->
      <div class="fh-balde-wrap">
        <div class="fh-balde-pct" style="color:${meta.color}">${actualPct.toFixed(0)}<span class="fh-balde-unit">%</span></div>
        <div class="fh-balde-target">meta: ${targetPct.toFixed(0)}%</div>
      </div>

      <div class="fh-balde-bar-bg">
        <div class="fh-balde-bar-fg" style="width:${fillWidth}%;background:${barColor}${isOver ? ';animation:fh-pulse 1.5s infinite' : ''}"></div>
        ${isOver ? `<div class="fh-balde-overflow-marker" style="left:${(1/fillRatio)*100}%"></div>` : ''}
      </div>
      <div class="fh-balde-tip" style="color:${meta.color}">${meta.target_tip}</div>

      <!-- Montos -->
      <div class="fh-balde-amounts">
        <div class="fh-ba">
          <div class="fh-ba-val">${fmtCurrency(spent, currency)}</div>
          <div class="fh-ba-lbl">Gastado</div>
        </div>
        <div class="fh-ba">
          <div class="fh-ba-val">${fmtCurrency(assigned, currency)}</div>
          <div class="fh-ba-lbl">Asignado</div>
        </div>
        <div class="fh-ba">
          <div class="fh-ba-val" style="color:${available >= 0 ? 'var(--fin-success)' : 'var(--fin-danger)'}">
            ${fmtCurrency(available, currency)}
          </div>
          <div class="fh-ba-lbl">Disponible</div>
        </div>
      </div>
    </div>`;
}

// ── BLOQUE 4: CATEGORÍAS EXCEDIDAS ───────────────────────────────────────────

function overBudgetSection(items, currency) {
  return `
    <div class="fh-section">
      <div class="fh-section-title" style="color:var(--fin-danger)">🚨 Te pasaste del presupuesto</div>
      <div class="fh-section-sub">En estas categorías gastaste más de lo que habías planeado.</div>
      <div class="fh-over-cards">
        ${items.map(c => {
          const pct = c.assigned > 0 ? ((c.spent / c.assigned) * 100) : 0;
          const extra = c.overspend ?? (c.spent - c.assigned);
          return `
            <div class="fh-over-card">
              <div class="fh-over-card-top">
                <div>
                  <div class="fh-over-card-name">${sanitize(c.category_name ?? '—')}</div>
                  <div class="fh-over-card-group">${sanitize(c.group_name ?? '—')}</div>
                </div>
                <div class="fh-over-card-extra">+${fmtCurrency(extra, currency)}</div>
              </div>
              <div class="fh-over-bar-bg">
                <div class="fh-over-bar-plan" style="width:${c.assigned > 0 ? Math.min(100,(c.assigned/c.spent)*100) : 0}%"></div>
              </div>
              <div class="fh-over-card-sub">
                Gastaste <strong>${fmtCurrency(c.spent, currency)}</strong> de <strong>${fmtCurrency(c.assigned, currency)}</strong> asignados
                (${pct.toFixed(0)}%)
              </div>
            </div>`;
        }).join('')}
      </div>
    </div>`;
}

// ── BLOQUE 5: LO QUE SÍ ESTÁ BIEN ────────────────────────────────────────────

function goodsSection(goods) {
  return `
    <div class="fh-section">
      <div class="fh-section-title">⭐ Lo que estás haciendo bien</div>
      <div class="fh-goods">
        ${goods.map(g => `
          <div class="fh-good-item">
            <span class="fh-good-check">✓</span>
            <span>${sanitize(g.message)}</span>
          </div>`).join('')}
      </div>
    </div>`;
}

// ── BLOQUE 6: DETALLE ─────────────────────────────────────────────────────────

function detailSection(buckets, currency) {
  const rows = [];
  for (const { key, color } of [
    { key: 'needs',   color: BUCKET_META.needs.color },
    { key: 'wants',   color: BUCKET_META.wants.color },
    { key: 'savings', color: BUCKET_META.savings.color },
  ]) {
    const b    = buckets[key];
    const cats = (b?.categories ?? []).filter(c => (c.assigned ?? 0) > 0 || (c.spent ?? 0) > 0);
    if (!cats.length) continue;

    rows.push(`<div class="fh-dcat-group" style="color:${color}">${BUCKET_META[key].emoji} ${BUCKET_META[key].label}</div>`);
    cats.forEach(c => {
      const assigned = c.assigned ?? 0;
      const spent    = c.spent ?? 0;
      const pct      = assigned > 0 ? (spent / assigned) * 100 : 0;
      const ok       = pct <= 80;
      const warn     = pct > 80 && pct <= 100;
      const dotColor = ok ? 'var(--fin-success)' : warn ? 'var(--fin-amber)' : 'var(--fin-danger)';

      rows.push(`
        <div class="fh-dcat-row">
          <span class="fh-dcat-dot" style="background:${dotColor}"></span>
          <span class="fh-dcat-name">${sanitize(c.category_name)}</span>
          <div class="fh-dcat-bar-bg">
            <div class="fh-dcat-bar-fg" style="width:${Math.min(100, pct)}%;background:${dotColor}"></div>
          </div>
          <span class="fh-dcat-pct">${assigned > 0 ? pct.toFixed(0) + '%' : '—'}</span>
          <span class="fh-dcat-amt">${fmtCurrency(spent, currency)}</span>
        </div>`);
    });
  }

  if (!rows.length) return '';

  return `
    <div class="fh-section fh-detail-section">
      <div class="fh-detail-toggle-bar">
        <div class="fh-section-title" style="margin:0">📂 Detalle por categoría</div>
        <button class="fh-toggle-btn" id="fhDetailToggle">Ver todas las categorías ▾</button>
      </div>
      <div id="fhDetailBody" style="display:none">
        <div class="fh-dcat-legend">
          <span><span class="fh-leg-dot" style="background:var(--fin-success)"></span>OK</span>
          <span><span class="fh-leg-dot" style="background:var(--fin-amber)"></span>Precaución</span>
          <span><span class="fh-leg-dot" style="background:var(--fin-danger)"></span>Excedido</span>
        </div>
        <div class="fh-dcat-list">${rows.join('')}</div>
      </div>
    </div>`;
}

// ── HELPERS ───────────────────────────────────────────────────────────────────

function getGradeInfo(score) {
  if (score == null) return { color: '#717971', face: '😶', label: '—', message: '' };
  if (score >= 90) return {
    color: '#316342', face: '🤩', label: '¡Excelente!',
    message: 'Tus finanzas están en forma. Sigue así y llegarás a tus metas.',
  };
  if (score >= 80) return {
    color: '#2F6B4F', face: '😄', label: '¡Muy bien!',
    message: 'Vas por buen camino. Hay pequeñas cosas que afinar.',
  };
  if (score >= 70) return {
    color: '#735142', face: '😊', label: 'Bien',
    message: 'Estás bien, pero hay oportunidades claras de mejorar.',
  };
  if (score >= 60) return {
    color: '#8A5A44', face: '😐', label: 'Regular',
    message: 'Algunas cosas necesitan atención. Lee las acciones de abajo.',
  };
  if (score >= 40) return {
    color: '#B4462F', face: '😟', label: 'Atención',
    message: 'Tu salud financiera necesita trabajo. No te preocupes, hay pasos claros.',
  };
  return {
    color: '#BA1A1A', face: '😨', label: '¡Alerta!',
    message: 'Situación crítica. Enfócate en las acciones de abajo hoy mismo.',
  };
}

// ── ESTILOS ───────────────────────────────────────────────────────────────────

function fhStyles() {
  return `<style>
    .fh-page { display: flex; flex-direction: column; gap: 24px; padding-bottom: 40px }

    /* Navegación */
    .fh-nav {
      display: flex; align-items: center; justify-content: center; gap: 16px;
    }
    .fh-nav-btn {
      background: var(--fin-surface); border: 1px solid var(--fin-border);
      color: var(--fin-ink-2); border-radius: 8px; width: 36px; height: 36px;
      font-size: 1.2rem; cursor: pointer; display: flex; align-items: center; justify-content: center;
      transition: background .15s;
    }
    .fh-nav-btn:hover { background: var(--fin-border) }
    .fh-nav-month { font-size: 1rem; font-weight: 600; color: var(--fin-ink) }

    /* Empty */
    .fh-empty {
      display: flex; flex-direction: column; align-items: center;
      gap: 12px; padding: 80px 24px; text-align: center;
    }
    .fh-empty-emoji { font-size: 3rem }
    .fh-empty-title { font-size: 1.1rem; font-weight: 700; color: var(--fin-ink) }
    .fh-empty-sub   { font-size: 0.875rem; color: var(--fin-ink-3); max-width: 360px }

    /* Hero */
    .fh-hero {
      background: var(--fin-surface);
      border: 1px solid var(--fin-border);
      border-radius: 18px;
      padding: 28px 28px 0;
      display: flex; flex-direction: column; align-items: center; gap: 16px;
      text-align: center;
    }
    .fh-gauge-wrap { position: relative; display: inline-block }
    .fh-gauge-svg  { display: block }
    .fh-gauge-face {
      position: absolute; bottom: -2px; right: -2px;
      font-size: 1.8rem; line-height: 1;
    }
    .fh-hero-text { display: flex; flex-direction: column; gap: 4px }
    .fh-hero-label { font-size: 1.5rem; font-weight: 800 }
    .fh-hero-msg   { font-size: 0.9rem; color: var(--fin-ink-2); max-width: 380px; line-height: 1.5 }

    .fh-kpis {
      display: flex; width: 100%;
      border-top: 1px solid var(--fin-border); margin-top: 8px;
    }
    .fh-kpi {
      flex: 1; padding: 16px 8px; text-align: center;
      border-right: 1px solid var(--fin-border);
    }
    .fh-kpi:last-child { border-right: none }
    .fh-kpi-icon { font-size: 1.3rem; margin-bottom: 4px }
    .fh-kpi-val  { font-family: var(--font-mono); font-size: 0.9rem; font-weight: 700; color: var(--fin-ink); margin-bottom: 2px }
    .fh-kpi-lbl  { font-size: 0.68rem; text-transform: uppercase; letter-spacing: .06em; color: var(--fin-ink-3) }

    /* Secciones genéricas */
    .fh-section {
      background: var(--fin-surface);
      border: 1px solid var(--fin-border);
      border-radius: 14px;
      padding: 20px 20px;
    }
    .fh-section-title {
      font-size: 0.95rem; font-weight: 700; color: var(--fin-ink);
      margin-bottom: 4px;
    }
    .fh-section-sub {
      font-size: 0.78rem; color: var(--fin-ink-3); margin-bottom: 16px; line-height: 1.4;
    }

    /* All good */
    .fh-all-good {
      display: flex; align-items: center; gap: 16px;
      background: rgba(5,150,105,0.07);
      border: 1px solid rgba(5,150,105,0.2);
      border-radius: 14px; padding: 20px 24px;
    }
    .fh-all-good-emoji { font-size: 2rem; flex-shrink: 0 }
    .fh-all-good-title { font-size: 1rem; font-weight: 700; color: var(--fin-success); margin-bottom: 2px }
    .fh-all-good-sub   { font-size: 0.82rem; color: var(--fin-ink-2) }

    /* Acciones */
    .fh-actions-list { display: flex; flex-direction: column; gap: 10px; margin-top: 14px }
    .fh-action {
      display: flex; align-items: flex-start; gap: 12px;
      border-radius: 10px; padding: 14px 16px;
      border-left: 3px solid;
    }
    .fh-action--urgent {
      background: rgba(220,38,38,0.06);
      border-color: var(--fin-danger);
    }
    .fh-action--warn {
      background: rgba(217,119,6,0.06);
      border-color: var(--fin-amber);
    }
    .fh-action-num {
      flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%;
      background: var(--fin-border); color: var(--fin-ink-3);
      font-size: 0.7rem; font-weight: 700;
      display: flex; align-items: center; justify-content: center;
    }
    .fh-action-icon { font-size: 1.2rem; flex-shrink: 0; margin-top: 1px }
    .fh-action-body { flex: 1 }
    .fh-action-title  { font-size: 0.875rem; font-weight: 600; color: var(--fin-ink); line-height: 1.4 }
    .fh-action-detail { font-size: 0.78rem; color: var(--fin-ink-3); margin-top: 3px; line-height: 1.4 }

    /* Torta de distribución */
    .fh-pie-wrap {
      display: flex; align-items: center; gap: 32px;
      margin-top: 18px; margin-bottom: 20px; flex-wrap: wrap;
    }
    .fh-pie-chart {
      position: relative; flex-shrink: 0;
      width: 208px; height: 208px;
      border-radius: 50%;
      filter: drop-shadow(0 8px 20px rgba(0,0,0,.28));
    }
    .fh-pie-chart::before {
      content: '';
      position: absolute; inset: 6%;
      border-radius: 50%;
      background: radial-gradient(circle at 50% 42%, rgba(255,255,255,.05), rgba(255,255,255,0) 60%);
      pointer-events: none;
    }
    .fh-pie-center {
      position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
      text-align: center; pointer-events: none;
    }
    .fh-pie-center-lbl { font-size: 0.64rem; color: var(--fin-ink-3); text-transform: uppercase; letter-spacing: .08em }
    .fh-pie-center-val { font-family: var(--font-mono); font-size: 0.95rem; font-weight: 700; color: var(--fin-ink); margin-top: 3px }

    .fh-pie-legend { flex: 0 1 380px; min-width: 240px; max-width: 420px; display: flex; flex-direction: column; gap: 8px }
    .fh-pie-leg-row {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 12px; border-radius: 10px;
      border: 1px solid transparent;
      transition: background .15s, border-color .15s;
    }
    .fh-pie-leg-row:hover { background: rgba(255,255,255,.03); border-color: var(--fin-border) }
    .fh-pie-leg-dot {
      width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0;
      box-shadow: 0 0 0 4px rgba(255,255,255,.05);
    }
    .fh-pie-leg-body { flex: 1; min-width: 0 }
    .fh-pie-leg-top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px }
    .fh-pie-leg-name { font-size: 0.83rem; font-weight: 600; color: var(--fin-ink) }
    .fh-pie-leg-pct  { font-family: var(--font-mono); font-size: 0.88rem; font-weight: 700; color: var(--fin-ink); flex-shrink: 0 }
    .fh-pie-leg-sub  { font-size: 0.72rem; color: var(--fin-ink-3); margin-top: 2px }
    .fh-pie-leg-bar {
      height: 4px; border-radius: 2px; background: var(--fin-border);
      margin-top: 7px; overflow: hidden;
    }
    .fh-pie-leg-bar-fg { height: 100%; border-radius: inherit; transition: width .6s ease }

    @media (max-width: 560px) {
      .fh-pie-wrap { justify-content: center }
      .fh-pie-chart { margin: 0 auto }
    }

    /* Baldes */
    .fh-buckets { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-top: 4px }

    .fh-bucket {
      background: var(--fin-bg);
      border: 1px solid var(--fin-border);
      border-radius: 12px;
      padding: 16px;
      display: flex; flex-direction: column; gap: 12px;
    }

    .fh-bucket-top {
      display: flex; align-items: flex-start; gap: 10px;
    }
    .fh-bucket-emoji { font-size: 1.6rem; flex-shrink: 0; margin-top: 2px }
    .fh-bucket-info  { flex: 1 }
    .fh-bucket-name  { font-size: 0.85rem; font-weight: 700; color: var(--fin-ink) }
    .fh-bucket-desc  { font-size: 0.68rem; color: var(--fin-ink-3); margin-top: 2px }
    .fh-bucket-badge { font-size: 0.72rem; font-weight: 700; white-space: nowrap; flex-shrink: 0; padding-top: 2px }

    .fh-balde-wrap { display: flex; align-items: baseline; gap: 8px }
    .fh-balde-pct  { font-family: var(--font-display); font-size: 2.4rem; font-weight: 800; line-height: 1; letter-spacing: -.03em }
    .fh-balde-unit { font-size: 1rem; opacity: .5 }
    .fh-balde-target {
      font-size: 0.68rem; color: var(--fin-ink-3);
      background: rgba(255,255,255,.04);
      border: 1px solid var(--fin-border);
      border-radius: 6px; padding: 2px 8px;
    }

    .fh-balde-bar-bg {
      height: 8px; background: var(--fin-border);
      border-radius: 4px; overflow: hidden; position: relative;
    }
    .fh-balde-bar-fg { height: 100%; border-radius: inherit; transition: width .6s ease }
    .fh-balde-overflow-marker {
      position: absolute; top: 0; height: 100%; width: 2px;
      background: rgba(255,255,255,0.4);
    }
    .fh-balde-tip { font-size: 0.66rem; color: var(--fin-ink-3) }

    .fh-balde-amounts {
      display: grid; grid-template-columns: repeat(3,1fr);
      border-top: 1px solid var(--fin-border);
      padding-top: 10px;
    }
    .fh-ba { display: flex; flex-direction: column; gap: 2px; text-align: center }
    .fh-ba:first-child { text-align: left }
    .fh-ba:last-child  { text-align: right }
    .fh-ba-val { font-family: var(--font-mono); font-size: 0.76rem; font-weight: 600; color: var(--fin-ink) }
    .fh-ba-lbl { font-size: 0.6rem; text-transform: uppercase; letter-spacing: .06em; color: var(--fin-ink-3) }

    /* Categorías excedidas */
    .fh-over-cards { display: flex; flex-direction: column; gap: 10px; margin-top: 12px }
    .fh-over-card {
      border: 1px solid rgba(220,38,38,0.2);
      border-radius: 10px; padding: 14px 16px;
      background: rgba(220,38,38,0.04);
      display: flex; flex-direction: column; gap: 8px;
    }
    .fh-over-card-top { display: flex; justify-content: space-between; align-items: flex-start }
    .fh-over-card-name  { font-size: 0.875rem; font-weight: 600; color: var(--fin-ink) }
    .fh-over-card-group { font-size: 0.7rem; color: var(--fin-ink-3); margin-top: 2px }
    .fh-over-card-extra { font-family: var(--font-mono); font-size: 0.95rem; font-weight: 700; color: var(--fin-danger) }
    .fh-over-bar-bg {
      height: 6px; background: rgba(220,38,38,0.15);
      border-radius: 3px; overflow: hidden;
    }
    .fh-over-bar-plan { height: 100%; background: rgba(220,38,38,0.5); border-radius: inherit }
    .fh-over-card-sub { font-size: 0.75rem; color: var(--fin-ink-3) }

    /* Lo que está bien */
    .fh-goods { display: flex; flex-direction: column; gap: 8px; margin-top: 12px }
    .fh-good-item {
      display: flex; align-items: center; gap: 10px;
      font-size: 0.85rem; color: var(--fin-ink-2);
    }
    .fh-good-check {
      width: 22px; height: 22px; border-radius: 50%;
      background: rgba(5,150,105,0.15);
      color: var(--fin-success); font-weight: 700; font-size: 0.8rem;
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }

    /* Detalle */
    .fh-detail-section { padding-bottom: 0 }
    .fh-detail-toggle-bar {
      display: flex; justify-content: space-between; align-items: center;
      padding-bottom: 16px;
    }
    .fh-toggle-btn {
      background: var(--fin-bg); border: 1px solid var(--fin-border);
      color: var(--fin-ink-2); border-radius: 8px; padding: 6px 14px;
      font-size: 0.78rem; cursor: pointer; transition: background .15s;
    }
    .fh-toggle-btn:hover { background: var(--fin-border) }

    .fh-dcat-legend {
      display: flex; gap: 16px; margin-bottom: 12px;
      font-size: 0.72rem; color: var(--fin-ink-3);
    }
    .fh-dcat-legend span { display: flex; align-items: center; gap: 5px }
    .fh-leg-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block }

    .fh-dcat-list { display: flex; flex-direction: column; gap: 5px; padding-bottom: 16px }
    .fh-dcat-group {
      font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: .08em; margin-top: 10px; margin-bottom: 4px;
    }
    .fh-dcat-group:first-child { margin-top: 0 }
    .fh-dcat-row {
      display: grid; grid-template-columns: 8px 1fr 90px 50px 90px;
      align-items: center; gap: 8px;
      padding: 7px 10px; border-radius: 7px;
      background: rgba(255,255,255,.02);
      border: 1px solid var(--fin-border);
    }
    .fh-dcat-dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0 }
    .fh-dcat-name { font-size: 0.78rem; font-weight: 500; color: var(--fin-ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis }
    .fh-dcat-bar-bg { height: 3px; background: var(--fin-border); border-radius: 2px; overflow: hidden }
    .fh-dcat-bar-fg { height: 100%; border-radius: inherit }
    .fh-dcat-pct { font-size: 0.68rem; color: var(--fin-ink-3); text-align: right }
    .fh-dcat-amt { font-family: var(--font-mono); font-size: 0.75rem; color: var(--fin-ink-2); text-align: right }

    /* Animación barra excedida */
    @keyframes fh-pulse {
      0%,100% { opacity: 1 } 50% { opacity: .6 }
    }

    /* Responsive */
    @media (max-width: 900px) {
      .fh-buckets { grid-template-columns: 1fr 1fr }
    }
    @media (max-width: 640px) {
      .fh-hero { padding: 20px 16px 0 }
      .fh-buckets { grid-template-columns: 1fr }
      .fh-kpis { flex-wrap: wrap }
      .fh-kpi { flex: 1 1 50%; border-bottom: 1px solid var(--fin-border) }
      .fh-section { padding: 16px }
      .fh-dcat-row { grid-template-columns: 8px 1fr 60px 40px }
      .fh-dcat-amt { display: none }
    }
  </style>`;
}
