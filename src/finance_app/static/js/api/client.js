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
const del  = (p, params) => request('DELETE', p, null, params);
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
  delete:   (id, opts) => del(`/transactions/${id}`, opts),
  transfer: (data)   => post('/transactions/transfer', data),
  reimburse:(id, d)  => post(`/transactions/${id}/reimburse`, d),
};

export const budgets = {
  current:       ()             => get('/budgets/current'),
  month:         (m)            => { const { year, month } = parseMonth(m); return get(`/budgets/month/${year}/${month}`); },
  update:        (m, catId, d)  => post('/budgets/assign', { category_id: catId, amount: d.assigned, month: m + '-01', currency_code: d.currency_code ?? 'COP', ...(d.initial_amount !== undefined ? { initial_amount: d.initial_amount } : {}) }),
  setInitial:    (m, catId, d)  => post('/budgets/assign', { category_id: catId, amount: 0, month: m + '-01', currency_code: d.currency_code, initial_amount: d.initial_amount }),
  initialize:    (m)            => { const { year, month } = parseMonth(m); return post(`/budgets/initialize/${year}/${month}`); },
  coverExcess:   (d)            => post('/budgets/cover-overspending', d),
  updateCoverExcess: (txId, d)  => put(`/budgets/cover-overspending/${txId}`, d),
  assignedTotals:()             => get('/budgets/assigned-totals'),
  readyToAssign: ()             => get('/budgets/ready-to-assign'),
  recalcSavings: ()             => post('/budgets/recalculate-savings'),
  exportUrl:     (params = {})  => {
    const q = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== '')));
    return `/api/budgets/export${q.toString() ? '?' + q : ''}`;
  },
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
  list:               ()              => get('/debts'),
  get:                (id)            => get(`/debts/${id}`),
  summary:            ()              => get('/debts/summary'),
  schedule:           (id, mode)      => get(`/debts/${id}/schedule`, { mode: mode ?? 'plan' }),
  costAnalysis:       (id)            => get(`/debts/${id}/cost-analysis`),
  simulate:           (params)        => get('/debts/simulator', params),
  timeline:           ()              => get('/debts/timeline'),
  create:             (data)          => post('/debts', data),
  update:             (id, data)      => patch(`/debts/${id}`, data),
  delete:             (id)            => del(`/debts/${id}`),
  payments:           (id)            => get(`/debts/${id}/payments`),
  addPayment:         (id, data)      => post(`/debts/${id}/payments`, data),
  installments:       (id)            => get(`/debts/${id}/installments`),
  createInstallment:  (id, data)      => post(`/debts/${id}/installments`, data),
  updateInstallment:  (id, iid, data) => patch(`/debts/${id}/installments/${iid}`, data),
  deleteInstallment:  (id, iid)       => del(`/debts/${id}/installments/${iid}`),
  strategyComparison: (params)        => get('/debts/strategy-comparison', params),
  exportUrl:          '/api/debts/export',
};

export const goals = {
  list:            ()       => get('/goals'),
  create:          (data)   => post('/goals', data),
  update:          (id, d)  => put(`/goals/${id}`, d),
  delete:          (id)     => del(`/goals/${id}`),
  addContribution: (id, d)  => post(`/goals/${id}/contributions`, d),
};

export const mortgage = {
  accounts:    ()     => get('/mortgage/accounts'),
  schedule:    (id)   => get(`/mortgage/${id}/schedule`),
  calculate:   (data) => post('/mortgage/calculate', data),
};

export const investmentSimulator = {
  simulate: (data) => post('/investment-simulator/simulate', data),
};

export const emergencyFund = {
  coverage:       (params) => get('/emergency-fund/coverage', params),
  categories:     ()       => get('/emergency-fund/categories'),
  updateCategory: (id, flags) => patch(`/emergency-fund/categories/${id}`, flags),
};

export const reports = {
  spending:           (params) => get('/reports/spending', params),
  balance:            (params) => get('/reports/balance', params),
  income:             (params) => get('/reports/income', params),
  summary:            (params) => get('/reports/summary', params),
  cashflowSummary:    (params) => get('/reports/cashflow-summary', params),
  financialHealth:    (params) => get('/reports/financial-health', params),
  debt:               (params) => get('/reports/debt', params),
  budgetIncomeExpenses: (params) => get('/reports/budget-income-expenses', params),
  savingsRate:        (params) => get('/reports/savings-rate', params),
  netWorthTimeline:   ()       => get('/reports/net-worth-timeline'),
  spendingByCategory: (params) => get('/reports/spending-by-category', params),
  spendingOverTime:   (params) => get('/reports/spending-by-category-over-time', params),
  spendingByPayee:    (params) => get('/reports/spending-by-payee', params),
  monthComparison:    (params) => get('/reports/month-comparison', params),
  spendingExportUrl:  (params = {}) => {
    const q = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== '')));
    return `/api/reports/spending/export${q.toString() ? '?' + q : ''}`;
  },
};

