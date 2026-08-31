"""Lightweight read-only snapshot for mobile / offline cache."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session, joinedload

from finance_app.models import Account
from finance_app.services.budget_service import get_month_budget

DEBT_ACCOUNT_TYPES = frozenset({'credit_card', 'credit_loan', 'mortgage'})


def _category_attention(group: dict, cat: dict) -> dict | None:
    if group.get('is_income'):
        return None

    assigned = float(cat.get('assigned') or 0)
    activity = float(cat.get('activity') or 0)
    spent = max(0.0, -activity)
    available = float(cat.get('available') or 0)
    is_savings = cat.get('rollover_type') == 'accumulate'
    initial = float(cat.get('initial_amount') or 0)

    if is_savings:
        if available >= 0 or spent <= 0:
            return None
        pool = assigned + initial
        pct = (spent / pool * 100.0) if pool > 0 else 101.0
    else:
        if spent <= assigned and not (assigned <= 0 and spent > 0):
            return None
        pct = (spent / assigned * 100.0) if assigned > 0 else 101.0

    return {
        'category_id': cat['category_id'],
        'name': cat['category_name'],
        'group': group.get('name') or '',
        'assigned': round(assigned, 2),
        'spent': round(spent, 2),
        'available': round(available, 2),
        'pct_used': round(pct, 1),
        'status': 'danger',
        'is_savings': is_savings,
    }


def build_mobile_snapshot(db: Session, currency_code: str = 'COP') -> dict:
    today = date.today()
    month_date = date(today.year, today.month, 1)
    budget = get_month_budget(db, month_date, currency_code) or {}

    attention: list[dict] = []
    total_savings = 0.0

    for group in budget.get('groups') or []:
        for cat in group.get('categories') or []:
            if cat.get('rollover_type') == 'accumulate':
                total_savings += float(cat.get('available') or 0)
            item = _category_attention(group, cat)
            if item:
                attention.append(item)

    attention.sort(key=lambda x: (0 if x['status'] == 'danger' else 1, -x['pct_used']))
    attention = attention[:8]

    accounts = (
        db.query(Account)
        .options(joinedload(Account.currency))
        .filter(Account.is_closed.is_(False))
        .all()
    )

    by_currency: dict[str, float] = {}
    budget_liquid = 0.0
    for acc in accounts:
        code = acc.currency.code if acc.currency else 'COP'
        bal = float(acc.balance or 0)
        by_currency[code] = by_currency.get(code, 0.0) + bal
        if acc.is_budget and acc.type not in DEBT_ACCOUNT_TYPES:
            budget_liquid += bal if code == currency_code else bal  # COP display path

    totals = budget.get('totals') or {}

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'month': month_date.strftime('%Y-%m'),
        'currency': currency_code,
        'ready_to_assign': round(float(budget.get('ready_to_assign') or 0), 2),
        'totals': {
            'available': round(float(totals.get('available') or 0), 2),
            'savings': round(total_savings, 2),
            'in_accounts': round(float(totals.get('in_accounts') or budget_liquid or 0), 2),
        },
        'accounts_by_currency': {k: round(v, 2) for k, v in by_currency.items()},
        'attention': attention,
    }
