import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, todayISO } from '../utils.js';
import { openModal } from '../components/modal.js';
import { toast } from '../components/toast.js';

export const title = 'Metas';

let _goals = [];

export async function mount(container) {
  container.innerHTML = '<div class="page-loading"><div class="spinner"></div></div>';
  try {
    _goals = await api.goals.list();
    render(container, _goals);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${sanitize(err.message)}</div>`;
  }
}

function render(container, goals) {
  const active    = goals.filter(g => g.status !== 'achieved' && g.status !== 'cancelled');
  const completed = goals.filter(g => g.status === 'achieved');

  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Metas de Ahorro</h1>
        <p>${active.length} meta${active.length !== 1 ? 's' : ''} activa${active.length !== 1 ? 's' : ''}</p>
      </div>
      <div class="page-header-actions">
        <button class="btn btn-primary" id="btnNewGoal">+ Nueva Meta</button>
      </div>
    </div>

    ${active.length === 0 && completed.length === 0 ? `
      <div class="empty-state">
        <div class="empty-state-icon">🎯</div>
        <h3>Sin metas todavía</h3>
        <p>Crea tu primera meta de ahorro para comenzar.</p>
        <button class="btn btn-primary" id="btnNewGoalEmpty">+ Nueva Meta</button>
      </div>` : ''}

    ${active.length ? `
      <div class="section-grid cols-auto" style="margin-bottom:24px">
        ${active.map(g => goalCard(g)).join('')}
      </div>` : ''}

    ${completed.length ? `
      <h3 style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-soft);margin:0 0 12px;font-weight:600">Completadas</h3>
      <div class="section-grid cols-auto">
        ${completed.map(g => goalCard(g)).join('')}
      </div>` : ''}
  `;

  container.querySelector('#btnNewGoal')?.addEventListener('click', () => openGoalModal(null, container));
  container.querySelector('#btnNewGoalEmpty')?.addEventListener('click', () => openGoalModal(null, container));

  container.querySelectorAll('[data-edit-goal]').forEach(btn => {
    const goal = goals.find(g => g.id === parseInt(btn.dataset.editGoal));
    btn.addEventListener('click', () => openGoalModal(goal, container));
  });

  container.querySelectorAll('[data-contribute-goal]').forEach(btn => {
    const goal = goals.find(g => g.id === parseInt(btn.dataset.contributeGoal));
    btn.addEventListener('click', () => openContributionModal(goal, container));
  });

  container.querySelectorAll('[data-delete-goal]').forEach(btn => {
    const id = parseInt(btn.dataset.deleteGoal);
    btn.addEventListener('click', () => deleteGoal(id, container));
  });
}