export const recurring = {
  list:     ()       => get('/recurring'),
  create:   (data)   => post('/recurring', data),
  update:   (id, d)  => put(`/recurring/${id}`, d),
  delete:   (id)     => del(`/recurring/${id}`),
  generate: ()       => post('/recurring/generate'),
  upcoming: (params) => get('/recurring/upcoming', params),
  approve:  (id, d)  => post(`/recurring/${id}/approve`, d ?? {}),
  skip:     (id, d)  => post(`/recurring/${id}/skip`, d ?? {}),
  snooze:   (id, d)  => post(`/recurring/${id}/snooze`, d ?? {}),
};

export const search = {
  query: (q, limit = 8) => get('/search', { q, limit }),
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
  reprocessAll: (data)             => post('/import/gmail/reprocess-all', data ?? {}),
};

export const merchantRules = {
  list:    ()           => get('/merchant-rules'),
  create:  (data)       => post('/merchant-rules', data),
  update:  (id, data)   => put(`/merchant-rules/${id}`, data),
  delete:  (id)         => del(`/merchant-rules/${id}`),
  preview: (data)       => post('/merchant-rules/preview', data),
};

export const merchantIgnoreRules = {
  list:   ()           => get('/merchant-ignore-rules'),
  create: (data)       => post('/merchant-ignore-rules', data),
  delete: (id)         => del(`/merchant-ignore-rules/${id}`),
};

export const chat = {
  query: (data) => post('/chat/query', data),
};

export const patrimonio = {
  summary:     ()       => get('/patrimonio/resumen'),
  assets:      ()       => get('/patrimonio/activos'),
  createAsset: (data)   => post('/patrimonio/activos', data),
  updateAsset: (id, d)  => put(`/patrimonio/activos/${id}`, d),
  deleteAsset: (id)     => del(`/patrimonio/activos/${id}`),
  exportUrl:   '/api/patrimonio/export',
};

export const exchangeRates = {
  list:    ()  => get('/exchange-rates'),
  current: ()  => get('/exchange-rates/current'),
  sync:    ()  => post('/exchange-rates/sync'),
};

export const alerts = {
  budget:  (params) => get('/alerts/budget', params),
  smart:   (params) => get('/alerts/smart-notifications', params),
  count:   (params) => get('/alerts/count', params),
  rules:   {
    list:   ()        => get('/alerts/rules'),
    create: (data)    => post('/alerts/rules', data),
    update: (id, d)   => patch(`/alerts/rules/${id}`, d),
    delete: (id)      => del(`/alerts/rules/${id}`),
  },
};

export const whatIf = {
  simulate: (params) => get('/what-if', params),
};

export const mobile = {
  snapshot: (params) => get('/mobile/snapshot', params),
};

export const cashFlow = {
  forecast:  (params) => get('/cash-flow/forecast', params),
  upcoming:  (params) => get('/cash-flow/upcoming', params),
};

export const reconciliation = {
  summary:     (params)  => get('/reconciliation/summary', params),
  markCleared: (data)    => post('/reconciliation/mark-cleared', data),
  createSession: (data)  => post('/reconciliation/sessions', data),
  sessions:    (accountId) => get(`/reconciliation/sessions/${accountId}`),
};

export const setup = {
  status:   ()     => get('/setup/status'),
  complete: (data) => post('/setup/complete', data),
};

export const currencies = {
  list: () => get('/currencies'),
};

export const admin = {
  health: () => get('/admin/health'),
  syncEmail: () => post('/admin/sync-email'),
  backupUrl: '/api/admin/backup',
};

/** Portfolio & FIRE live under `/api/v1/...` (legacy prefix on those routers). */
export const portfolio = {
  assets:      ()         => get('/v1/portfolio/assets'),
  createAsset: (data)     => post('/v1/portfolio/assets', data),
  deleteAsset: (id)       => del(`/v1/portfolio/assets/${id}`),
  addPrice:    (id, data) => post(`/v1/portfolio/assets/${id}/prices`, data),
  prices:      (id)       => get(`/v1/portfolio/assets/${id}/prices`),
};

export const fire = {
  dashboard: () => get('/v1/fire'),
};
