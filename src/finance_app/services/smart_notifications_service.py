"""
Smart Notifications Service

Generates contextual, date-aware notifications for the dashboard:
- Recurring payment reminders based on last month's transactions
- Budget pacing warnings (spending too fast relative to month progress)
- Upcoming debt payments
"""
from datetime import date, timedelta
import calendar
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from finance_app.models import Transaction, Category, CategoryGroup, Payee, Account, Debt
from finance_app.services.budget_service import get_month_budget


def _format_cop(amount: float) -> str:
    return f"${abs(amount):,.0f}"


def _format_amount(amount: float, currency_code: str = "COP") -> str:
    if currency_code == "USD":
        return f"US${abs(amount):,.2f}"
    return _format_cop(amount)


def _get_enabled_category_ids(db: Session) -> Optional[set]:
    """Return set of category IDs with smart_notif_enabled=True, or None if all enabled."""
    cats = db.query(Category.id, Category.smart_notif_enabled).all()
    # If all are enabled (or column doesn't exist yet), return None = no filtering
    disabled = [c.id for c in cats if c.smart_notif_enabled is False]
    if not disabled:
        return None
    return {c.id for c in cats if c.smart_notif_enabled is not False}


def get_smart_notifications(
    db: Session,
    today: Optional[date] = None,
    currency_code: str = "COP",
    day_window: int = 3,
) -> List[Dict]:
    """
    Returns a list of smart notification dicts, each with:
      - type: 'reminder' | 'budget_warning' | 'debt_upcoming' | 'info'
      - icon: emoji
      - title: short headline
      - message: descriptive text
      - severity: 'info' | 'warning' | 'danger' | 'success'
    """
    today = today or date.today()
    notifications: List[Dict] = []

    # Get enabled category IDs for filtering
    enabled_cat_ids = _get_enabled_category_ids(db)

    notifications.extend(_payment_reminders(db, today, day_window, currency_code, enabled_cat_ids))
    notifications.extend(_budget_pacing_warnings(db, today, currency_code, enabled_cat_ids))
    notifications.extend(_upcoming_debt_payments(db, today))
    notifications.extend(_month_comparison(db, today, currency_code, enabled_cat_ids))

    return notifications


def _payment_reminders(
    db: Session, today: date, day_window: int, currency_code: str,
    enabled_cat_ids: Optional[set] = None,
) -> List[Dict]:
    """
    Find transactions from last month around the same day and remind the user.
    E.g., 'Around this date last month you paid Agua ($85,000)'.
    """
    notifications = []

    # Last month same window
    if today.month == 1:
        last_month = date(today.year - 1, 12, 1)
    else:
        last_month = date(today.year, today.month - 1, 1)

    last_month_days = calendar.monthrange(last_month.year, last_month.month)[1]
    target_day = min(today.day, last_month_days)

    window_start = date(last_month.year, last_month.month, max(1, target_day - day_window))
    window_end = date(last_month.year, last_month.month, min(last_month_days, target_day + day_window))

    # Find expense transactions in that window, grouped by payee
    rows = (
        db.query(
            Payee.name,
            Category.name.label("category_name"),
            func.sum(Transaction.amount).label("total"),
        )
        .join(Payee, Transaction.payee_id == Payee.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.date >= window_start,
            Transaction.date <= window_end,
            Transaction.amount < 0,
            Transaction.transfer_account_id.is_(None),
            Transaction.is_adjustment == False,
        )
    )
    if enabled_cat_ids is not None:
        rows = rows.filter(Transaction.category_id.in_(enabled_cat_ids))
    rows = (
        rows
        .group_by(Payee.name, Category.name)
        .having(func.sum(Transaction.amount) < -10000 if currency_code == "COP" else func.sum(Transaction.amount) < -5)
        .order_by(func.sum(Transaction.amount))
        .limit(5)
        .all()
    )

    for row in rows:
        payee_name = row[0]
        cat_name = row[1] or ""
        amount = abs(row[2])
        cat_label = f" ({cat_name})" if cat_name else ""
        notifications.append({
            "type": "reminder",
            "icon": "🔔",
            "title": "Recordatorio de pago",
            "message": f"Por estas fechas el mes pasado pagaste <strong>{payee_name}</strong>{cat_label} por {_format_amount(amount, currency_code)}.",
            "severity": "info",
        })

    return notifications


