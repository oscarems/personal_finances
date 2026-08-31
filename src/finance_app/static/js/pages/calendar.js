import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, todayISO } from '../utils.js';
import { emptyState } from '../components/emptyState.js';
import { loadingState, showError } from '../components/pageState.js';

export const title = 'Vencimientos';

const DAY_OPTIONS = [7, 14, 30];

function daysFromToday(isoDate) {
  const today = new Date(todayISO() + 'T12:00:00');
  const target = new Date(isoDate + 'T12:00:00');
  return Math.round((target - today) / 86400000);
}

function dateGroupLabel(isoDate) {
  const diff = daysFromToday(isoDate);
  const formatted = fmtDate(isoDate);
  if (diff === 0) return `Hoy · ${formatted}`;
  if (diff === 1) return `Mañana · ${formatted}`;
  const weekday = new Date(isoDate + 'T12:00:00').toLocaleDateString('es-CO', { weekday: 'long' });
  return `${weekday.charAt(0).toUpperCase() + weekday.slice(1)} · ${formatted}`;
}

function eventLink(ev) {
  if (ev.source === 'recurring') return '/recurring';
  if (ev.source === 'debt' || ev.source === 'installment') return '/debts';
  return '/cash-flow';
}

function sourceBadge(source) {
  const map = {
    recurring: { cls: 'badge-primary', label: 'Recurrente' },
    debt: { cls: 'badge-warning', label: 'Deuda' },
    installment: { cls: 'badge-warning', label: 'Cuota' },
  };
  return map[source] ?? { cls: 'badge-neutral', label: 'Otro' };
}

function typeBadge(type) {
  if (type === 'income') return { cls: 'badge-success', label: 'Ingreso' };
  if (type === 'debt_payment') return { cls: 'badge-warning', label: 'Pago' };
  if (type === 'installment') return { cls: 'badge-warning', label: 'Cuota' };
  return { cls: 'badge-danger', label: 'Gasto' };
}

function groupByDate(events) {
  const groups = new Map();
  for (const ev of events) {
    if (!ev.date) continue;
    if (!groups.has(ev.date)) groups.set(ev.date, []);
    groups.get(ev.date).push(ev);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function renderEventRow(ev) {
  const isIncome = ev.type === 'income';
  const amount = Math.abs(ev.amount_cop ?? ev.amount_signed ?? 0);
  const currency = ev.currency ?? 'COP';
  const amtCls = isIncome ? 'text-success' : 'text-danger';
  const sign = isIncome ? '+' : '−';
  const src = sourceBadge(ev.source);
  const typ = typeBadge(ev.type);

  return `
    <a class="list-row flex justify-between items-center gap-3" data-link="${eventLink(ev)}" href="${eventLink(ev)}">
      <div style="min-width:0;flex:1">
        <div style="font-weight:500">${sanitize(ev.label)}</div>
        <div class="flex gap-2 flex-wrap mt-1">
          <span class="badge ${src.cls}">${src.label}</span>
          <span class="badge ${typ.cls}">${typ.label}</span>
        </div>
      </div>
      <div class="amount ${amtCls}" style="white-space:nowrap;font-weight:600">
        ${sign}${fmtCurrency(amount, currency === 'USD' ? 'USD' : 'COP')}
      </div>
    </a>`;
}

function renderPage(events, days) {
  const grouped = groupByDate(events);

  return `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Vencimientos</h1>
        <p>Próximos ${days} días · ${events.length} evento${events.length !== 1 ? 's' : ''}</p>
      </div>
      <div class="page-actions">
        <div class="btn-group">
          ${DAY_OPTIONS.map(d => `
            <button type="button" class="btn btn-sm ${d === days ? 'btn-primary' : 'btn-ghost'}" data-days="${d}">${d}d</button>
          `).join('')}
        </div>
      </div>
    </div>

    ${grouped.length === 0
      ? emptyState({
          icon: '📅',
          title: 'No hay vencimientos en este periodo',
          hint: 'Prueba ampliar el rango de días o revisa tus recurrentes y deudas.',
        })
      : `
        <div class="card">
          <div class="card-body" style="padding:0">
            ${grouped.map(([date, dayEvents]) => `
              <section>
                <div class="text-soft" style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.06em;padding:12px 16px 8px;font-weight:600;background:var(--fin-surface-2)">
                  ${sanitize(dateGroupLabel(date))}
                </div>
                ${dayEvents.map(renderEventRow).join('')}
              </section>
            `).join('')}
          </div>
        </div>`
    }`;
}

export async function mount(container) {
  let days = 30;

  async function load() {
    container.innerHTML = loadingState({ message: 'Cargando vencimientos…' });
    try {
      const data = await api.cashFlow.upcoming({ days });
      const events = data?.events ?? [];
      container.innerHTML = renderPage(events, days);

      container.querySelectorAll('[data-days]').forEach(btn => {
        btn.addEventListener('click', () => {
          days = parseInt(btn.dataset.days, 10);
          load();
        });
      });
    } catch (err) {
      showError(container, {
        title: 'Vencimientos',
        message: err.message || 'Error al cargar vencimientos',
        onRetry: load,
      });
    }
  }

  await load();
}
