import { progressPct } from '../utils.js';

/** Flatten API budget groups into enriched category rows (same shape as budget page). */
export function flattenBudgetGroups(data) {
  const cats = [];
  for (const group of (data?.groups ?? [])) {
    for (const cat of (group.categories ?? [])) {
      cats.push({
        ...cat,
        group: group.name,
        group_id: group.id,
        category_type: group.is_income
          ? 'income'
          : (cat.rollover_type === 'accumulate' ? 'savings' : 'expense'),
        spent: group.is_income
          ? Math.abs(cat.activity ?? 0)
          : Math.max(0, -(cat.activity ?? 0)),
        available: cat.available ?? 0,
        covered: cat.covered ?? 0,
      });
    }
  }
  return cats;
}

/** Uncapped spent/limit % (can exceed 100). Savings use assigned + saved pool, not assigned alone. */
export function usagePercent(spent, limit) {
  const s = spent ?? 0;
  const lim = limit ?? 0;
  if (lim <= 0) return s > 0 ? 101 : 0;
  return (s / lim) * 100;
}

export function savingsPool(cat) {
  return (cat.assigned ?? 0) + (cat.initial_amount ?? 0);
}

/** Limit used for the usage bar: assigned for expenses, assigned+guardado for savings. */
export function categoryUsageLimit(cat) {
  if (cat.category_type === 'savings') return savingsPool(cat);
  return cat.assigned ?? 0;
}

/**
 * @returns {'none'|'ok'|'warn'|'danger'}
 * Expense: danger only if spent > assigned (>100%).
 * Savings: danger only if spent more than available (available < 0).
 */
export function categoryUsageStatus(cat) {
  if (cat.category_type === 'income') return 'none';

  const assigned = cat.assigned ?? 0;
  const spent = cat.spent ?? 0;
  const available = cat.available ?? 0;

  if (cat.category_type === 'savings') {
    return available < 0 && spent > 0 ? 'danger' : 'ok';
  }

  if (assigned <= 0) return spent > 0 ? 'danger' : 'none';
  return spent > assigned ? 'danger' : 'ok';
}

export function categoryUsagePct(cat) {
  return usagePercent(cat.spent ?? 0, categoryUsageLimit(cat));
}

export function expenseOverspendAmount(cat) {
  if (cat.category_type !== 'expense') return 0;
  return Math.max(0, (cat.spent ?? 0) - (cat.assigned ?? 0));
}

export function expenseSpentExcludingSavings(flatCats) {
  return (flatCats ?? [])
    .filter(c => c.category_type === 'expense')
    .reduce((s, c) => s + (c.spent ?? 0), 0);
}

const STATUS_RANK = { danger: 0, warn: 1, ok: 2, none: 3 };

/** Categories that need attention: only those past 100% (or savings past available). */
export function getAttentionCategories(flatCats, { limit = 5 } = {}) {
  return flatCats
    .filter(c => c.category_type !== 'income')
    .map(c => ({ cat: c, status: categoryUsageStatus(c), pct: categoryUsagePct(c) }))
    .filter(x => x.status === 'danger')
    .sort((a, b) => {
      const sr = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (sr !== 0) return sr;
      return b.pct - a.pct;
    })
    .slice(0, limit)
    .map(({ cat, status, pct }) => ({
      category_id: cat.category_id,
      name: cat.category_name,
      group: cat.group,
      assigned: cat.assigned ?? 0,
      spent: cat.spent ?? 0,
      available: cat.available ?? 0,
      pct_used: Math.round(pct),
      status,
      is_savings: cat.category_type === 'savings',
    }));
}

export function sortCategoriesBySeverity(cats) {
  return [...cats].sort((a, b) => {
    const sa = categoryUsageStatus(a);
    const sb = categoryUsageStatus(b);
    const rank = STATUS_RANK[sa] - STATUS_RANK[sb];
    if (rank !== 0) return rank;
    return categoryUsagePct(b) - categoryUsagePct(a);
  });
}

export function statusTone(status) {
  if (status === 'danger') return 'var(--fin-danger)';
  if (status === 'warn') return 'var(--fin-amber)';
  return 'var(--fin-success)';
}

export function statusLabel(status, pct, { isSavings = false } = {}) {
  if (status === 'danger') {
    if (isSavings) return 'Más de lo disponible';
    return pct > 100 ? `${Math.round(pct)}% · pasado` : 'En rojo';
  }
  if (status === 'warn') return `${Math.round(pct)}% usado`;
  return 'OK';
}

export function progressTone(pct) {
  if (pct > 100) return 'var(--fin-danger)';
  if (pct >= 80) return 'var(--fin-amber)';
  return 'var(--fin-success)';
}

/** Toast hint after saving a transaction against a category budget. */
export function budgetImpactMessage(cat) {
  if (!cat || cat.category_type === 'income') return null;
  const assigned = cat.assigned ?? 0;
  const spent = cat.spent ?? 0;
  const name = cat.category_name || 'Categoría';
  const status = categoryUsageStatus(cat);
  const pct = categoryUsagePct(cat);

  if (status === 'danger') {
    if (cat.category_type === 'savings') {
      return `${name}: gastaste más de lo disponible`;
    }
    return `${name}: ${Math.round(pct)}% del presupuesto — te pasaste`;
  }
  if (assigned <= 0) return null;
  const barPct = progressPct(spent, categoryUsageLimit(cat));
  if (barPct >= 80) {
    return `${name}: ${Math.round(pct)}% del presupuesto`;
  }
  return `${name}: ${Math.round(pct)}% usado · quedan ${Math.round(Math.max(0, 100 - pct))}%`;
}
