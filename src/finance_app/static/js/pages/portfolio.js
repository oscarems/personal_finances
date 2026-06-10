import { fmtCurrency, fmtNumber, sanitize } from '../utils.js';

export const title = 'Portafolio de Inversiones';

const BASE = '/api/v1';
const api = {
  assets:      ()          => fetch(`${BASE}/portfolio/assets`).then(r => r.json()),
  createAsset: (data)      => fetch(`${BASE}/portfolio/assets`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(async r => { if (!r.ok) { const e = await r.json(); throw new Error(e.detail || `HTTP ${r.status}`); } return r.json(); }),
  addPrice:    (id, data)  => fetch(`${BASE}/portfolio/assets/${id}/prices`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(async r => { if (!r.ok) { const e = await r.json(); throw new Error(e.detail || `HTTP ${r.status}`); } return r.json(); }),
};

let allAssets = [];
let allocationChart = null;

const TIPO_LABELS = {
  accion: 'Acción', etf: 'ETF', cripto: 'Cripto', fondo: 'Fondo', otro: 'Otro',
};
const CLASE_LABELS = {
  renta_variable: 'Renta Variable', renta_fija: 'Renta Fija', liquidez: 'Liquidez', alternativo: 'Alternativo',
};
const CLASE_COLORS = {
  renta_variable: '#2D6A4F', renta_fija: '#3d5a80', liquidez: '#B7621A', alternativo: '#6B6560',
};

function formatCurrency(value, moneda) {
  return fmtCurrency(value, moneda || 'COP');
}

function formatPct(value) {
  const n = value ?? 0;
  const cls = n >= 0 ? 'pf-positive' : 'pf-negative';
  return `<span class="${cls}">${n >= 0 ? '+' : ''}${n.toFixed(2)}%</span>`;
}

async function loadAssets() {
  try {
    allAssets = await api.assets();
    renderKpis();
    renderTable(allAssets);
    loadAllocation();
  } catch (err) {
    const tbody = document.getElementById('assetsTableBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:32px;color:var(--color-danger);font-size:13px">${err.message}</td></tr>`;
  }
}

function renderKpis() {
  const container = document.getElementById('portfolioKpis');
  if (!container) return;

  const totalValor = allAssets.reduce((s, a) => s + (a.current_value ?? a.valor_actual ?? 0), 0);
  const totalCosto = allAssets.reduce((s, a) => {
    const u = a.units ?? a.unidades ?? 0;
    const pc = a.purchase_price ?? a.precio_compra ?? 0;
    return s + u * pc;
  }, 0);
  const ganancia = totalValor - totalCosto;
  const retorno = totalCosto > 0 ? (ganancia / totalCosto) * 100 : 0;
  const moneda = allAssets[0]?.currency ?? allAssets[0]?.moneda ?? 'COP';
  const gClass = ganancia >= 0 ? 'pf-positive' : 'pf-negative';

  container.innerHTML = `
    <div class="card p-5">
      <div class="pf-kpi-label">Valor Total</div>
      <div class="pf-kpi-value" style="font-family:var(--font-mono);font-size:1.2rem;font-weight:600;color:var(--text-primary)">${formatCurrency(totalValor, moneda)}</div>
    </div>
    <div class="card p-5">
      <div class="pf-kpi-label">Costo Base</div>
      <div class="pf-kpi-value" style="font-family:var(--font-mono);font-size:1.2rem;font-weight:600;color:var(--text-secondary)">${formatCurrency(totalCosto, moneda)}</div>
    </div>
    <div class="card p-5">
      <div class="pf-kpi-label">Ganancia / Pérdida</div>
      <div class="pf-kpi-value ${gClass}" style="font-family:var(--font-mono);font-size:1.2rem;font-weight:600">${formatCurrency(ganancia, moneda)}</div>
    </div>
    <div class="card p-5">
      <div class="pf-kpi-label">Retorno</div>
      <div style="font-family:var(--font-mono);font-size:1.2rem;font-weight:600">${formatPct(retorno)}</div>
    </div>
  `;

  container.querySelectorAll('.pf-kpi-label').forEach(el => {
    el.style.cssText = 'font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);margin-bottom:6px';
  });
}

function renderTable(assets) {
  const tbody = document.getElementById('assetsTableBody');
  const count = document.getElementById('assetCount');
  if (!tbody) return;

  if (count) count.textContent = `${assets.length} activo${assets.length !== 1 ? 's' : ''}`;

  if (!assets.length) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:40px;color:var(--text-soft);font-size:13px">
      <div style="margin-bottom:8px">📊</div>
      <div>Sin activos registrados</div>
    </td></tr>`;
    return;
  }

  tbody.innerHTML = assets.map(a => {
    const unidades = a.units ?? a.unidades ?? 0;
    const precioCompra = a.purchase_price ?? a.precio_compra ?? 0;
    const precioActual = a.current_price ?? a.precio_actual ?? precioCompra;
    const valorActual = a.current_value ?? (unidades * precioActual);
    const costo = unidades * precioCompra;
    const ganancia = valorActual - costo;
    const retorno = costo > 0 ? (ganancia / costo) * 100 : 0;
    const moneda = a.currency ?? a.moneda ?? 'COP';
    const tipo = a.asset_type ?? a.tipo ?? '';
    const simbolo = a.symbol ?? a.simbolo ?? '—';
    const nombre = a.name ?? a.nombre ?? '—';

    return `<tr>
      <td class="pf-symbol">${sanitize(simbolo)}</td>
      <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${sanitize(nombre)}</td>
      <td><span class="pf-badge">${TIPO_LABELS[tipo] ?? sanitize(tipo)}</span></td>
      <td class="text-right">${fmtNumber(unidades, 4)}</td>
      <td class="text-right">${formatCurrency(precioCompra, moneda)}</td>
      <td class="text-right">${formatCurrency(precioActual, moneda)}</td>
      <td class="text-right" style="font-weight:600">${formatCurrency(valorActual, moneda)}</td>
      <td class="text-right ${ganancia >= 0 ? 'pf-positive' : 'pf-negative'}">${formatCurrency(ganancia, moneda)}</td>
      <td class="text-right">${formatPct(retorno)}</td>
      <td>
        <button class="pf-action-btn" onclick="openPriceModal(${a.id}, '${sanitize(simbolo)}')">Precio</button>
      </td>
    </tr>`;
  }).join('');
}

function loadAllocation() {
  const canvas = document.getElementById('allocationChart');
  const legendEl = document.getElementById('allocationLegend');
  const emptyEl = document.getElementById('allocationEmpty');
  if (!canvas) return;

  if (!allAssets.length) {
    canvas.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }

  const byClase = {};
  for (const a of allAssets) {
    const clase = a.asset_class ?? a.clase ?? 'otro';
    const val = a.current_value ?? ((a.units ?? a.unidades ?? 0) * (a.current_price ?? a.precio_actual ?? a.purchase_price ?? a.precio_compra ?? 0));
    byClase[clase] = (byClase[clase] ?? 0) + val;
  }

  const labels = Object.keys(byClase).map(k => CLASE_LABELS[k] ?? k);
  const data = Object.values(byClase);
  const total = data.reduce((s, v) => s + v, 0);
  const colors = Object.keys(byClase).map(k => CLASE_COLORS[k] ?? '#A09890');

  if (allocationChart) allocationChart.destroy();

  const ctx = canvas.getContext('2d');
  allocationChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderWidth: 1.5, borderColor: getComputedStyle(document.documentElement).getPropertyValue('--fin-surface').trim() || '#fff', hoverOffset: 6 }],
    },
    options: {
      cutout: '68%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : 0}%`,
          },
        },
      },
    },
  });

  if (legendEl) {
    legendEl.innerHTML = Object.entries(byClase).map(([clase, val]) => {
      const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
      const color = CLASE_COLORS[clase] ?? '#A09890';
      return `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
        <div style="display:flex;align-items:center;gap:6px">
          <span style="width:10px;height:10px;border-radius:2px;background:${color};flex-shrink:0"></span>
          <span style="font-size:12px;color:var(--text-secondary)">${CLASE_LABELS[clase] ?? clase}</span>
        </div>
        <span style="font-size:11px;font-family:var(--font-mono);color:var(--text-soft)">${pct}%</span>
      </div>`;
    }).join('');
  }
}

