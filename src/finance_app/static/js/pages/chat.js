import * as api from '../api/client.js';
import { sanitize } from '../utils.js';

export const title = 'Chat SQL';

const EXAMPLES = [
  'SELECT * FROM transactions ORDER BY date DESC LIMIT 10',
  'SELECT category_name, SUM(amount) as total FROM transactions GROUP BY category_name ORDER BY total DESC',
  'SELECT account_name, balance FROM accounts WHERE is_closed = 0',
  'SELECT strftime(\'%Y-%m\', date) as month, SUM(amount) as total FROM transactions WHERE transaction_type = \'expense\' GROUP BY month',
];

export async function mount(container) {
  container.innerHTML = `
    <div class="page-header">
      <div class="page-header-text">
        <h1>Chat SQL</h1>
        <p>Consulta la base de datos directamente con SQL.</p>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 220px;gap:20px">
      <div>
        <div class="card" style="margin-bottom:16px">
          <div class="card-body" style="padding:16px">
            <div class="form-group" style="margin-bottom:12px">
              <label class="form-label">Consulta SQL</label>
              <textarea id="chat-query" rows="5" placeholder="SELECT * FROM transactions LIMIT 10" style="font-family:var(--font-mono);font-size:0.8125rem"></textarea>
            </div>
            <div style="display:flex;justify-content:flex-end;gap:8px">
              <button class="btn btn-secondary btn-sm" id="btnClear">Limpiar</button>
              <button class="btn btn-primary" id="btnRun">
                ▶ Ejecutar
              </button>
            </div>
          </div>
        </div>
        <div id="chat-result"></div>
      </div>

      <div>
        <div class="card">
          <div class="card-header"><span class="card-title">Ejemplos</span></div>
          <div class="card-body" style="padding:8px">
            ${EXAMPLES.map((q, i) => `
              <button class="btn btn-ghost btn-xs" data-example="${i}" style="display:block;text-align:left;white-space:normal;margin-bottom:8px;width:100%;font-family:var(--font-mono);font-size:0.7rem;line-height:1.4;padding:8px">
                ${sanitize(q)}
              </button>`).join('')}
          </div>
        </div>
      </div>
    </div>
  `;

  const queryEl  = container.querySelector('#chat-query');
  const resultEl = container.querySelector('#chat-result');

  container.querySelector('#btnRun').addEventListener('click', () => runQuery(queryEl.value, resultEl));
  container.querySelector('#btnClear').addEventListener('click', () => {
    queryEl.value = '';
    resultEl.innerHTML = '';
  });

  container.querySelectorAll('[data-example]').forEach(btn => {
    btn.addEventListener('click', () => {
      queryEl.value = EXAMPLES[parseInt(btn.dataset.example)];
    });
  });

  // Ctrl+Enter to run
  queryEl.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runQuery(queryEl.value, resultEl);
  });
}

async function runQuery(sql, resultEl) {
  if (!sql.trim()) return;
  resultEl.innerHTML = '<div class="page-loading" style="min-height:80px"><div class="spinner"></div></div>';

  try {
    const result = await api.chat.query({ query: sql.trim() });
    const rows   = result?.rows ?? result?.results ?? result?.data ?? [];
    const cols   = result?.columns ?? result?.headers ?? (rows.length ? Object.keys(rows[0]) : []);
    const elapsed= result?.elapsed_ms ?? null;

    if (!rows.length) {
      resultEl.innerHTML = `<div class="empty-state"><p>${rows === null ? 'Sin resultados' : `0 filas${elapsed != null ? ` · ${elapsed}ms` : ''}`}</p></div>`;
      return;
    }

    resultEl.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:0.8rem;color:var(--text-secondary)">${rows.length} fila${rows.length !== 1 ? 's' : ''}${elapsed != null ? ` · ${elapsed}ms` : ''}</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>${cols.map(c => `<th>${sanitize(String(c))}</th>`).join('')}</tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>${cols.map(c => `<td style="font-size:0.8rem;font-family:var(--font-mono)">${sanitize(String(row[c] ?? ''))}</td>`).join('')}</tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (err) {
    resultEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> ${sanitize(err.message)}</div>`;
  }
}
