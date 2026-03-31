"""
Financial health endpoint: 50/30/20 rule, pay-yourself-first, emergency fund coverage.
"""
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from finance_app.database import get_db
from finance_app.models import BudgetMonth, Category, CategoryGroup, Currency
from finance_app.services.emergency_fund_service import calculate_emergency_coverage

from .common import get_exchange_rate, convert_to_currency

router = APIRouter()


@router.get("/financial-health")
def get_financial_health(
    month: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db),
):
    """Analyse financial health for a given month using budget data."""
    today = date.today()
    if month:
        year, mo = month.split("-")
        month_date = date(int(year), int(mo), 1)
    else:
        month_date = today.replace(day=1)

    exchange_rate = get_exchange_rate(db)

    # Fetch all budget rows for the month with category + group eagerly loaded
    budgets = (
        db.query(BudgetMonth)
        .join(Category, BudgetMonth.category_id == Category.id)
        .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
        .options(
            joinedload(BudgetMonth.category).joinedload(Category.category_group),
        )
        .filter(BudgetMonth.month == month_date)
        .all()
    )

    # ---- Income: sum activity for income groups ----
    income_total = 0.0
    income_sources: dict[str, float] = {}
    for bm in budgets:
        cat = bm.category
        if not cat or not cat.category_group:
            continue
        if cat.category_group.is_income:
            amount = convert_to_currency(
                bm.activity or 0, bm.currency_id, currency_id, exchange_rate
            )
            income_total += amount
            income_sources[cat.name] = income_sources.get(cat.name, 0) + amount

    no_income = income_total == 0

    # ---- 50/30/20 buckets ----
    needs_cats: dict[tuple[str, str], float] = {}
    wants_cats: dict[tuple[str, str], float] = {}
    savings_cats: dict[tuple[str, str], float] = {}

    for bm in budgets:
        cat = bm.category
        if not cat or not cat.category_group:
            continue
        if cat.category_group.is_income:
            continue

        group_name = cat.category_group.name
        cat_name = cat.name

        if cat.rollover_type == "accumulate":
            amount = convert_to_currency(
                bm.assigned or 0, bm.currency_id, currency_id, exchange_rate
            )
            key = (cat_name, group_name)
            savings_cats[key] = savings_cats.get(key, 0) + amount
        elif cat.is_essential:
            amount = convert_to_currency(
                abs(bm.activity or 0), bm.currency_id, currency_id, exchange_rate
            )
            key = (cat_name, group_name)
            needs_cats[key] = needs_cats.get(key, 0) + amount
        else:
            amount = convert_to_currency(
                abs(bm.activity or 0), bm.currency_id, currency_id, exchange_rate
            )
            key = (cat_name, group_name)
            wants_cats[key] = wants_cats.get(key, 0) + amount

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
