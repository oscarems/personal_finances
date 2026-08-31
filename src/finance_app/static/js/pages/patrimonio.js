import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';
import { emptyState } from '../components/emptyState.js';
import { loadingState, showError } from '../components/pageState.js';

export const title = 'Patrimonio';

let _chart = null;
let _timelineChart = null;
let _assets = [];

export async function mount(container) {
  container.innerHTML = loadingState();
  try {
    const [summary, assets, timeline] = await Promise.all([
      api.patrimonio.summary(),
      api.patrimonio.assets(),
      api.reports.netWorthTimeline().catch(() => []),
    ]);
    _assets = Array.isArray(assets) ? assets : [];
    render(container, summary, _assets, Array.isArray(timeline) ? timeline : []);
  } catch (err) {
    showError(container, {
      title: 'Patrimonio',
      message: err.message || 'Error al cargar el patrimonio',
      onRetry: () => mount(container),
    });
  }
}

export function cleanup() {
  _chart?.destroy();
  _chart = null;
  _timelineChart?.destroy();
  _timelineChart = null;
}

const TIPO_ICON = { inmueble: '🏠', vehiculo: '🚗', inversion: '📈', cuenta: '🏦', efectivo: '💵', otro: '📦' };
const TIPO_LABEL = { inmueble: 'Inmuebles', vehiculo: 'Vehículos', inversion: 'Inversiones', cuenta: 'Cuentas', efectivo: 'Efectivo', otro: 'Otros' };

function render(container, summary, assets, timeline = []) {
  const totalAssets = summary?.total_activos ?? 0;
  const totalDebt   = summary?.total_deudas  ?? 0;
  const netWorth    = summary?.patrimonio_neto ?? (totalAssets - totalDebt);

  // Use enriched assets from summary if available, otherwise raw assets
  const displayAssets = summary?.activos ?? assets;
  const categories = groupByTipo(displayAssets);

  const totalCosto  = displayAssets.reduce((s, a) => s + (a.valor_adquisicion ?? 0), 0);
  const gananciaTot = totalAssets - totalCosto;
  const gananciaPct = totalCosto > 0 ? (gananciaTot / totalCosto) * 100 : 0;
  const debtRatio   = totalAssets > 0 ? (totalDebt / totalAssets) * 100 : 0;

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Patrimonio</h1>
        <p class="text-soft" style="margin:2px 0 0;font-size:0.8125rem">Activos, valorización y composición de tu patrimonio neto</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-ghost btn-sm" id="btnExportPatrimonio" title="Exportar CSV">↓ Exportar</button>
        <button class="btn btn-primary" id="btnAddAsset">+ Activo</button>
      </div>
    </div>

    <div class="kpi-grid mb-3">
      <div class="kpi-card">
        <div class="kpi-label">Patrimonio Neto</div>
        <div class="kpi-value ${netWorth >= 0 ? 'text-success' : 'text-danger'} amount">${fmtCurrency(netWorth, 'COP')}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Total Activos</div>
        <div class="kpi-value text-success amount">${fmtCurrency(totalAssets, 'COP')}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Total Pasivos</div>
        <div class="kpi-value text-danger amount">${fmtCurrency(totalDebt, 'COP')}</div>
        <div class="text-soft" style="font-size:0.72rem;margin-top:2px">${debtRatio.toFixed(1)}% de los activos</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Valorización</div>
        <div class="kpi-value ${gananciaTot >= 0 ? 'text-success' : 'text-danger'} amount">${gananciaTot >= 0 ? '+' : ''}${fmtCurrency(gananciaTot, 'COP')}</div>
        <div class="text-soft" style="font-size:0.72rem;margin-top:2px">${gananciaPct >= 0 ? '+' : ''}${gananciaPct.toFixed(1)}% sobre costo</div>
      </div>
    </div>

    <div class="card mb-3">
      <div class="card-header"><span class="card-title">Evolución patrimonio neto</span></div>
      <div class="card-body" style="height:260px;position:relative">
        ${timeline.length < 1
          ? emptyState({ icon: '📈', title: 'Sin historial aún', hint: 'El snapshot del mes se genera al abrir la app o esta página.' })
          : '<canvas id="netWorthChart"></canvas>'}
      </div>
    </div>

    <div class="grid-2 mb-3">
      <div class="card">
        <div class="card-header"><span class="card-title">Activos</span></div>
        <div class="card-body">
          ${displayAssets.length === 0
            ? emptyState({
                icon: '🏦',
                title: 'Sin activos registrados',
                hint: 'Agrega inmuebles, vehículos, inversiones u otros bienes para calcular tu patrimonio neto.',
                actionLabel: '+ Activo',
                actionId: 'btnAddAssetEmpty',
              })
            : Object.entries(categories).map(([cat, list]) => categorySection(cat, list)).join('')}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Composición</span></div>
        <div class="card-body" style="height:280px;position:relative">
          ${displayAssets.length === 0
            ? emptyState({ icon: '📊', title: 'Sin datos para graficar', hint: 'Agrega activos para ver la composición.' })
            : '<canvas id="patriChart"></canvas>'}
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btnExportPatrimonio')?.addEventListener('click', () => {
    window.location = api.patrimonio.exportUrl;
  });
  container.querySelector('#btnAddAsset').addEventListener('click', () => openAssetModal(null, container));
  container.querySelector('#btnAddAssetEmpty')?.addEventListener('click', () => openAssetModal(null, container));
  container.querySelectorAll('[data-edit-asset]').forEach(btn => {
    const asset = assets.find(a => a.id === parseInt(btn.dataset.editAsset));
    btn.addEventListener('click', () => openAssetModal(asset, container));
  });
  container.querySelectorAll('[data-delete-asset]').forEach(btn => {
    const id = parseInt(btn.dataset.deleteAsset);
    btn.addEventListener('click', () => deleteAsset(id, container));
  });

  // Net worth timeline
  const nwCtx = container.querySelector('#netWorthChart');
  if (nwCtx && timeline.length) {
    const accent = (window.CHART_PALETTE ?? ['#316342'])[0];
    _timelineChart?.destroy();
    _timelineChart = new Chart(nwCtx, {
      type: 'line',
      data: {
        labels: timeline.map(s => s.month),
        datasets: [{
          label: 'Patrimonio neto',
          data: timeline.map(s => s.net_cop),
          borderColor: accent,
          backgroundColor: accent + '33',
          fill: true,
          tension: 0.25,
          pointRadius: timeline.length > 18 ? 0 : 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` ${fmtCurrency(ctx.raw, 'COP')}` } },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 8, color: 'var(--fin-ink-3)', font: { size: 10 } }, grid: { display: false } },
          y: {
            ticks: {
              color: 'var(--fin-ink-3)',
              font: { size: 10 },
              callback: v => fmtCurrency(v, 'COP'),
            },
            grid: { color: 'var(--fin-border)' },
          },
        },
      },
    });
  }

  // Pie chart
  const ctx = container.querySelector('#patriChart');
  if (ctx && displayAssets.length) {
    const COLORS = window.CHART_PALETTE ?? ['#316342','#BA1A1A','#735142','#3B5B66','#6B4226','#4C6B3F','#8A5A44','#7A6A53'];
    const data = Object.entries(categories).map(([cat, list], i) => ({
      label: TIPO_LABEL[cat] ?? cat,
      value: list.reduce((s, a) => s + (a.valor_actual ?? a.valor_adquisicion ?? 0), 0),
      color: COLORS[i % COLORS.length],
    })).filter(d => d.value > 0);

    _chart?.destroy();
    _chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.map(d => d.label),
        datasets: [{ data: data.map(d => d.value), backgroundColor: data.map(d => d.color), borderWidth: 2, borderColor: 'var(--fin-surface)' }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 10 }, color: 'var(--fin-ink-3)', padding: 8 } },
          tooltip: { callbacks: { label: ctx => ` ${fmtCurrency(ctx.raw, 'COP')}` } },
        },
      },
    });
  }
}

