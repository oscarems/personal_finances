const BASE = '/api';

async function request(method, path, body = null, params = null) {
  let url = BASE + path;
  if (params) {
    const q = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ''))
    );
    if (q.toString()) url += '?' + q;
  }
  const res = await fetch(url, {
    method,
    headers: body !== null ? { 'Content-Type': 'application/json' } : {},
    body: body !== null ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    let detailObj = null;
    try {
      const j = await res.json();
      if (Array.isArray(j.detail)) {
        detail = j.detail.map(e => e.msg || JSON.stringify(e)).join('; ');
      } else if (j.detail && typeof j.detail === 'object') {
        detailObj = j.detail;
        detail = j.detail.message ?? JSON.stringify(j.detail);
      } else {
        detail = j.detail ?? JSON.stringify(j);
      }
    } catch {}
    const err = new Error(detail);
    if (detailObj) err.detail = detailObj;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

function parseMonth(m) {
  const [year, month] = m.split('-').map(Number);
  return { year, month };
}

const get  = (p, params) => request('GET',    p, null, params);
const post = (p, body)   => request('POST',   p, body);
const put  = (p, body)   => request('PUT',    p, body);
const del  = (p)         => request('DELETE', p);
const patch= (p, body)   => request('PATCH',  p, body);

export const accounts = {
  list:   (params) => get('/accounts', params),
  get:    (id)     => get(`/accounts/${id}`),
  create: (data)   => post('/accounts', data),
  update: (id, d)  => put(`/accounts/${id}`, d),
  delete: (id)     => del(`/accounts/${id}`),
  adjust: (id, d)  => post(`/accounts/${id}/adjust`, d),
};

export const transactions = {
  list:     (params) => get('/transactions', params),
  get:      (id)     => get(`/transactions/${id}`),
  create:   (data)   => post('/transactions', data),
  update:   (id, d)  => put(`/transactions/${id}`, d),
  delete:   (id)     => del(`/transactions/${id}`),
  transfer: (data)   => post('/transactions/transfer', data),
};

export const budgets = {
  current:       ()             => get('/budgets/current'),
  month:         (m)            => { const { year, month } = parseMonth(m); return get(`/budgets/month/${year}/${month}`); },
  update:        (m, catId, d)  => post('/budgets/assign', { category_id: catId, amount: d.assigned, month: m + '-01', currency_code: d.currency_code ?? 'COP', ...(d.initial_amount !== undefined ? { initial_amount: d.initial_amount } : {}) }),
  setInitial:    (m, catId, d)  => post('/budgets/assign', { category_id: catId, amount: 0, month: m + '-01', currency_code: d.currency_code, initial_amount: d.initial_amount }),
  initialize:    (m)            => { const { year, month } = parseMonth(m); return post(`/budgets/initialize/${year}/${month}`); },
  coverExcess:   (d)            => post('/budgets/cover-overspending', d),
  assignedTotals:()             => get('/budgets/assigned-totals'),
  readyToAssign: ()             => get('/budgets/ready-to-assign').catch(() => null),
};

export const categories = {
  list:        (params) => get('/categories', params),
  create:      (data)   => post('/categories', data),
  update:      (id, d)  => patch(`/categories/${id}`, d),
  delete:      (id)     => del(`/categories/${id}`),
  deleteForce: (id)     => request('DELETE', `/categories/${id}`, null, { force: true }),
  seed:        ()       => post('/categories/seed'),
  groups:      ()       => get('/categories/groups'),
  createGroup: (data)   => post('/categories/groups', data),
  updateGroup: (id, d)  => patch(`/categories/groups/${id}`, d),
  deleteGroup: (id, force) => request('DELETE', `/categories/groups/${id}`, null, force ? { force: true } : null),
};

export const debts = {
  list:         ()     => get('/debts'),
  get:          (id)   => get(`/debts/${id}`),
  amortization: (id)   => get(`/debts/${id}/amortization`),
  simulate:     (data) => post('/debts/simulate', data),
  timeline:     ()     => get('/debts/timeline').catch(() => []),
};

export const goals = {
  list:            ()       => get('/goals'),
  create:          (data)   => post('/goals', data),
  update:          (id, d)  => put(`/goals/${id}`, d),
  delete:          (id)     => del(`/goals/${id}`),
  addContribution: (id, d)  => post(`/goals/${id}/contributions`, d),
};

export const mortgage = {
  accounts:    ()     => get('/mortgage/accounts').catch(() => []),
  schedule:    (id)   => get(`/mortgage/${id}/schedule`),
  payment:     (id,d) => post(`/mortgage/${id}/payments`, d),
  calculate:   (data) => post('/mortgage/calculate', data),
};

export const investmentSimulator = {
  simulate: (data) => post('/investment-simulator/simulate', data),
};

export const emergencyFund = {
  coverage:       (params) => get('/emergency-fund/coverage', params),
  categories:     ()       => get('/emergency-fund/categories').catch(() => []),
  updateCategory: (id, flags) => patch(`/emergency-fund/categories/${id}`, flags),
};

export const reports = {
  spending:       (params) => get('/reports/spending', params),
  balance:        (params) => get('/reports/balance', params),
  income:         (params) => get('/reports/income', params),
  financialHealth:(params) => get('/reports/financial-health', params),
  debt:           (params) => get('/reports/debt', params),
};

export const recurring = {
  list:     ()       => get('/recurring'),
  create:   (data)   => post('/recurring', data),
  update:   (id, d)  => put(`/recurring/${id}`, d),
  delete:   (id)     => del(`/recurring/${id}`),
  generate: ()       => post('/recurring/generate'),
};

export const emailSenderRules = {
  list:   ()       => get('/email-sender-rules'),
  create: (data)   => post('/email-sender-rules', data),
  update: (id, d)  => put(`/email-sender-rules/${id}`, d),
  delete: (id)     => del(`/email-sender-rules/${id}`),
};

export const gmailImport = {
  emails:      (params)            => get('/import/gmail/emails', params),
  models:      ()                  => get('/import/gmail/models'),
  preview:     (messageId)         => get(`/import/gmail/preview/${encodeURIComponent(messageId)}`),
  process:     (messageId, model)  => post(`/import/gmail/process/${encodeURIComponent(messageId)}${model ? `?model=${encodeURIComponent(model)}` : ''}`),
  confirm:     (data)              => post('/import/gmail/confirm', data),
  bulkConfirm: (data)              => post('/import/gmail/bulk-confirm', data),
  reset:       (messageId)         => post(`/import/gmail/reset/${encodeURIComponent(messageId)}`),
  bulkReset:   (data)              => post('/import/gmail/bulk-reset', data),
  skip:        (messageId)         => post(`/import/gmail/skip/${encodeURIComponent(messageId)}`),
};

export const merchantRules = {
  list:   ()           => get('/merchant-rules'),
  create: (data)       => post('/merchant-rules', data),
  update: (id, data)   => put(`/merchant-rules/${id}`, data),
  delete: (id)         => del(`/merchant-rules/${id}`),
};

export const chat = {
  query: (data) => post('/chat/query', data),
};

export const patrimonio = {
  summary:     ()       => get('/patrimonio/resumen').catch(() => null),
  assets:      ()       => get('/patrimonio/activos').catch(() => []),
  createAsset: (data)   => post('/patrimonio/activos', data),
  updateAsset: (id, d)  => put(`/patrimonio/activos/${id}`, d),
  deleteAsset: (id)     => del(`/patrimonio/activos/${id}`),
};

export const exchangeRates = {
  list:    ()  => get('/exchange-rates'),
  current: ()  => get('/exchange-rates/current').catch(() => ({ USD: 1, COP: 1 })),
  sync:    ()  => post('/exchange-rates/sync'),
};

export const alerts = {
  list:    ()   => get('/alerts').catch(() => []),
  dismiss: (id) => post(`/alerts/${id}/dismiss`),
};

export const cashFlow = {
  projection: (params) => get('/cash-flow/projection', params).catch(() => null),
};

export const setup = {
  status:   ()     => get('/setup/status'),
  complete: (data) => post('/setup/complete', data),
};

export const currencies = {
  list: () => get('/currencies').catch(() => [{ code: 'COP' }, { code: 'USD' }]),
};

export const admin = {
  health: () => get('/admin/health'),
  syncEmail: () => post('/admin/sync-email'),
};
