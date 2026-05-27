import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Patrimonio';

let _chart = null;
let _assets = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    const [summary, assets] = await Promise.all([
      api.patrimonio.summary(),
      api.patrimonio.assets(),
    ]);
    _assets = Array.isArray(assets) ? assets : [];
    render(container, summary, _assets);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

export function cleanup() { _chart?.destroy(); _chart = null; }

function render(container, summary, assets) {
  const totalAssets = summary?.total_activos ?? 0;
  const totalDebt   = summary?.total_deudas  ?? 0;
  const netWorth    = summary?.patrimonio_neto ?? (totalAssets - totalDebt);

  // Use enriched assets from summary if available, otherwise raw assets
  const displayAssets = summary?.activos ?? assets;
  const categories = groupByTipo(displayAssets);

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text"><h1>Patrimonio</h1></div>
      <div class="page-header-actions">
        <button class="btn btn-primary" id="btnAddAsset">+ Activo</button>
      </div>
    </div>

    <div class="kpi-grid" style="margin-bottom:24px">
      <div class="kpi-card">
        <div class="kpi-label">Patrimonio Neto</div>
        <div class="kpi-value ${netWorth >= 0 ? 'positive' : 'negative'}">${fmtCurrency(netWorth, 'COP')}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Total Activos</div>
        <div class="kpi-value positive">${fmtCurrency(totalAssets, 'COP')}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Total Pasivos</div>
        <div class="kpi-value negative">${fmtCurrency(totalDebt, 'COP')}</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 300px;gap:20px;margin-bottom:24px">
      <div class="card">
        <div class="card-header"><span class="card-title">Activos</span></div>
        <div class="card-body">
          ${Object.entries(categories).map(([cat, list]) => categorySection(cat, list)).join('')}
          ${displayAssets.length === 0 ? `<div class="empty-state"><p>Sin activos registrados</p></div>` : ''}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Composición</span></div>
        <div class="card-body" style="height:260px;position:relative">
          <canvas id="patriChart"></canvas>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btnAddAsset').addEventListener('click', () => openAssetModal(null, container));
  container.querySelectorAll('[data-edit-asset]').forEach(btn => {
    const asset = assets.find(a => a.id === parseInt(btn.dataset.editAsset));
    btn.addEventListener('click', () => openAssetModal(asset, container));
  });
  container.querySelectorAll('[data-delete-asset]').forEach(btn => {
    const id = parseInt(btn.dataset.deleteAsset);
    btn.addEventListener('click', () => deleteAsset(id, container));
  });

  // Pie chart
  const ctx = container.querySelector('#patriChart');
  if (ctx && displayAssets.length) {
    const COLORS = ['#D97706','#059669','#0891B2','#7C3AED','#DB2777','#EA580C'];
    const data = Object.entries(categories).map(([cat, list], i) => ({
      label: cat,
      value: list.reduce((s, a) => s + (a.valor_actual ?? a.valor_adquisicion ?? 0), 0),
      color: COLORS[i % COLORS.length],
    })).filter(d => d.value > 0);

    _chart?.destroy();
    _chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.map(d => d.label),
        datasets: [{ data: data.map(d => d.value), backgroundColor: data.map(d => d.color), borderWidth: 2, borderColor: 'var(--bg-surface)' }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 10 }, color: 'var(--text-secondary)', padding: 8 } },
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
  return `
    <div style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft)">${sanitize(cat)}</span>
        <span style="font-family:var(--font-mono);font-size:0.8125rem;color:var(--text-secondary)">${fmtCurrency(total, 'COP')}</span>
      </div>
      ${list.map(a => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border-muted)">
          <div>
            <div style="font-size:0.8125rem;font-weight:500">${sanitize(a.nombre)}</div>
            ${a.notas ? `<div style="font-size:0.72rem;color:var(--text-soft)">${sanitize(a.notas)}</div>` : ''}
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="amount positive" style="font-size:0.8125rem">
              ${fmtCurrency(a.valor_actual ?? a.valor_adquisicion ?? 0, a.currency?.code ?? 'COP')}
            </span>
            <button class="btn btn-ghost btn-xs" data-edit-asset="${a.id}">✏</button>
            <button class="btn btn-ghost btn-xs" style="color:var(--color-danger)" data-delete-asset="${a.id}">✕</button>
          </div>
        </div>`).join('')}
    </div>`;
}

function assetFormHtml(asset) {
  const a = asset ?? {};
  const tipos = ['inmueble','vehiculo','inversion','cuenta','efectivo','otro'];
  const currencyIdMap = { COP: 1, USD: 2 };
  const currCode = a.currency?.code ?? 'COP';
  return `
    <div class="form-group" style="margin-bottom:16px">
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
      <input type="number" id="af-tasa" value="${a.tasa_anual ?? 0}" step="0.01" placeholder="0.00">
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
      const data = {
        nombre:            body.querySelector('#af-nombre').value.trim(),
        valor_adquisicion: parseFloat(body.querySelector('#af-valor').value),
        fecha_adquisicion: body.querySelector('#af-fecha').value,
        tipo:              body.querySelector('#af-tipo').value,
        tasa_anual:        parseFloat(body.querySelector('#af-tasa').value || '0'),
        moneda_id:         currencyIdMap[currCode] ?? 1,
        notas:             body.querySelector('#af-notas').value.trim() || null,
      };
      if (!data.nombre || !data.valor_adquisicion || !data.fecha_adquisicion) throw new Error('Nombre, valor y fecha son obligatorios');
      if (isEdit) { await api.patrimonio.updateAsset(asset.id, data); toast.success('Actualizado'); }
      else        { await api.patrimonio.createAsset(data);           toast.success('Activo creado'); }
      const [summary, assets] = await Promise.all([api.patrimonio.summary(), api.patrimonio.assets()]);
      _assets = Array.isArray(assets) ? assets : [];
      render(container, summary, _assets);
    },
  });
}

async function deleteAsset(id, container) {
  if (!confirm('¿Eliminar este activo?')) return;
  try {
    await api.patrimonio.deleteAsset(id);
    toast.success('Eliminado');
    const [summary, assets] = await Promise.all([api.patrimonio.summary(), api.patrimonio.assets()]);
    _assets = Array.isArray(assets) ? assets : [];
    render(container, summary, _assets);
  } catch (err) { toast.error(err.message); }
}