function groupByTipo(assets) {
  return assets.reduce((acc, a) => {
    const cat = a.tipo ?? 'Otros';
    (acc[cat] ??= []).push(a);
    return acc;
  }, {});
}

function categorySection(cat, list) {
  const total = list.reduce((s, a) => s + (a.valor_actual ?? a.valor_adquisicion ?? 0), 0);
  const icon = TIPO_ICON[cat] ?? '📦';
  const label = TIPO_LABEL[cat] ?? sanitize(cat);
  return `
    <div class="mb-3">
      <div class="flex justify-between mb-1">
        <span class="text-soft" style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em">${icon} ${label}</span>
        <span class="amount text-muted" style="font-size:0.8125rem">${fmtCurrency(total, 'COP')}</span>
      </div>
      ${list.map(a => {
        const valorActual = a.valor_actual ?? a.valor_adquisicion ?? 0;
        const costo = a.valor_adquisicion ?? 0;
        const ganancia = valorActual - costo;
        const gananciaPct = costo > 0 ? (ganancia / costo) * 100 : 0;
        const gCls = ganancia >= 0 ? 'text-success' : 'text-danger';
        return `
        <div class="flex justify-between items-center" style="padding:8px 0;border-bottom:1px solid var(--fin-border)">
          <div>
            <div style="font-size:0.8125rem;font-weight:500">${sanitize(a.nombre)}</div>
            <div class="text-soft" style="font-size:0.72rem">
              ${a.fecha_adquisicion ? fmtDate(a.fecha_adquisicion) : ''}${a.notas ? ` · ${sanitize(a.notas)}` : ''}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <div style="text-align:right">
              <div class="amount" style="font-size:0.8125rem;font-weight:600">
                ${fmtCurrency(valorActual, a.currency?.code ?? 'COP')}
              </div>
              ${costo > 0 ? `<div class="amount ${gCls}" style="font-size:0.68rem">${ganancia >= 0 ? '+' : ''}${gananciaPct.toFixed(1)}%</div>` : ''}
            </div>
            <button class="btn btn-ghost btn-xs" data-edit-asset="${a.id}" title="Editar">✏</button>
            <button class="btn btn-ghost btn-xs text-danger" data-delete-asset="${a.id}" title="Eliminar">✕</button>
          </div>
        </div>`;
      }).join('')}
    </div>`;
}