window.openNewAssetModal = function() {
  const modal = document.getElementById('newAssetModal');
  if (!modal) return;
  document.getElementById('naFechaCompra').value = new Date().toISOString().split('T')[0];
  document.getElementById('naError').style.display = 'none';
  modal.style.display = 'block';
  document.body.style.overflow = 'hidden';
};

window.closeNewAssetModal = function() {
  const modal = document.getElementById('newAssetModal');
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = '';
};

window.submitNewAsset = async function() {
  const btn = document.getElementById('naSubmit');
  const errEl = document.getElementById('naError');
  errEl.style.display = 'none';

  const simbolo = document.getElementById('naSimbolo').value.trim();
  const nombre = document.getElementById('naNombre').value.trim();
  const tipo = document.getElementById('naTipo').value;
  const clase = document.getElementById('naClase').value;
  const unidades = parseFloat(document.getElementById('naUnidades').value);
  const precioCompra = parseFloat(document.getElementById('naPrecioCompra').value);
  const fechaCompra = document.getElementById('naFechaCompra').value;
  const moneda = document.getElementById('naMoneda').value;
  const notas = document.getElementById('naNotas').value.trim();

  if (!simbolo) { showErr(errEl, 'El símbolo es requerido'); return; }
  if (!nombre)  { showErr(errEl, 'El nombre es requerido'); return; }
  if (isNaN(unidades) || unidades <= 0) { showErr(errEl, 'Ingresa las unidades'); return; }
  if (isNaN(precioCompra) || precioCompra <= 0) { showErr(errEl, 'Ingresa el precio de compra'); return; }

  btn.disabled = true;
  btn.textContent = 'Guardando…';
  try {
    await api.createAsset({ symbol: simbolo, name: nombre, asset_type: tipo, asset_class: clase, units: unidades, purchase_price: precioCompra, purchase_date: fechaCompra || null, currency: moneda, notes: notas || null });
    window.closeNewAssetModal();
    ['naSimbolo','naNombre','naUnidades','naPrecioCompra','naNotas'].forEach(id => { document.getElementById(id).value = ''; });
    await loadAssets();
  } catch (err) {
    showErr(errEl, err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Guardar Activo';
  }
};

window.openPriceModal = function(assetId, simbolo) {
  const modal = document.getElementById('priceModal');
  if (!modal) return;
  document.getElementById('priceAssetId').value = assetId;
  document.getElementById('priceModalTitle').textContent = `Actualizar Precio — ${simbolo}`;
  document.getElementById('pFecha').value = new Date().toISOString().split('T')[0];
  document.getElementById('pPrecio').value = '';
  document.getElementById('pError').style.display = 'none';
  modal.style.display = 'block';
  document.body.style.overflow = 'hidden';
};

window.closePriceModal = function() {
  const modal = document.getElementById('priceModal');
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = '';
};

window.submitPrice = async function() {
  const btn = document.getElementById('pSubmit');
  const errEl = document.getElementById('pError');
  errEl.style.display = 'none';

  const assetId = parseInt(document.getElementById('priceAssetId').value);
  const fecha = document.getElementById('pFecha').value;
  const precio = parseFloat(document.getElementById('pPrecio').value);

  if (!fecha) { showErr(errEl, 'La fecha es requerida'); return; }
  if (isNaN(precio) || precio <= 0) { showErr(errEl, 'Ingresa un precio válido'); return; }

  btn.disabled = true;
  btn.textContent = 'Actualizando…';
  try {
    await api.addPrice(assetId, { date: fecha, price: precio });
    window.closePriceModal();
    await loadAssets();
  } catch (err) {
    showErr(errEl, err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Actualizar Precio';
  }
};

function showErr(el, msg) {
  el.textContent = msg;
  el.style.display = 'block';
}

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  await loadAssets();
}
