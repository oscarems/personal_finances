"""
Financial health endpoint: 50/30/20 rule, pay-yourself-first, emergency fund coverage.
"""
from typing import Optional
from datetime import date

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Category, CategoryGroup, Currency, Transaction
from finance_app.services.budget_service import (
    build_income_transactions_query,
    build_spent_transactions_query,
)
from finance_app.services.emergency_fund_service import calculate_emergency_coverage

from .common import get_exchange_rate, convert_to_currency

router = APIRouter()


@router.get("/financial-health")
def get_financial_health(
    month: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db),
):
    """Analyse financial health for a given month using transaction data."""
    today = date.today()
    if month:
        year, mo = month.split("-")
        month_date = date(int(year), int(mo), 1)
    else:
        month_date = today.replace(day=1)

    month_end = month_date + relativedelta(months=1)
    exchange_rate = get_exchange_rate(db)

    # ---- Income: from actual transactions ----
    # build_income_transactions_query already joins Category and CategoryGroup
    income_txs = (
        build_income_transactions_query(db, month_date, month_end)
        .with_entities(Transaction.amount, Transaction.currency_id, Category.name)
        .all()
    )

    income_total = 0.0
    income_sources: dict[str, float] = {}
    for t in income_txs:
        amount = convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        income_total += amount
        src_name = t.name or "Sin categoría"
        income_sources[src_name] = income_sources.get(src_name, 0) + amount

    no_income = income_total == 0

    # ---- 50/30/20 buckets from actual spending transactions ----
    # build_spent_transactions_query already joins Category and CategoryGroup
    spent_txs = (
        build_spent_transactions_query(db, month_date, month_end)
        .with_entities(
            Transaction.amount,
            Transaction.currency_id,
            Category.name.label("cat_name"),
            Category.is_essential,
            Category.rollover_type,
            CategoryGroup.name.label("group_name"),
        )
        .all()
    )

    needs_cats: dict[tuple[str, str], float] = {}
    wants_cats: dict[tuple[str, str], float] = {}
    savings_cats: dict[tuple[str, str], float] = {}

    for t in spent_txs:
        amt = convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
        key = (t.cat_name, t.group_name)

        if t.rollover_type == "accumulate":
            savings_cats[key] = savings_cats.get(key, 0) + amt
        elif t.is_essential:
            needs_cats[key] = needs_cats.get(key, 0) + amt
        else:
            wants_cats[key] = wants_cats.get(key, 0) + amt

    needs_total = sum(needs_cats.values())
    wants_total = sum(wants_cats.values())
    savings_total = sum(savings_cats.values())

    def _pct(value: float) -> float:
        if no_income:
            return 0.0
        return round(value / income_total * 100, 2)

    assigned_pct = _pct(needs_total) + _pct(wants_total) + _pct(savings_total)
    unassigned_pct = round(max(0.0, 100.0 - assigned_pct), 2) if not no_income else 0.0

    def _cat_list(bucket: dict[tuple[str, str], float]) -> list[dict]:
        items = [
            {"name": name, "group": group, "amount": amt}
            for (name, group), amt in bucket.items()
        ]
        items.sort(key=lambda x: x["amount"], reverse=True)
        return items

    # ---- Emergency fund ----
    ef = calculate_emergency_coverage(db, month_date, currency_id)

    # ---- Currency ----
    currency = db.query(Currency).get(currency_id)
    currency_code = currency.code if currency else "COP"

    result: dict = {
        "month": month_date.strftime("%Y-%m"),
        "currency_code": currency_code,
        "income": {
            "total": income_total,
            "sources": [
                {"name": name, "amount": amt}
                for name, amt in sorted(income_sources.items(), key=lambda x: x[1], reverse=True)
            ],
        },
        "rule_50_30_20": {
            "needs": {
                "amount": needs_total,
                "pct_of_income": _pct(needs_total),
                "categories": _cat_list(needs_cats),
            },
            "wants": {
                "amount": wants_total,
                "pct_of_income": _pct(wants_total),
                "categories": _cat_list(wants_cats),
            },
            "savings": {
                "amount": savings_total,
                "pct_of_income": _pct(savings_total),
                "categories": _cat_list(savings_cats),
            },
            "unassigned_pct": unassigned_pct,
        },
        "pay_yourself_first": {
            "savings_amount": savings_total,
            "savings_pct": _pct(savings_total),
            "income_total": income_total,
        },
        "emergency_fund": {
            "months_coverage": ef["months_coverage"],
            "emergency_funds_total": ef["emergency_funds_total"],
            "essential_expenses_total": ef["essential_expenses_total"],
            "status": ef["status"],
        },
    }

    if no_income:
        result["no_income_data"] = True

    return result
