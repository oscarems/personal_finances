import * as api from '../api/client.js';
import { fmtCurrency, sanitize, debounce } from '../utils.js';
import { emptyState } from '../components/emptyState.js';
import { loadingState, showError } from '../components/pageState.js';

export const title = 'Qué pasa si';

let _extra = 500000;
let _strategy = 'avalanche';
let _data = null;

export async function mount(container) {
  container.innerHTML = loadingState();
  try {
    await loadAndRender(container);
  } catch (err) {
    showError(container, { title: 'Qué pasa si', message: err.message, onRetry: () => mount(container) });
  }
}

async function loadAndRender(container) {
  _data = await api.whatIf.simulate({ extra_monthly: _extra, strategy: _strategy });
  render(container);
}

function render(container) {
  const d = _data;
  const debt = d.debt;
  const em = d.emergency;
  const fire = d.fire;

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Qué pasa si…</h1>
        <p>Un solo dial: impacto en deudas, emergencia y FIRE</p>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-body">
        <div class="flex justify-between items-center mb-2">
          <label class="form-label" style="margin:0">Pago / ahorro extra mensual</label>
          <strong class="amount">${fmtCurrency(_extra, 'COP')}</strong>
        </div>
        <input type="range" id="wf-extra" min="0" max="5000000" step="50000" value="${_extra}" style="width:100%">
        <div class="flex gap-2 mt-3">
          <button class="tab-pill ${_strategy === 'avalanche' ? 'active' : ''}" data-strat="avalanche">Avalancha</button>
          <button class="tab-pill ${_strategy === 'snowball' ? 'active' : ''}" data-strat="snowball">Bola de nieve</button>
        </div>
        <p class="text-soft text-sm mt-3">${sanitize(d.note || '')}</p>
      </div>
    </div>

    <div class="section-grid cols-3 mb-4">
      <div class="card">
        <div class="card-header"><span class="card-title">Deudas</span></div>
        <div class="card-body">
          ${debt ? `
            <div class="kpi-label">Meses hasta libre de deuda</div>
            <div class="flex justify-between items-end mb-3">
              <div>
                <div class="text-soft text-sm">Hoy</div>
                <div class="kpi-value">${debt.baseline?.months ?? '—'} m</div>
              </div>
              <div class="text-soft">→</div>
              <div>
                <div class="text-soft text-sm">Con extra</div>
                <div class="kpi-value positive">${debt.with_extra?.months ?? '—'} m</div>
              </div>
            </div>
            <div class="text-sm">Ahorras <strong class="amount text-success">${debt.months_saved ?? 0} meses</strong>
              y <strong class="amount text-success">${fmtCurrency(debt.interest_saved ?? 0, 'COP')}</strong> de interés</div>
          ` : emptyState({ icon: '💳', title: 'Sin deudas activas', hint: '' })}
        </div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">Fondo de emergencia</span></div>
        <div class="card-body">
          <div class="kpi-label">Meses de cobertura (si ahorras el extra 12 meses)</div>
          <div class="flex justify-between items-end mb-3">
            <div>
              <div class="text-soft text-sm">Hoy</div>
              <div class="kpi-value">${em.months_now?.toFixed?.(1) ?? em.months_now} m</div>
            </div>
            <div class="text-soft">→</div>
            <div>
              <div class="text-soft text-sm">+12 meses</div>
              <div class="kpi-value positive">${em.months_with_extra_12m?.toFixed?.(1) ?? em.months_with_extra_12m} m</div>
            </div>
          </div>
          <div class="text-sm text-soft">Fondos: ${fmtCurrency(em.funds_now, 'COP')} → ${fmtCurrency(em.funds_with_extra_12m, 'COP')}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">FIRE</span></div>
        <div class="card-body">
          <div class="kpi-label">Años restantes (si inviertes el extra)</div>
          <div class="flex justify-between items-end mb-3">
            <div>
              <div class="text-soft text-sm">Hoy</div>
              <div class="kpi-value">${fire.anos_restantes_now ?? '—'}</div>
            </div>
            <div class="text-soft">→</div>
            <div>
              <div class="text-soft text-sm">Con extra</div>
              <div class="kpi-value positive">${fire.anos_restantes_with_extra ?? '—'}</div>
            </div>
          </div>
          <div class="text-sm text-soft">Ratio: ${(fire.ratio_now * 100).toFixed(1)}% → ${(fire.ratio_after_1y_extra * 100).toFixed(1)}% (1 año)</div>
        </div>
      </div>
    </div>
  `;

  const slider = container.querySelector('#wf-extra');
  const reload = debounce(async () => {
    _extra = parseFloat(slider.value) || 0;
    await loadAndRender(container);
  }, 280);
  slider.addEventListener('input', () => {
    container.querySelector('.amount').textContent = fmtCurrency(parseFloat(slider.value) || 0, 'COP');
    reload();
  });

  container.querySelectorAll('[data-strat]').forEach(btn => {
    btn.addEventListener('click', async () => {
      _strategy = btn.dataset.strat;
      await loadAndRender(container);
    });
  });
}
