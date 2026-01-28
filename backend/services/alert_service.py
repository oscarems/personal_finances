from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import calendar
from sqlalchemy.orm import Session

from backend.models import AlertRule, Category, BudgetAlertState
from backend.services.budget_service import get_month_budget
from config import (
    BUDGET_ALERT_DEFAULT_THRESHOLDS,
    BUDGET_ALERT_DEFAULT_PACING_MARGINS,
    BUDGET_ALERT_CATEGORY_OVERRIDES,
    BUDGET_ALERT_COOLDOWN_DAYS
)

ALERT_SEVERITY_ORDER = {
    "OK": 0,
    "WARNING": 1,
    "RISK": 2,
    "CRITICAL": 3
}

ALERT_STATE_LABELS = {
    "OK": "OK",
    "WARNING": "ADVERTENCIA",
    "RISK": "RIESGO",
    "CRITICAL": "CRÍTICO"
}


def _get_period_progress(month_date: date, today: Optional[date] = None) -> Tuple[float, int]:
    """
    Calcula el % esperado de gasto con base en el progreso del periodo.

    Retorna:
        expected_percent (float): porcentaje esperado (0-100)
        days_remaining (int): días restantes en el periodo
    """
    current_day = today or date.today()
    days_in_month = calendar.monthrange(month_date.year, month_date.month)[1]
    period_start = date(month_date.year, month_date.month, 1)
    period_end = date(month_date.year, month_date.month, days_in_month)

    if current_day < period_start:
        elapsed_days = 0
        days_remaining = days_in_month
    elif current_day > period_end:
        elapsed_days = days_in_month
        days_remaining = 0
    else:
        elapsed_days = current_day.day
        days_remaining = (period_end - current_day).days

    expected_percent = (elapsed_days / days_in_month) * 100 if days_in_month else 0
    return expected_percent, days_remaining


def _resolve_category_config(category: Category) -> Dict[str, Dict[str, int]]:
    override = None
    if category.id in BUDGET_ALERT_CATEGORY_OVERRIDES:
        override = BUDGET_ALERT_CATEGORY_OVERRIDES[category.id]
    elif category.name in BUDGET_ALERT_CATEGORY_OVERRIDES:
        override = BUDGET_ALERT_CATEGORY_OVERRIDES[category.name]

    thresholds = dict(BUDGET_ALERT_DEFAULT_THRESHOLDS)
    pacing_margins = dict(BUDGET_ALERT_DEFAULT_PACING_MARGINS)

    if override:
        thresholds.update(override.get("thresholds", {}))
        pacing_margins.update(override.get("pacing_margins", {}))

    return {
        "thresholds": thresholds,
        "pacing_margins": pacing_margins
    }


def _state_from_thresholds(percent_spent: float, thresholds: Dict[str, int]) -> str:
    if percent_spent >= thresholds["critical"]:
        return "CRITICAL"
    if percent_spent >= thresholds["risk"]:
        return "RISK"
    if percent_spent >= thresholds["warning"]:
        return "WARNING"
    return "OK"


def _state_from_pacing(
    percent_spent: float,
    expected_percent: float,
    pacing_margins: Dict[str, int]
) -> Tuple[str, float]:
    overage = percent_spent - expected_percent
    if overage >= pacing_margins["critical"]:
        return "CRITICAL", overage
    if overage >= pacing_margins["risk"]:
        return "RISK", overage
    if overage >= pacing_margins["warning"]:
        return "WARNING", overage
    return "OK", overage


def _choose_final_state(threshold_state: str, pacing_state: str) -> str:
    return threshold_state if ALERT_SEVERITY_ORDER[threshold_state] >= ALERT_SEVERITY_ORDER[pacing_state] else pacing_state


def _format_amount(amount: float, currency_code: str) -> str:
    decimals = 0 if currency_code == "COP" else 2
    return f"{amount:,.{decimals}f}"


def _build_alert_message(
    category_name: str,
    percent_spent: float,
    spent: float,
    assigned: float,
    days_remaining: int,
    currency_code: str,
    final_state: str,
    threshold_state: str,
    pacing_state: str,
    expected_percent: float
) -> str:
    percent_label = f"{percent_spent:.0f}%"
    spent_text = _format_amount(spent, currency_code)
    assigned_text = _format_amount(assigned, currency_code)

    if ALERT_SEVERITY_ORDER[pacing_state] > ALERT_SEVERITY_ORDER[threshold_state]:
        pacing_reason = f"con solo {expected_percent:.0f}% del mes transcurrido. Ritmo alto."
        return (
            f"{category_name}: {percent_label} ({spent_text} / {assigned_text}) "
            f"{pacing_reason} Quedan {days_remaining} días. Estado: {ALERT_STATE_LABELS[final_state]}."
        )

    return (
        f"{category_name}: {percent_label} ({spent_text} / {assigned_text}). "
        f"Quedan {days_remaining} días. Estado: {ALERT_STATE_LABELS[final_state]}."
    )


