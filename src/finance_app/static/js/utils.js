export function fmtCOP(amount) {
  return new Intl.NumberFormat('es-CO', {
    style: 'currency', currency: 'COP',
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(amount ?? 0);
}

export function fmtUSD(amount) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(amount ?? 0);
}

export function fmtCurrency(amount, currency = 'COP') {
  return currency === 'USD' ? fmtUSD(amount) : fmtCOP(amount);
}

export function fmtNumber(n, decimals = 0) {
  return new Intl.NumberFormat('es-CO', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  }).format(n ?? 0);
}

export function fmtPercent(value, decimals = 1) {
  return `${((value ?? 0) * 100).toFixed(decimals)}%`;
}

export function fmtDate(dateStr) {
  if (!dateStr) return '—';
  const [y, m, d] = (dateStr.includes('T') ? dateStr.split('T')[0] : dateStr).split('-');
  return `${d}/${m}/${y}`;
}

export function fmtDateShort(dateStr) {
  if (!dateStr) return '—';
  const [, m, d] = (dateStr.includes('T') ? dateStr.split('T')[0] : dateStr).split('-');
  return `${d}/${m}`;
}

export function fmtMonthLabel(month) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(y, m - 1);
  const label = d.toLocaleDateString('es-CO', { month: 'long', year: 'numeric' });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function prevMonth(month) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(y, m - 2);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function nextMonth(month) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(y, m);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function todayISO() {
  return new Date().toISOString().split('T')[0];
}

export function sanitize(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

export function amountClass(amount) {
  if ((amount ?? 0) > 0) return 'positive';
  if ((amount ?? 0) < 0) return 'negative';
  return '';
}

export function progressFillClass(used, total) {
  if (!total || total <= 0) return 'ok';
  const pct = used / total;
  if (pct >= 1) return 'danger';
  if (pct >= 0.8) return 'warning';
  return 'ok';
}

export function progressPct(used, total) {
  if (!total || total <= 0) return 0;
  return Math.min(100, (used / total) * 100);
}

export function progressBar(used, total) {
  const pct = progressPct(used, total);
  const cls = progressFillClass(used, total);
  return `
    <div class="progress-wrap">
      <div class="progress-fill ${cls}" style="width:${pct}%"></div>
    </div>`;
}

export function accountTypeLabel(type) {
  const map = {
    checking: 'Corriente', savings: 'Ahorros',
    credit_card: 'Tarjeta Crédito', credit_loan: 'Crédito',
    mortgage: 'Hipoteca', cdt: 'CDT',
    investment: 'Inversión', cash: 'Efectivo',
  };
  return map[type] ?? type ?? '—';
}

export function accountTypeIcon(type) {
  const map = {
    checking: '🏦', savings: '💰', credit_card: '💳',
    credit_loan: '📋', mortgage: '🏠', cdt: '📊',
    investment: '📈', cash: '💵',
  };
  return map[type] ?? '💼';
}

export function debounce(fn, ms = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

export function groupBy(arr, key) {
  return arr.reduce((acc, item) => {
    const k = typeof key === 'function' ? key(item) : item[key];
    (acc[k] ??= []).push(item);
    return acc;
  }, {});
}

export function sortBy(arr, key, dir = 'asc') {
  return [...arr].sort((a, b) => {
    const av = typeof key === 'function' ? key(a) : a[key];
    const bv = typeof key === 'function' ? key(b) : b[key];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return dir === 'asc' ? cmp : -cmp;
  });
}
