import { fmtCurrency, fmtNumber } from '../utils.js';

export const title = 'Independencia Financiera (FIRE)';

const BASE = '/api/v1';

async function fetchFire() {
  const res = await fetch(`${BASE}/fire`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function formatCurrency(value, currency) {
  return fmtCurrency(value ?? 0, currency ?? 'COP');
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

async function loadFireDashboard() {
  try {
    const data = await fetchFire();
    const currency = data.currency ?? 'COP';

    const patrimonio = data.investable_patrimony ?? data.patrimonio_invertible ?? 0;
    const gastosAnuales = data.annual_expenses ?? data.gastos_anuales ?? 0;
    const ingresoPasivo = data.passive_income ?? data.ingreso_pasivo ?? 0;
    const ratioFire = data.fire_ratio ?? 0;
    const aniosRestantes = data.years_to_fire ?? data.anios_restantes ?? null;
    const pct = Math.min(100, (ratioFire * 100));
    const objetivo = gastosAnuales * 25;
    const retiroSeguro = patrimonio * 0.04;
    const gap = Math.max(0, objetivo - patrimonio);

    // KPI amounts — add .amount class via element update
    const patrimonioEl = document.getElementById('valPatrimonio');
    if (patrimonioEl) { patrimonioEl.textContent = formatCurrency(patrimonio, currency); patrimonioEl.classList.add('amount'); }

    const gastosEl = document.getElementById('valGastos');
    if (gastosEl) { gastosEl.textContent = formatCurrency(gastosAnuales, currency); gastosEl.classList.add('amount'); }

    const ingresoEl = document.getElementById('valIngreso');
    if (ingresoEl) { ingresoEl.textContent = formatCurrency(ingresoPasivo, currency); ingresoEl.classList.add('amount'); }

    const ratioEl = document.getElementById('valRatio');
    if (ratioEl) {
      ratioEl.textContent = `${ratioFire.toFixed(2)}×`;
      ratioEl.classList.add('amount');
      ratioEl.classList.remove('text-success', 'text-danger', 'text-warning');
      ratioEl.classList.add(ratioFire >= 1 ? 'text-success' : '');
    }

    const aniosEl = document.getElementById('valAnios');
    if (aniosEl) {
      aniosEl.classList.remove('text-success', 'text-danger', 'text-warning');
      if (ratioFire >= 1) {
        aniosEl.textContent = '¡Independencia alcanzada!';
        aniosEl.classList.add('text-success');
      } else if (aniosRestantes !== null && aniosRestantes < 999) {
        const yr = Math.ceil(aniosRestantes);
        aniosEl.textContent = `~${yr} años restantes`;
        if (yr > 20)       aniosEl.classList.add('text-danger');
        else if (yr >= 10) aniosEl.classList.add('text-warning');
        else               aniosEl.classList.add('text-success');
      } else {
        aniosEl.textContent = 'Años estimados';
      }
    }

    const targetEl = document.getElementById('targetFire');
    if (targetEl) { targetEl.textContent = formatCurrency(objetivo, currency); targetEl.classList.add('amount'); }

    const retiroEl = document.getElementById('safeWithdrawal');
    if (retiroEl) { retiroEl.textContent = formatCurrency(retiroSeguro, currency); retiroEl.classList.add('amount'); }

    const gapEl = document.getElementById('fireGap');
    if (gapEl) {
      gapEl.textContent = gap > 0 ? `–${formatCurrency(gap, currency)}` : '¡Objetivo alcanzado!';
      gapEl.classList.add('amount');
      gapEl.classList.remove('text-success', 'text-danger');
      gapEl.classList.add(gap > 0 ? 'text-danger' : 'text-success');
    }

    renderStatusBadge(ratioFire);
    renderGauge(pct);

  } catch (err) {
    renderGaugeFallback();
    const badge = document.getElementById('fireStatusBadge');
    if (badge) badge.textContent = 'Error al cargar datos';
    console.error('[FIRE]', err.message);
  }
}

function renderStatusBadge(ratio) {
  const badge = document.getElementById('fireStatusBadge');
  const desc = document.getElementById('fireStatusDesc');
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

function renderGauge(pct) {
  const canvas = document.getElementById('fireGauge');
  if (!canvas) return;

  const pctEl = document.getElementById('firePctValue');
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
    // Map pct ranges to CSS token colours via getComputedStyle
    const root = getComputedStyle(document.documentElement);
    const successColor = root.getPropertyValue('--fin-success').trim() || '#2D6A4F';
    const amberColor   = root.getPropertyValue('--fin-amber').trim()   || '#B7621A';
    const mutedColor   = root.getPropertyValue('--fin-ink-3').trim()   || '#6B6560';
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

function renderGaugeFallback() {
  const pctEl = document.getElementById('firePctValue');
  if (pctEl) pctEl.textContent = '—';
}

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  await loadFireDashboard();
}
