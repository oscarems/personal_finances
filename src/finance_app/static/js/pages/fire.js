import * as api from '../api/client.js';
import { fmtCurrency, sanitize } from '../utils.js';

export const title = 'Independencia Financiera (FIRE)';

function formatCurrency(value, currency) {
  return fmtCurrency(value ?? 0, currency ?? 'COP');
}

function shellHtml() {
  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Independencia Financiera (FIRE)</h1>
        <p class="text-soft" style="margin:2px 0 0;font-size:0.8125rem">Ratio FIRE, cobertura y años estimados hacia la independencia</p>
      </div>
      <div class="page-header-actions">
        <span id="fireStatusBadge" class="badge text-muted">Cargando…</span>
      </div>
    </div>

    <p id="fireStatusDesc" class="text-soft mb-3" style="font-size:0.8125rem;max-width:640px"></p>

    <div class="kpi-grid mb-3">
      <div class="kpi-card">
        <div class="kpi-label">Patrimonio invertible</div>
        <div class="kpi-value amount" id="valPatrimonio">—</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Gastos anuales esenciales</div>
        <div class="kpi-value amount" id="valGastos">—</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Ingreso pasivo anual</div>
        <div class="kpi-value amount" id="valIngreso">—</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Ratio FIRE</div>
        <div class="kpi-value amount" id="valRatio">—</div>
      </div>
    </div>

    <div class="grid-2 mb-3">
      <div class="card">
        <div class="card-header"><span class="card-title">Progreso hacia FIRE</span></div>
        <div class="card-body" style="display:flex;flex-direction:column;align-items:center;padding-top:24px">
          <canvas id="fireGauge" width="200" height="110" aria-label="Medidor FIRE"></canvas>
          <div style="margin-top:8px;font-size:1.5rem;font-weight:700">
            <span class="amount" id="firePctValue">—</span><span class="text-soft" style="font-size:0.9rem">%</span>
          </div>
          <div class="text-soft" style="font-size:0.75rem;margin-top:4px" id="valAnios">Años estimados</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">Objetivo (regla 4%)</span></div>
        <div class="card-body">
          <div class="flex justify-between items-center mb-3" style="padding:10px 0;border-bottom:1px solid var(--fin-border)">
            <span class="text-soft" style="font-size:0.8125rem">Número FIRE (gastos × 25)</span>
            <span class="amount" id="targetFire" style="font-weight:600">—</span>
          </div>
          <div class="flex justify-between items-center mb-3" style="padding:10px 0;border-bottom:1px solid var(--fin-border)">
            <span class="text-soft" style="font-size:0.8125rem">Retiro seguro (4%)</span>
            <span class="amount" id="safeWithdrawal" style="font-weight:600">—</span>
          </div>
          <div class="flex justify-between items-center" style="padding:10px 0">
            <span class="text-soft" style="font-size:0.8125rem">Brecha al objetivo</span>
            <span class="amount" id="fireGap" style="font-weight:600">—</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

async function loadFireDashboard(container) {
  try {
    const data = await api.fire.dashboard();
    const currency = data.currency ?? data.moneda ?? 'COP';

    // Backend keys (fire_service) first; legacy EN/alt names as fallback
    const patrimonio = data.patrimonio_invertible ?? data.investable_patrimony ?? 0;
    const gastosAnuales = data.gastos_anuales_esenciales
      ?? data.gastos_anuales
      ?? data.annual_expenses
      ?? 0;
    const ingresoPasivo = data.ingreso_pasivo_anual
      ?? data.ingreso_pasivo
      ?? data.passive_income
      ?? 0;
    const ratioFire = data.ratio_fire ?? data.fire_ratio ?? 0;
    const independenciaPct = data.independencia_pct
      ?? Math.min(100, ratioFire * 100);
    const aniosRestantes = data.anos_restantes
      ?? data.anios_restantes
      ?? data.years_to_fire
      ?? null;

    const objetivo = gastosAnuales * 25;
    const retiroSeguro = patrimonio * 0.04;
    const gap = Math.max(0, objetivo - patrimonio);
    const pct = Math.min(100, independenciaPct);

    const setAmount = (id, text, extraClass) => {
      const el = container.querySelector(`#${id}`);
      if (!el) return;
      el.textContent = text;
      el.classList.add('amount');
      if (extraClass) {
        el.classList.remove('text-success', 'text-danger', 'text-warning');
        if (extraClass) el.classList.add(extraClass);
      }
    };

    setAmount('valPatrimonio', formatCurrency(patrimonio, currency));
    setAmount('valGastos', formatCurrency(gastosAnuales, currency));
    setAmount('valIngreso', formatCurrency(ingresoPasivo, currency));
    setAmount('valRatio', `${Number(ratioFire).toFixed(2)}×`, ratioFire >= 1 ? 'text-success' : null);
    setAmount('targetFire', formatCurrency(objetivo, currency));
    setAmount('safeWithdrawal', formatCurrency(retiroSeguro, currency));

    const gapEl = container.querySelector('#fireGap');
    if (gapEl) {
      gapEl.textContent = gap > 0 ? `–${formatCurrency(gap, currency)}` : '¡Objetivo alcanzado!';
      gapEl.classList.add('amount');
      gapEl.classList.remove('text-success', 'text-danger');
      gapEl.classList.add(gap > 0 ? 'text-danger' : 'text-success');
    }

    const aniosEl = container.querySelector('#valAnios');
    if (aniosEl) {
      aniosEl.classList.remove('text-success', 'text-danger', 'text-warning');
      if (ratioFire >= 1) {
        aniosEl.textContent = '¡Independencia alcanzada!';
        aniosEl.classList.add('text-success');
      } else if (aniosRestantes !== null && aniosRestantes < 999) {
        const yr = Math.ceil(aniosRestantes);
        aniosEl.textContent = `~${yr} años restantes`;
        if (yr > 20) aniosEl.classList.add('text-danger');
        else if (yr >= 10) aniosEl.classList.add('text-warning');
        else aniosEl.classList.add('text-success');
      } else {
        aniosEl.textContent = 'Años estimados';
      }
    }

    renderStatusBadge(container, ratioFire);
    renderGauge(container, pct);
  } catch (err) {
    renderGaugeFallback(container);
    const badge = container.querySelector('#fireStatusBadge');
    if (badge) badge.textContent = 'Error al cargar datos';
    const desc = container.querySelector('#fireStatusDesc');
    if (desc) desc.textContent = sanitize(err.message);
    console.error('[FIRE]', err.message);
  }
}

function renderStatusBadge(container, ratio) {
  const badge = container.querySelector('#fireStatusBadge');
  const desc = container.querySelector('#fireStatusDesc');
  if (!badge) return;

  let label, colorToken, description;

  if (ratio >= 1.0) {
    label = 'Independencia alcanzada';
    colorToken = 'text-success';
    description = 'Has alcanzado la independencia financiera. Tu patrimonio puede sostener tus gastos indefinidamente.';
  } else if (ratio >= 0.75) {
    label = 'Muy cerca';
    colorToken = 'text-success';
    description = 'Estás en la recta final. Mantén el ritmo y llegarás pronto a tu objetivo FIRE.';
  } else if (ratio >= 0.5) {
    label = 'En camino';
    colorToken = 'text-warning';
    description = 'Buen progreso. Has recorrido más de la mitad del camino hacia la independencia financiera.';
  } else if (ratio >= 0.25) {
    label = 'Iniciando';
    colorToken = 'text-warning';
    description = 'Estás construyendo tu base. Cada ahorro te acerca más a tu libertad financiera.';
  } else {
    label = 'Comenzando';
    colorToken = 'text-muted';
    description = 'El viaje FIRE comienza con el primer paso. Define tu objetivo y empieza a invertir consistentemente.';
  }

  badge.className = `badge ${colorToken}`;
  badge.style.cssText = 'display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;padding:4px 12px;border-radius:100px;border:0.5px solid var(--fin-border)';
  badge.textContent = label;

  if (desc) desc.textContent = description;
}

function renderGauge(container, pct) {
  const canvas = container.querySelector('#fireGauge');
  if (!canvas) return;

  const pctEl = container.querySelector('#firePctValue');
  if (pctEl) pctEl.textContent = pct.toFixed(1);

  const ctx = canvas.getContext('2d');
  const W = 200, H = 110;
  const cx = W / 2, cy = H - 10;
  const r = 80;
  const startAngle = Math.PI;
  const endAngle = 2 * Math.PI;
  const fillAngle = startAngle + (pct / 100) * Math.PI;

  ctx.clearRect(0, 0, W, H);

  const trackColor = getComputedStyle(document.documentElement).getPropertyValue('--fin-border').trim() || 'rgba(26,23,20,0.10)';
  ctx.beginPath();
  ctx.arc(cx, cy, r, startAngle, endAngle);
  ctx.lineWidth = 18;
  ctx.strokeStyle = trackColor;
  ctx.lineCap = 'round';
  ctx.stroke();

  if (pct > 0) {
    const root = getComputedStyle(document.documentElement);
    const successColor = root.getPropertyValue('--fin-success').trim() || '#316342';
    const amberColor = root.getPropertyValue('--fin-amber').trim() || '#735142';
    const mutedColor = root.getPropertyValue('--fin-ink-3').trim() || '#717971';
    const fillColor = pct >= 75 ? successColor : pct >= 25 ? amberColor : mutedColor;
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, fillAngle);
    ctx.lineWidth = 18;
    ctx.strokeStyle = fillColor;
    ctx.lineCap = 'round';
    ctx.stroke();
  }

  const milestones = [25, 50, 75, 100];
  milestones.forEach(m => {
    const angle = startAngle + (m / 100) * Math.PI;
    const x = cx + (r + 14) * Math.cos(angle);
    const y = cy + (r + 14) * Math.sin(angle);
    ctx.fillStyle = trackColor;
    ctx.font = '9px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${m}`, x, y);
  });
}

function renderGaugeFallback(container) {
  const pctEl = container.querySelector('#firePctValue');
  if (pctEl) pctEl.textContent = '—';
}

export async function mount(container) {
  container.innerHTML = shellHtml();
  await loadFireDashboard(container);
}