def _should_notify(
    current_state: str,
    last_state: Optional[str],
    last_notified_at: Optional[datetime],
    cooldown_days: int
) -> bool:
    if current_state == "OK":
        return False
    if last_state is None or current_state != last_state:
        return True
    if not last_notified_at:
        return True
    return datetime.utcnow() - last_notified_at >= timedelta(days=cooldown_days)


def get_budget_alerts(
    db: Session,
    month_date: date,
    include_unconfigured: bool = True,
    currency_code: str = "COP"
) -> List[dict]:
    budget_data = get_month_budget(db, month_date, currency_code)
    expected_percent, days_remaining = _get_period_progress(month_date)

    rules = db.query(AlertRule).filter(
        AlertRule.rule_type == "budget_threshold",
        AlertRule.is_active == True
    ).all()
    rules_by_category = {rule.category_id: rule for rule in rules if rule.category_id}

    alerts = []
    category_states = []
    period_key = month_date.strftime("%Y-%m")
    existing_states = db.query(BudgetAlertState).filter(
        BudgetAlertState.period_key == period_key
    ).all()
    state_by_category = {state.category_id: state for state in existing_states}

    for group in budget_data.get("groups", []):
        if group.get("is_income"):
            continue

        for cat in group.get("categories", []):
            category = db.query(Category).get(cat["category_id"])
            if not category or not category.category_group or category.category_group.is_income:
                continue

            rule = rules_by_category.get(cat["category_id"])
            if not rule and not include_unconfigured:
                continue

            assigned = cat.get("assigned") or 0.0
            activity = cat.get("activity") or 0.0
            spent = abs(activity)

            if assigned <= 0 and spent > 0:
                percent_spent = 100.0
            elif assigned <= 0:
                percent_spent = 0.0
            else:
                percent_spent = (spent / assigned) * 100

            config = _resolve_category_config(category)
            thresholds = config["thresholds"]
            pacing_margins = config["pacing_margins"]

            threshold_state = _state_from_thresholds(percent_spent, thresholds)
            pacing_state, _ = _state_from_pacing(percent_spent, expected_percent, pacing_margins)
            final_state = _choose_final_state(threshold_state, pacing_state)

            category_states.append({
                "category_id": cat["category_id"],
                "state": final_state
            })

            state_record = state_by_category.get(cat["category_id"])
            last_state = state_record.last_state if state_record else None
            last_notified_at = state_record.last_notified_at if state_record else None
            should_notify = _should_notify(final_state, last_state, last_notified_at, BUDGET_ALERT_COOLDOWN_DAYS)

            if not state_record:
                state_record = BudgetAlertState(
                    category_id=cat["category_id"],
                    period_key=period_key,
                    last_state=final_state
                )
                db.add(state_record)
            else:
                state_record.last_state = final_state

            if should_notify:
                state_record.last_notified_at = datetime.utcnow()

            if final_state == "OK" or not should_notify:
                continue

            alerts.append({
                "category_id": cat["category_id"],
                "category_name": cat["category_name"],
                "state": final_state,
                "state_label": ALERT_STATE_LABELS[final_state],
                "assigned": assigned,
                "spent": spent,
                "percent_spent": round(percent_spent, 2),
                "expected_percent": round(expected_percent, 2),
                "days_remaining": days_remaining,
                "threshold_state": threshold_state,
                "pacing_state": pacing_state,
                "currency_code": currency_code,
                "message": _build_alert_message(
                    cat["category_name"],
                    percent_spent,
                    spent,
                    assigned,
                    days_remaining,
                    currency_code,
                    final_state,
                    threshold_state,
                    pacing_state,
                    expected_percent
                )
            })

    db.commit()

    alerts.sort(key=lambda item: ALERT_SEVERITY_ORDER[item["state"]], reverse=True)
    return {
        "alerts": alerts,
        "category_states": category_states,
        "expected_percent": expected_percent,
        "days_remaining": days_remaining,
        "cooldown_days": BUDGET_ALERT_COOLDOWN_DAYS
    }
