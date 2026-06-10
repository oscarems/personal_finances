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

    setText('valPatrimonio', formatCurrency(patrimonio, currency));
    setText('valGastos', formatCurrency(gastosAnuales, currency));
    setText('valIngreso', formatCurrency(ingresoPasivo, currency));
    setText('valRatio', `${ratioFire.toFixed(2)}×`);

    const aniosEl = document.getElementById('valAnios');
    if (aniosEl) {
      if (ratioFire >= 1) {
        aniosEl.textContent = '¡Independencia alcanzada!';
        aniosEl.style.color = 'var(--color-success)';
      } else if (aniosRestantes !== null && aniosRestantes < 999) {
        aniosEl.textContent = `~${Math.ceil(aniosRestantes)} años restantes`;
      } else {
        aniosEl.textContent = 'Años estimados';
      }
    }

    setText('targetFire', formatCurrency(objetivo, currency));
    setText('safeWithdrawal', formatCurrency(retiroSeguro, currency));
    setText('fireGap', gap > 0 ? `–${formatCurrency(gap, currency)}` : '¡Objetivo alcanzado!');

    const gapEl = document.getElementById('fireGap');
    if (gapEl) gapEl.style.color = gap > 0 ? 'var(--color-danger)' : 'var(--color-success)';

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

  let label, color, bg, borderColor, description;

  if (ratio >= 1.0) {
    label = 'Independencia alcanzada'; color = '#245740'; bg = 'rgba(45,106,79,0.09)'; borderColor = 'rgba(45,106,79,0.22)';
    description = 'Has alcanzado la independencia financiera. Tu patrimonio puede sostener tus gastos indefinidamente.';
  } else if (ratio >= 0.75) {
    label = 'Muy cerca'; color = '#245740'; bg = 'rgba(45,106,79,0.07)'; borderColor = 'rgba(45,106,79,0.18)';
    description = 'Estás en la recta final. Mantén el ritmo y llegarás pronto a tu objetivo FIRE.';
  } else if (ratio >= 0.5) {
    label = 'En camino'; color = '#9D5417'; bg = 'rgba(183,98,26,0.08)'; borderColor = 'rgba(183,98,26,0.20)';
    description = 'Buen progreso. Has recorrido más de la mitad del camino hacia la independencia financiera.';
  } else if (ratio >= 0.25) {
    label = 'Iniciando'; color = '#B7621A'; bg = 'rgba(183,98,26,0.06)'; borderColor = 'rgba(183,98,26,0.16)';
    description = 'Estás construyendo tu base. Cada ahorro te acerca más a tu libertad financiera.';
  } else {
    label = 'Comenzando'; color = '#6B6560'; bg = 'rgba(107,101,96,0.07)'; borderColor = 'rgba(107,101,96,0.18)';
    description = 'El viaje FIRE comienza con el primer paso. Define tu objetivo y empieza a invertir consistentemente.';
  }

  badge.style.cssText = `display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;padding:4px 12px;border-radius:100px;background:${bg};border:0.5px solid ${borderColor};color:${color}`;
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

  const trackColor = getComputedStyle(document.documentElement).getPropertyValue('--border-muted').trim() || 'rgba(26,23,20,0.10)';
  ctx.beginPath();
  ctx.arc(cx, cy, r, startAngle, endAngle);
  ctx.lineWidth = 18;
  ctx.strokeStyle = trackColor;
  ctx.lineCap = 'round';
  ctx.stroke();

  if (pct > 0) {
    const fillColor = pct >= 100 ? '#2D6A4F' : pct >= 75 ? '#2D6A4F' : pct >= 50 ? '#B7621A' : pct >= 25 ? '#B7621A' : '#6B6560';
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