function goalCard(g) {
  const current   = g.current_amount ?? 0;
  const target    = g.target_amount ?? 0;
  const currency  = g.currency_code ?? 'COP';
  const pct       = target > 0 ? Math.min(100, (current / target) * 100) : 0;
  const remaining = Math.max(0, target - current);
  const isAchieved = g.status === 'achieved';

  const fillColor = pct >= 100 ? 'var(--color-success)' : pct >= 60 ? 'var(--color-success)' : pct >= 30 ? 'var(--color-warning)' : 'var(--color-danger)';

  // On-track indicator
  const onTrackBadge = _onTrackBadge(g);

  // Projection info
  const projDate = g.projected_achievement_date;
  const reqPerMonth = g.required_per_month ?? g.monthly_required ?? 0;

  return `
    <div class="card ${isAchieved ? 'card-completed' : ''}">
      <div style="padding:16px 20px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:10px">
          <div>
            <div style="font-weight:600;font-size:0.9375rem">🎯 ${sanitize(g.name)}</div>
            ${g.target_date ? `<div style="font-size:0.72rem;color:var(--text-soft)">Fecha límite: ${fmtDate(g.target_date)}</div>` : ''}
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
            ${isAchieved ? '<span class="badge badge-success">✓ Completada</span>' : onTrackBadge}
          </div>
        </div>

        <div class="amount positive" style="font-size:1.25rem;font-weight:600;margin-bottom:2px">
          ${fmtCurrency(current, currency)}
        </div>
        <div style="font-size:0.75rem;color:var(--text-soft);margin-bottom:10px">
          de ${fmtCurrency(target, currency)} meta
        </div>

        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--text-soft);margin-bottom:4px">
            <span>Progreso</span><span>${pct.toFixed(0)}%</span>
          </div>
          <div style="height:6px;background:var(--border-muted);border-radius:3px">
            <div style="height:100%;width:${pct}%;background:${fillColor};border-radius:3px;transition:width .4s"></div>
          </div>
        </div>

        ${remaining > 0 ? `
          <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:0.75rem;color:var(--text-secondary)">
            <span>Faltan: <strong>${fmtCurrency(remaining, currency)}</strong></span>
            ${reqPerMonth > 0 ? `<span>Necesitas: <strong>${fmtCurrency(reqPerMonth, currency)}/mes</strong></span>` : ''}
          </div>` : ''}

        ${projDate && !isAchieved ? `
          <div style="font-size:0.72rem;color:var(--text-soft);margin-top:6px">
            Proyección: ${fmtDate(projDate)}
          </div>` : ''}

        ${g.notes ? `<div style="font-size:0.75rem;color:var(--text-soft);margin-top:8px">${sanitize(g.notes)}</div>` : ''}
      </div>
      <div style="display:flex;gap:8px;padding:10px 20px;border-top:1px solid var(--border-muted);background:var(--bg-surface-muted)">
        ${!isAchieved ? `<button class="btn btn-primary btn-xs" data-contribute-goal="${g.id}">+ Abonar</button>` : ''}
        <button class="btn btn-ghost btn-xs" data-edit-goal="${g.id}">Editar</button>
        <button class="btn btn-ghost btn-xs" style="color:var(--color-danger)" data-delete-goal="${g.id}">Eliminar</button>
      </div>
    </div>`;
}

function _onTrackBadge(g) {
  if (!g.target_date || !g.target_amount) return '';
  const current = g.current_amount ?? 0;
  const target  = g.target_amount;

  const today = new Date();
  const start = g.start_date ? new Date(g.start_date) : new Date(g.created_at);
  const end   = new Date(g.target_date);

  const totalMs   = end - start;
  const elapsedMs = today - start;
  if (totalMs <= 0) return '';

  const expectedPct = Math.min(100, (elapsedMs / totalMs) * 100);
  const actualPct   = target > 0 ? (current / target) * 100 : 0;
  const diff = actualPct - expectedPct;

  if (diff >= -5) {
    return `<span style="font-size:0.68rem;padding:2px 7px;border-radius:10px;background:rgba(34,197,94,0.15);color:var(--color-success);font-weight:600">En camino</span>`;
  } else if (diff >= -20) {
    return `<span style="font-size:0.68rem;padding:2px 7px;border-radius:10px;background:rgba(245,158,11,0.15);color:var(--color-warning);font-weight:600">Leve retraso</span>`;
  } else {
    return `<span style="font-size:0.68rem;padding:2px 7px;border-radius:10px;background:rgba(239,68,68,0.15);color:var(--color-danger);font-weight:600">Atrasado</span>`;
  }
}

