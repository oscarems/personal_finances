import * as api from '../api/client.js';
import { sanitize } from '../utils.js';
import { toast } from '../components/toast.js';
import { navigate } from '../router.js';

export const title = 'Configuración';

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    const [rates, currencies] = await Promise.all([
      api.exchangeRates.list().catch(() => []),
      api.currencies.list(),
    ]);
    render(container, rates, currencies);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container, rates, currencies) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Configuración</h1>
        <p>Tasas de cambio, categorías y ajustes del sistema.</p>
      </div>
    </div>

    <div class="section-grid cols-2">
      <!-- Exchange Rates -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Tasas de Cambio</span>
          <button class="btn btn-secondary btn-sm" id="btnSyncRates">⟳ Sincronizar</button>
        </div>
        <div class="card-body" id="ratesBody">
          ${rates.length ? `
            <table>
              <thead><tr><th>Par</th><th class="td-right">Tasa</th><th>Fecha</th></tr></thead>
              <tbody>
                ${rates.map(r => `
                  <tr>
                    <td style="font-size:0.8125rem;font-family:var(--font-mono)">${sanitize(r.from_currency ?? r.base ?? '')} → ${sanitize(r.to_currency ?? r.target ?? '')}</td>
                    <td class="td-right td-mono" style="font-size:0.8125rem">${(r.rate ?? r.exchange_rate ?? 0).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td class="td-soft" style="font-size:0.8rem">${r.date ?? r.effective_date ?? '—'}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          ` : '<div class="empty-state"><p>Sin tasas registradas</p></div>'}
        </div>
      </div>

      <!-- Categories Init -->
      <div class="card">
        <div class="card-header"><span class="card-title">Categorías</span></div>
        <div class="card-body">
          <p style="font-size:0.875rem;color:var(--text-secondary);margin-bottom:16px">
            Si no tienes categorías configuradas, puedes sembrar el set predeterminado.
          </p>
          <button class="btn btn-secondary" id="btnSeedCats">🌱 Sembrar categorías por defecto</button>
        </div>
      </div>

      <!-- Email Sync -->
      <div class="card">
        <div class="card-header"><span class="card-title">Sincronización de Email</span></div>
        <div class="card-body">
          <p style="font-size:0.875rem;color:var(--text-secondary);margin-bottom:16px">
            Lee los correos de Gmail y crea transacciones automáticamente según las reglas configuradas.
          </p>
          <div style="display:flex;gap:8px">
            <button class="btn btn-secondary" id="btnSyncEmail">📬 Sincronizar ahora</button>
            <a class="btn btn-ghost" data-link="/email-sender-rules">Ver reglas →</a>
          </div>
        </div>
      </div>

      <!-- App Info -->
      <div class="card">
        <div class="card-header"><span class="card-title">Información</span></div>
        <div class="card-body">
          <div style="display:flex;flex-direction:column;gap:10px">
            <div style="display:flex;justify-content:space-between;font-size:0.875rem">
              <span style="color:var(--text-secondary)">Versión</span>
              <span style="font-family:var(--font-mono)">2.0.0</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.875rem">
              <span style="color:var(--text-secondary)">Monedas soportadas</span>
              <span>${currencies.map(c => c.code).join(', ')}</span>
            </div>
          </div>
          <hr class="divider">
          <p style="font-size:0.8rem;color:var(--text-soft)">
            Aplicación de finanzas personales local. Los datos se almacenan en SQLite en tu máquina.
          </p>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btnSyncRates')?.addEventListener('click', async () => {
    try {
      await api.exchangeRates.sync();
      toast.success('Tasas actualizadas');
      const rates = await api.exchangeRates.list().catch(() => []);
      container.querySelector('#ratesBody').innerHTML = rates.length ? 'Actualizado — recarga la página' : 'Sin datos';
    } catch (err) { toast.error(err.message); }
  });

  container.querySelector('#btnSeedCats')?.addEventListener('click', async () => {
    if (!confirm('¿Sembrar categorías por defecto? Esto no eliminará las existentes.')) return;
    try {
      await api.categories.seed();
      toast.success('Categorías sembradas');
    } catch (err) { toast.error(err.message); }
  });

  container.querySelector('#btnSyncEmail')?.addEventListener('click', async () => {
    try {
      toast.info('Sincronizando email…');
      await api.admin.syncEmail();
      toast.success('Sincronización completada');
    } catch (err) { toast.error(err.message); }
  });
}