def _budget_pacing_warnings(
    db: Session, today: date, currency_code: str,
    enabled_cat_ids: Optional[set] = None,
) -> List[Dict]:
    """
    Warn when spending in a category is ahead of the month's pace.
    E.g., 'Llevas 65% del presupuesto de Salidas pero solo va 40% del mes'.
    """
    notifications = []
    month_start = date(today.year, today.month, 1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    month_progress = today.day / days_in_month

    # Only warn if we're at least a few days in
    if today.day < 3:
        return notifications

    budget_data = get_month_budget(db, month_start, currency_code)

    for group in budget_data.get("groups", []):
        if group.get("is_income"):
            continue
        for cat in group.get("categories", []):
            assigned = cat.get("assigned") or 0
            if assigned <= 0:
                continue
            if enabled_cat_ids is not None and cat["category_id"] not in enabled_cat_ids:
                continue
            # accumulate categories (savings) don't apply
            if cat.get("rollover_type") == "accumulate":
                continue

            activity = abs(cat.get("activity") or 0)
            spent_pct = activity / assigned
            # Warn if spent % is significantly ahead of month progress
            if spent_pct >= 0.8 and month_progress < 0.5:
                notifications.append({
                    "type": "budget_warning",
                    "icon": "⚠️",
                    "title": "Presupuesto en riesgo",
                    "message": (
                        f"Llevas <strong>{spent_pct:.0%}</strong> del presupuesto de "
                        f"<strong>{cat['category_name']}</strong> "
                        f"({_format_amount(activity, currency_code)} de {_format_amount(assigned, currency_code)}) "
                        f"y solo va el <strong>{month_progress:.0%}</strong> del mes."
                    ),
                    "severity": "danger",
                })
            elif spent_pct >= 0.6 and month_progress < 0.4:
                notifications.append({
                    "type": "budget_warning",
                    "icon": "🟡",
                    "title": "Gasto acelerado",
                    "message": (
                        f"Ya usaste <strong>{spent_pct:.0%}</strong> del presupuesto de "
                        f"<strong>{cat['category_name']}</strong> "
                        f"y solo va el <strong>{month_progress:.0%}</strong> del mes. Ten cuidado."
                    ),
                    "severity": "warning",
                })
            elif spent_pct >= 1.0:
                notifications.append({
                    "type": "budget_warning",
                    "icon": "🔴",
                    "title": "Presupuesto excedido",
                    "message": (
                        f"Te pasaste del presupuesto de <strong>{cat['category_name']}</strong>: "
                        f"gastaste {_format_amount(activity, currency_code)} de {_format_amount(assigned, currency_code)} asignados."
                    ),
                    "severity": "danger",
                })

    return notifications


def _upcoming_debt_payments(db: Session, today: date) -> List[Dict]:
    """
    Remind about debts with payment_day close to today.
    """
    notifications = []
    debts = db.query(Debt).filter(Debt.is_active == True).all()

    for debt in debts:
        payment_day = getattr(debt, "payment_day", None)
        if not payment_day:
            continue
        days_until = payment_day - today.day
        if 0 <= days_until <= 5:
            label = "hoy" if days_until == 0 else f"en {days_until} día{'s' if days_until > 1 else ''}"
            notifications.append({
                "type": "debt_upcoming",
                "icon": "📅",
                "title": "Pago de deuda próximo",
                "message": f"El pago de <strong>{debt.name}</strong> vence <strong>{label}</strong> (día {payment_day}).",
                "severity": "warning" if days_until <= 2 else "info",
            })

    return notifications


def _month_comparison(db: Session, today: date, currency_code: str,
                      enabled_cat_ids: Optional[set] = None) -> List[Dict]:
    """
    Compare total spending up to this day vs last month same period.
    """
    notifications = []
    month_start = date(today.year, today.month, 1)

    if today.month == 1:
        last_month_start = date(today.year - 1, 12, 1)
    else:
        last_month_start = date(today.year, today.month - 1, 1)

    last_month_days = calendar.monthrange(last_month_start.year, last_month_start.month)[1]
    last_month_same_day = date(
        last_month_start.year, last_month_start.month, min(today.day, last_month_days)
    )

    def _total_spent(start: date, end: date) -> float:
        q = (
            db.query(func.sum(Transaction.amount))
            .filter(
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.amount < 0,
                Transaction.transfer_account_id.is_(None),
                Transaction.is_adjustment == False,
            )
        )
        if enabled_cat_ids is not None:
            q = q.filter(Transaction.category_id.in_(enabled_cat_ids))
        return abs(q.scalar() or 0)

    current_spent = _total_spent(month_start, today)
    last_spent = _total_spent(last_month_start, last_month_same_day)

    if last_spent > 0 and current_spent > 0:
        diff_pct = ((current_spent - last_spent) / last_spent) * 100
        if diff_pct > 20:
            notifications.append({
                "type": "info",
                "icon": "📊",
                "title": "Comparación mensual",
                "message": (
                    f"Llevas <strong>{_format_amount(current_spent, currency_code)}</strong> gastados este mes, "
                    f"un <strong>{diff_pct:.0f}% más</strong> que a esta misma fecha el mes pasado "
                    f"({_format_amount(last_spent, currency_code)})."
                ),
                "severity": "warning",
            })
        elif diff_pct < -20:
            notifications.append({
                "type": "info",
                "icon": "👏",
                "title": "Buen ritmo de gasto",
                "message": (
                    f"Llevas <strong>{_format_amount(current_spent, currency_code)}</strong> gastados, "
                    f"un <strong>{abs(diff_pct):.0f}% menos</strong> que a esta fecha el mes pasado. ¡Sigue así!"
                ),
                "severity": "success",
            })

    return notifications
