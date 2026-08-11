import * as api from '../api/client.js';
import { fmtCurrency, fmtNumber, sanitize } from '../utils.js';
import { openModal } from '../components/modal.js';
import { emptyState } from '../components/emptyState.js';
import { sectionErrorState, bindRetry } from '../components/pageState.js';

export const title = 'Portafolio de Inversiones';

let allAssets = [];
let allocationChart = null;
let rootEl = null;

const TIPO_LABELS = {
  accion: 'Acción', etf: 'ETF', cripto: 'Cripto', fondo: 'Fondo', otro: 'Otro',
};
const CLASE_LABELS = {
  renta_variable: 'Renta Variable', renta_fija: 'Renta Fija', liquidez: 'Liquidez', alternativo: 'Alternativo',
};

function formatCurrency(value, moneda) {
  return fmtCurrency(value, moneda || 'COP');
}

function formatPct(value) {
  const n = value ?? 0;
  const cls = n >= 0 ? 'text-success' : 'text-danger';
  return `<span class="${cls} amount">${n >= 0 ? '+' : ''}${n.toFixed(2)}%</span>`;
}

function shellHtml() {
  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Portafolio de Inversiones</h1>
        <p class="text-soft" style="margin:2px 0 0;font-size:0.8125rem">Activos, valorización y asignación por clase</p>
      </div>
      <div class="page-header-actions">
        <button type="button" class="btn btn-primary" id="btnNewAsset">+ Activo</button>
      </div>
    </div>

    <div class="kpi-grid mb-3" id="portfolioKpis"></div>

    <div class="grid-2 mb-3">
      <div class="card" style="grid-column:1 / -1">
        <div class="card-header flex justify-between items-center">
          <span class="card-title">Activos</span>
          <span class="text-soft" style="font-size:0.75rem" id="assetCount"></span>
        </div>
        <div class="card-body" style="overflow-x:auto">
          <table class="data-table fin-table">
            <thead>
              <tr>
                <th>Símbolo</th>
                <th>Nombre</th>
                <th>Tipo</th>
                <th class="amount">Unidades</th>
                <th class="amount">Precio compra</th>
                <th class="amount">Precio actual</th>
                <th class="amount">Valor</th>
                <th class="amount">Ganancia</th>
                <th class="amount">Retorno</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="assetsTableBody">
              <tr><td colspan="10" class="text-center text-soft" style="padding:32px">Cargando…</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">Asignación por clase</span></div>
        <div class="card-body" style="position:relative;min-height:240px">
          <canvas id="allocationChart" height="200"></canvas>
          <div id="allocationEmpty" class="empty-state" style="display:none;padding-top:2rem">
            <p class="empty-state__hint">Sin datos para graficar</p>
          </div>
          <div id="allocationLegend" class="mt-3" style="display:flex;flex-direction:column;gap:6px"></div>
        </div>
      </div>
    </div>
  `;
}

async function loadAssets() {
  try {
    const data = await api.portfolio.assets();
    allAssets = Array.isArray(data) ? data : [];
    renderKpis();
    renderTable(allAssets);
    loadAllocation();
  } catch (err) {
    const tbody = rootEl?.querySelector('#assetsTableBody');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="10">${sectionErrorState({ message: err.message, retryId: 'btnPortfolioRetry' })}</td></tr>`;
      bindRetry(tbody, () => loadAssets(), 'btnPortfolioRetry');
    }
  }
}

function renderKpis() {
  const container = rootEl?.querySelector('#portfolioKpis');
  if (!container) return;

  const totalValor = allAssets.reduce((s, a) => s + (a.valor_actual ?? a.current_value ?? 0), 0);
  const totalCosto = allAssets.reduce((s, a) => {
    const u = a.unidades ?? a.units ?? 0;
    const pc = a.precio_compra ?? a.purchase_price ?? 0;
    return s + u * pc;
  }, 0);
  const ganancia = totalValor - totalCosto;
  const retorno = totalCosto > 0 ? (ganancia / totalCosto) * 100 : 0;
  const moneda = allAssets[0]?.moneda ?? allAssets[0]?.currency ?? 'COP';
  const gClass = ganancia >= 0 ? 'text-success' : 'text-danger';

  container.innerHTML = `
    <div class="kpi-card">
      <div class="kpi-label">Valor Total</div>
      <div class="kpi-value amount">${formatCurrency(totalValor, moneda)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Costo Base</div>
      <div class="kpi-value amount text-muted">${formatCurrency(totalCosto, moneda)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Ganancia / Pérdida</div>
      <div class="kpi-value amount ${gClass}">${formatCurrency(ganancia, moneda)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Retorno</div>
      <div class="kpi-value">${formatPct(retorno)}</div>
    </div>
  `;
}