function goalFormHtml(g) {
  const goal = g ?? {};
  const today = todayISO();
  return `
    <div class="form-group" style="margin-bottom:16px">
      <label class="form-label required">Nombre</label>
      <input type="text" id="gf-name" value="${sanitize(goal.name ?? '')}" placeholder="Ej: Fondo de emergencia">
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Monto Meta</label>
        <input type="number" id="gf-target" value="${goal.target_amount ?? ''}" step="1000" min="0">
      </div>
      <div class="form-group">
        <label class="form-label">Monto Inicial</label>
        <input type="number" id="gf-start-amount" value="${goal.start_amount ?? '0'}" step="1000" min="0">
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Moneda</label>
        <select id="gf-currency">
          <option value="COP" ${(goal.currency_code ?? 'COP') === 'COP' ? 'selected' : ''}>COP</option>
          <option value="USD" ${goal.currency_code === 'USD' ? 'selected' : ''}>USD</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label required">Fecha Límite</label>
        <input type="date" id="gf-target-date" value="${goal.target_date ?? ''}">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:16px">
      <label class="form-label required">Fecha Inicio</label>
      <input type="date" id="gf-start-date" value="${goal.start_date ?? today}">
    </div>
    <div class="form-group">
      <label class="form-label">Notas</label>
      <textarea id="gf-notes" rows="2">${sanitize(goal.notes ?? '')}</textarea>
    </div>
  `;
}

function openGoalModal(goal, container) {
  const isEdit = !!goal;
  openModal({
    title: isEdit ? `Editar: ${goal.name}` : 'Nueva Meta',
    size: 'md',
    content: goalFormHtml(goal),
    submitLabel: isEdit ? 'Actualizar' : 'Crear',
    onSubmit: async (body) => {
      const currencyIdMap = { COP: 1, USD: 2 };
      const currCode     = body.querySelector('#gf-currency').value;
      const targetDate   = body.querySelector('#gf-target-date').value;
      const startDate    = body.querySelector('#gf-start-date').value;

      const data = {
        name:         body.querySelector('#gf-name').value.trim(),
        target_amount: parseFloat(body.querySelector('#gf-target').value),
        start_amount:  parseFloat(body.querySelector('#gf-start-amount').value || '0'),
        currency_id:  currencyIdMap[currCode] ?? 1,
        target_date:  targetDate || null,
        start_date:   startDate || todayISO(),
        notes:        body.querySelector('#gf-notes').value.trim() || null,
      };

      if (!data.name || !data.target_amount) throw new Error('Nombre y monto son obligatorios');
      if (!data.target_date) throw new Error('La fecha límite es obligatoria');

      if (isEdit) {
        await api.goals.update(goal.id, data);
        toast.success('Meta actualizada');
      } else {
        await api.goals.create(data);
        toast.success('Meta creada');
      }
      _goals = await api.goals.list();
      render(container, _goals);
    },
  });
}

function openContributionModal(goal, container) {
  const currencyIdMap = { COP: 1, USD: 2 };
  const currency = goal.currency_code ?? 'COP';

  openModal({
    title: `Abonar a: ${goal.name}`,
    size: 'sm',
    content: `
      <div style="margin-bottom:16px;font-size:0.875rem;color:var(--text-secondary)">
        Progreso: <strong class="amount positive">${fmtCurrency(goal.current_amount ?? 0, currency)}</strong>
        de ${fmtCurrency(goal.target_amount ?? 0, currency)}
      </div>
      <div class="form-group" style="margin-bottom:16px">
        <label class="form-label required">Monto del abono</label>
        <input type="number" id="cont-amount" value="" step="1000" min="0" placeholder="0">
      </div>
      <div class="form-group">
        <label class="form-label">Fecha</label>
        <input type="date" id="cont-date" value="${todayISO()}">
      </div>
    `,
    submitLabel: 'Abonar',
    onSubmit: async (body) => {
      const amount = parseFloat(body.querySelector('#cont-amount').value);
      const date   = body.querySelector('#cont-date').value;
      if (!amount) throw new Error('Ingresa un monto válido');
      await api.goals.addContribution(goal.id, {
        amount,
        date,
        currency_id: currencyIdMap[currency] ?? 1,
      });
      toast.success('Abono registrado');
      _goals = await api.goals.list();
      render(container, _goals);
    },
  });
}

async function deleteGoal(id, container) {
  if (!confirm('¿Eliminar esta meta?')) return;
  try {
    await api.goals.delete(id);
    toast.success('Meta eliminada');
    _goals = await api.goals.list();
    render(container, _goals);
  } catch (err) {
    toast.error(err.message);
  }
}