function assetFormHtml(asset) {
  const a = asset ?? {};
  const tipos = ['inmueble','vehiculo','inversion','cuenta','efectivo','otro'];
  const currencyIdMap = { COP: 1, USD: 2 };
  const currCode = a.currency?.code ?? 'COP';
  return `
    <div class="form-group mb-3">
      <label class="form-label required">Nombre</label>
      <input type="text" id="af-nombre" value="${sanitize(a.nombre ?? '')}" placeholder="Ej: Apartamento, Auto">
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Valor de adquisición</label>
        <input type="number" id="af-valor" value="${a.valor_adquisicion ?? ''}" step="0.01" min="0">
      </div>
      <div class="form-group">
        <label class="form-label">Moneda</label>
        <select id="af-currency">
          <option value="COP" ${currCode === 'COP' ? 'selected' : ''}>COP</option>
          <option value="USD" ${currCode === 'USD' ? 'selected' : ''}>USD</option>
        </select>
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Fecha de adquisición</label>
        <input type="date" id="af-fecha" value="${a.fecha_adquisicion ?? new Date().toISOString().split('T')[0]}">
      </div>
      <div class="form-group">
        <label class="form-label">Tipo</label>
        <select id="af-tipo">
          ${tipos.map(t => `<option value="${t}" ${a.tipo === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Tasa de apreciación anual (%)</label>
      <input type="number" id="af-tasa" value="${((a.tasa_anual ?? 0) * 100).toFixed(2)}" step="0.01" placeholder="0.00">
    </div>
    <div class="form-row cols-2" style="margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid var(--color-border)">
      <div class="form-group">
        <label class="form-label">Precio de mercado actual</label>
        <input type="number" id="af-valor-mercado" value="${a.valor_mercado_manual ?? ''}" step="0.01" min="0" placeholder="Avalúo, tasación…">
      </div>
      <div class="form-group">
        <label class="form-label">Fecha de ese precio</label>
        <input type="date" id="af-fecha-mercado" value="${a.fecha_valor_mercado ?? ''}">
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Notas</label>
      <textarea id="af-notas" rows="2">${sanitize(a.notas ?? '')}</textarea>
    </div>
  `;
}

function openAssetModal(asset, container) {
  const isEdit = !!asset;
  openModal({
    title: isEdit ? `Editar: ${asset.nombre}` : 'Nuevo Activo',
    content: assetFormHtml(asset),
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const currencyIdMap = { COP: 1, USD: 2 };
      const currCode = body.querySelector('#af-currency').value;
      const valorMercadoRaw = body.querySelector('#af-valor-mercado').value;
      const fechaMercadoRaw = body.querySelector('#af-fecha-mercado').value;
      const data = {
        nombre:               body.querySelector('#af-nombre').value.trim(),
        valor_adquisicion:    parseFloat(body.querySelector('#af-valor').value),
        fecha_adquisicion:    body.querySelector('#af-fecha').value,
        tipo:                 body.querySelector('#af-tipo').value,
        tasa_anual:           parseFloat(body.querySelector('#af-tasa').value || '0') / 100,
        moneda_id:            currencyIdMap[currCode] ?? 1,
        notas:                body.querySelector('#af-notas').value.trim() || null,
        valor_mercado_manual: valorMercadoRaw ? parseFloat(valorMercadoRaw) : null,
        fecha_valor_mercado:  fechaMercadoRaw || null,
      };
      if (!data.nombre || !data.valor_adquisicion || !data.fecha_adquisicion) throw new Error('Nombre, valor y fecha son obligatorios');
      if (isEdit) { await api.patrimonio.updateAsset(asset.id, data); toast.success('Actualizado'); }
      else        { await api.patrimonio.createAsset(data);           toast.success('Activo creado'); }
      const [summary, assets, timeline] = await Promise.all([
        api.patrimonio.summary(),
        api.patrimonio.assets(),
        api.reports.netWorthTimeline().catch(() => []),
      ]);
      _assets = Array.isArray(assets) ? assets : [];
      render(container, summary, _assets, Array.isArray(timeline) ? timeline : []);
    },
  });
}

async function deleteAsset(id, container) {
  if (!confirm('¿Eliminar este activo?')) return;
  try {
    await api.patrimonio.deleteAsset(id);
    toast.success('Eliminado');
    const [summary, assets, timeline] = await Promise.all([
      api.patrimonio.summary(),
      api.patrimonio.assets(),
      api.reports.netWorthTimeline().catch(() => []),
    ]);
    _assets = Array.isArray(assets) ? assets : [];
    render(container, summary, _assets, Array.isArray(timeline) ? timeline : []);
  } catch (err) { toast.error(err.message); }
}