function renderTable(assets) {
  const tbody = rootEl?.querySelector('#assetsTableBody');
  const count = rootEl?.querySelector('#assetCount');
  if (!tbody) return;

  if (count) count.textContent = `${assets.length} activo${assets.length !== 1 ? 's' : ''}`;

  if (!assets.length) {
    tbody.innerHTML = `<tr><td colspan="10">${emptyState({
      icon: '📊',
      title: 'Sin activos registrados',
      hint: 'Agrega acciones, ETFs, cripto u otros activos.',
      actionLabel: '+ Activo',
      actionId: 'btnEmptyNewAsset',
    })}</td></tr>`;
    tbody.querySelector('#btnEmptyNewAsset')?.addEventListener('click', () => {
      rootEl?.querySelector('#btnNewAsset')?.click();
    });
    return;
  }

  tbody.innerHTML = assets.map(a => {
    const unidades = a.unidades ?? a.units ?? 0;
    const precioCompra = a.precio_compra ?? a.purchase_price ?? 0;
    const precioActual = a.precio_actual ?? a.current_price ?? precioCompra;
    const valorActual = a.valor_actual ?? a.current_value ?? (unidades * precioActual);
    const costo = unidades * precioCompra;
    const ganancia = a.ganancia ?? (valorActual - costo);
    const retorno = a.ganancia_pct ?? (costo > 0 ? (ganancia / costo) * 100 : 0);
    const moneda = a.moneda ?? a.currency ?? 'COP';
    const tipo = a.tipo ?? a.asset_type ?? '';
    const simbolo = a.simbolo ?? a.symbol ?? '—';
    const nombre = a.nombre ?? a.name ?? '—';
    const ganCls = ganancia >= 0 ? 'text-success' : 'text-danger';
    const tipoLabel = TIPO_LABELS[tipo] ?? sanitize(tipo);

    return `<tr>
      <td style="font-weight:600">${sanitize(simbolo)}</td>
      <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${sanitize(nombre)}</td>
      <td><span class="badge">${tipoLabel}</span></td>
      <td class="amount">${fmtNumber(unidades, 4)}</td>
      <td class="amount">${formatCurrency(precioCompra, moneda)}</td>
      <td class="amount">${formatCurrency(precioActual, moneda)}</td>
      <td class="amount" style="font-weight:600">${formatCurrency(valorActual, moneda)}</td>
      <td class="amount ${ganCls}">${formatCurrency(ganancia, moneda)}</td>
      <td class="amount">${formatPct(retorno)}</td>
      <td>
        <button type="button" class="btn btn-ghost btn-xs" data-price-asset="${a.id}" data-simbolo="${sanitize(simbolo)}">Precio</button>
      </td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('[data-price-asset]').forEach(btn => {
    btn.addEventListener('click', () => {
      openPriceModal(parseInt(btn.dataset.priceAsset, 10), btn.dataset.simbolo || '');
    });
  });
}

function loadAllocation() {
  const canvas = rootEl?.querySelector('#allocationChart');
  const legendEl = rootEl?.querySelector('#allocationLegend');
  const emptyEl = rootEl?.querySelector('#allocationEmpty');
  if (!canvas) return;

  if (!allAssets.length) {
    canvas.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
    if (legendEl) legendEl.innerHTML = '';
    if (allocationChart) { allocationChart.destroy(); allocationChart = null; }
    return;
  }

  canvas.style.display = 'block';
  if (emptyEl) emptyEl.style.display = 'none';

  const palette = window.CHART_PALETTE ?? ['#316342','#BA1A1A','#735142','#3B5B66','#6B4226','#4C6B3F','#8A5A44','#7A6A53'];

  const byClase = {};
  const claseOrder = [];
  for (const a of allAssets) {
    const clase = a.asset_class ?? a.clase ?? 'otro';
    const val = a.valor_actual ?? a.current_value
      ?? ((a.unidades ?? a.units ?? 0) * (a.precio_actual ?? a.current_price ?? a.precio_compra ?? a.purchase_price ?? 0));
    if (!byClase[clase]) { byClase[clase] = 0; claseOrder.push(clase); }
    byClase[clase] += val;
  }

  const labels = claseOrder.map(k => CLASE_LABELS[k] ?? k);
  const data = claseOrder.map(k => byClase[k]);
  const total = data.reduce((s, v) => s + v, 0);
  const colors = claseOrder.map((_, i) => palette[i % palette.length]);

  if (allocationChart) allocationChart.destroy();

  const ctx = canvas.getContext('2d');
  allocationChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderWidth: 1.5,
        borderColor: getComputedStyle(document.documentElement).getPropertyValue('--fin-surface').trim() || '#fff',
        hoverOffset: 6,
      }],
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
    legendEl.innerHTML = claseOrder.map((clase, i) => {
      const val = byClase[clase];
      const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
      const color = colors[i];
      return `<div class="flex justify-between items-center gap-2">
        <div class="flex items-center gap-1">
          <span style="width:10px;height:10px;border-radius:2px;background:${sanitize(color)};flex-shrink:0"></span>
          <span class="text-muted" style="font-size:12px">${sanitize(CLASE_LABELS[clase] ?? clase)}</span>
        </div>
        <span class="amount" style="font-size:11px;color:var(--fin-ink-3)">${pct}%</span>
      </div>`;
    }).join('');
  }
}

function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function openNewAssetModal() {
  openModal({
    title: 'Nuevo activo',
    submitLabel: 'Guardar Activo',
    content: `
      <div class="form-row cols-2">
        <div class="form-group mb-3">
          <label class="form-label required">Símbolo</label>
          <input type="text" id="naSimbolo" placeholder="AAPL" autocomplete="off">
        </div>
        <div class="form-group mb-3">
          <label class="form-label required">Nombre</label>
          <input type="text" id="naNombre" placeholder="Apple Inc." autocomplete="off">
        </div>
      </div>
      <div class="form-row cols-2">
        <div class="form-group mb-3">
          <label class="form-label required">Tipo</label>
          <select id="naTipo">
            <option value="accion">Acción</option>
            <option value="etf">ETF</option>
            <option value="cripto">Cripto</option>
            <option value="fondo">Fondo</option>
            <option value="otro">Otro</option>
          </select>
        </div>
        <div class="form-group mb-3">
          <label class="form-label required">Clase</label>
          <select id="naClase">
            <option value="renta_variable">Renta Variable</option>
            <option value="renta_fija">Renta Fija</option>
            <option value="liquidez">Liquidez</option>
            <option value="alternativo">Alternativo</option>
          </select>
        </div>
      </div>
      <div class="form-row cols-2">
        <div class="form-group mb-3">
          <label class="form-label required">Unidades</label>
          <input type="number" id="naUnidades" step="any" min="0">
        </div>
        <div class="form-group mb-3">
          <label class="form-label required">Precio de compra</label>
          <input type="number" id="naPrecioCompra" step="any" min="0">
        </div>
      </div>
      <div class="form-row cols-2">
        <div class="form-group mb-3">
          <label class="form-label required">Fecha de compra</label>
          <input type="date" id="naFechaCompra" value="${todayISO()}">
        </div>
        <div class="form-group mb-3">
          <label class="form-label">Moneda</label>
          <select id="naMoneda">
            <option value="USD">USD</option>
            <option value="COP">COP</option>
          </select>
        </div>
      </div>
      <div class="form-group mb-3">
        <label class="form-label">Notas</label>
        <input type="text" id="naNotas" placeholder="Opcional">
      </div>
    `,
    onSubmit: async (body) => {
      const simbolo = body.querySelector('#naSimbolo').value.trim();
      const nombre = body.querySelector('#naNombre').value.trim();
      const tipo = body.querySelector('#naTipo').value;
      const assetClass = body.querySelector('#naClase').value;
      const unidades = parseFloat(body.querySelector('#naUnidades').value);
      const precioCompra = parseFloat(body.querySelector('#naPrecioCompra').value);
      const fechaCompra = body.querySelector('#naFechaCompra').value || todayISO();
      const moneda = body.querySelector('#naMoneda').value;
      const notas = body.querySelector('#naNotas').value.trim();

      if (!simbolo) throw new Error('El símbolo es requerido');
      if (!nombre) throw new Error('El nombre es requerido');
      if (isNaN(unidades) || unidades <= 0) throw new Error('Ingresa las unidades');
      if (isNaN(precioCompra) || precioCompra <= 0) throw new Error('Ingresa el precio de compra');

      await api.portfolio.createAsset({
        simbolo,
        nombre,
        tipo,
        asset_class: assetClass,
        unidades,
        precio_compra: precioCompra,
        fecha_compra: fechaCompra,
        moneda,
        notas: notas || null,
      });
      await loadAssets();
    },
  });
}

function openPriceModal(assetId, simbolo) {
  openModal({
    title: `Actualizar Precio — ${simbolo || 'Activo'}`,
    submitLabel: 'Actualizar Precio',
    content: `
      <input type="hidden" id="priceAssetId" value="${assetId}">
      <div class="form-group mb-3">
        <label class="form-label required">Fecha</label>
        <input type="date" id="pFecha" value="${todayISO()}">
      </div>
      <div class="form-group mb-3">
        <label class="form-label required">Precio</label>
        <input type="number" id="pPrecio" step="any" min="0">
      </div>
    `,
    onSubmit: async (body) => {
      const id = parseInt(body.querySelector('#priceAssetId').value, 10);
      const fecha = body.querySelector('#pFecha').value;
      const precio = parseFloat(body.querySelector('#pPrecio').value);

      if (!fecha) throw new Error('La fecha es requerida');
      if (isNaN(precio) || precio <= 0) throw new Error('Ingresa un precio válido');

      await api.portfolio.addPrice(id, { fecha, precio, fuente: 'manual' });
      await loadAssets();
    },
  });
}

function bindEvents(container) {
  container.querySelector('#btnNewAsset')?.addEventListener('click', openNewAssetModal);
}

export async function mount(container) {
  rootEl = container;
  container.innerHTML = shellHtml();
  bindEvents(container);
  await loadAssets();
}

export function cleanup() {
  if (allocationChart) { allocationChart.destroy(); allocationChart = null; }
  allAssets = [];
  rootEl = null;
}
