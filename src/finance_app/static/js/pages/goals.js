import * as api from '../api/client.js';
import { fmtCurrency, fmtDate, sanitize, progressBar, todayISO } from '../utils.js';
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
  const active   = goals.filter(g => !g.is_completed);
  const completed= goals.filter(g => g.is_completed);

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
  const current  = g.current_amount ?? g.saved_amount ?? 0;
  const target   = g.target_amount ?? g.goal_amount ?? 0;
  const currency = g.currency_code ?? 'COP';
  const pct      = target > 0 ? Math.min(100, (current / target) * 100) : 0;
  const remaining= Math.max(0, target - current);
  const fillClass= pct >= 100 ? 'ok' : pct >= 60 ? 'ok' : pct >= 30 ? 'warning' : 'danger';

  return `
    <div class="card ${g.is_completed ? 'card-completed' : ''}">
      <div style="padding:16px 20px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px">
          <div>
            <div style="font-weight:600;font-size:0.9375rem">
              ${g.icon ? g.icon + ' ' : '🎯 '}${sanitize(g.name)}
            </div>
            ${g.deadline ? `<div style="font-size:0.72rem;color:var(--text-soft)">Fecha límite: ${fmtDate(g.deadline)}</div>` : ''}
          </div>
          ${g.is_completed ? '<span class="badge badge-success">✓ Completada</span>' : ''}
        </div>

        <div class="amount positive" style="font-size:1.25rem;font-weight:600;margin-bottom:4px">
          ${fmtCurrency(current, currency)}
        </div>
        <div style="font-size:0.75rem;color:var(--text-soft);margin-bottom:10px">
          de ${fmtCurrency(target, currency)} meta
        </div>

        <div style="margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--text-soft);margin-bottom:4px">
            <span>Progreso</span><span>${pct.toFixed(0)}%</span>
          </div>
          <div class="progress-wrap">
            <div class="progress-fill ${fillClass}" style="width:${pct}%"></div>
          </div>
        </div>

        ${remaining > 0 ? `<div style="font-size:0.75rem;color:var(--text-secondary)">Faltan: ${fmtCurrency(remaining, currency)}</div>` : ''}
        ${g.notes ? `<div style="font-size:0.75rem;color:var(--text-soft);margin-top:8px">${sanitize(g.notes)}</div>` : ''}
      </div>
      <div style="display:flex;gap:8px;padding:10px 20px;border-top:1px solid var(--border-muted);background:var(--bg-surface-muted)">
        ${!g.is_completed ? `<button class="btn btn-primary btn-xs" data-contribute-goal="${g.id}">+ Abonar</button>` : ''}
        <button class="btn btn-ghost btn-xs" data-edit-goal="${g.id}">Editar</button>
        <button class="btn btn-ghost btn-xs" style="color:var(--color-danger)" data-delete-goal="${g.id}">Eliminar</button>
      </div>
    </div>`;
}

function goalFormHtml(g) {
  const goal = g ?? {};
  return `
    <div class="form-group" style="margin-bottom:16px">
      <label class="form-label required">Nombre</label>
      <input type="text" id="gf-name" value="${sanitize(goal.name ?? '')}" placeholder="Ej: Fondo de emergencia">
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label required">Monto Meta</label>
        <input type="number" id="gf-target" value="${goal.target_amount ?? goal.goal_amount ?? ''}" step="1000" min="0">
      </div>
      <div class="form-group">
        <label class="form-label">Monto Actual</label>
        <input type="number" id="gf-current" value="${goal.current_amount ?? goal.saved_amount ?? ''}" step="1000" min="0">
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
        <label class="form-label">Fecha Límite</label>
        <input type="date" id="gf-deadline" value="${goal.deadline ?? ''}">
      </div>
    </div>
    <div class="form-row cols-2">
      <div class="form-group">
        <label class="form-label">Ícono</label>
        <input type="text" id="gf-icon" value="${sanitize(goal.icon ?? '')}" placeholder="🎯" maxlength="4">
      </div>
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
      const currCode = body.querySelector('#gf-currency').value;
      const data = {
        name:           body.querySelector('#gf-name').value.trim(),
        target_amount:  parseFloat(body.querySelector('#gf-target').value),
        current_amount: parseFloat(body.querySelector('#gf-current').value || '0'),
        currency_id:    currencyIdMap[currCode] ?? 1,
        deadline:       body.querySelector('#gf-deadline').value || null,
        icon:           body.querySelector('#gf-icon').value.trim() || null,
        notes:          body.querySelector('#gf-notes').value.trim() || null,
      };
      if (!data.name || !data.target_amount) throw new Error('Nombre y monto son obligatorios');
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
  openModal({
    title: `Abonar a: ${goal.name}`,
    size: 'sm',
    content: `
      <div style="margin-bottom:16px;font-size:0.875rem;color:var(--text-secondary)">
        Progreso actual: <strong class="amount positive">${fmtCurrency(goal.current_amount ?? 0, goal.currency_code ?? 'COP')}</strong>
        de ${fmtCurrency(goal.target_amount ?? 0, goal.currency_code ?? 'COP')}
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
      await api.goals.addContribution(goal.id, { amount, date });
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
