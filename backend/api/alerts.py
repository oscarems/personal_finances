"""
Alerts API endpoints
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.database import get_db
from backend.models import AlertRule
from backend.services.alert_service import get_budget_alerts

router = APIRouter()


class AlertRuleCreate(BaseModel):
    name: str
    category_id: Optional[int] = None
    threshold_percent: float = 1.0
    is_active: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    threshold_percent: Optional[float] = None
    is_active: Optional[bool] = None


@router.get("/rules")
def list_alert_rules(db: Session = Depends(get_db)):
    rules = db.query(AlertRule).order_by(AlertRule.id.desc()).all()
    return [rule.to_dict() for rule in rules]


@router.post("/rules")
def create_alert_rule(rule_data: AlertRuleCreate, db: Session = Depends(get_db)):
    if rule_data.threshold_percent <= 0:
        raise HTTPException(status_code=400, detail="Threshold must be greater than 0")

    rule = AlertRule(
        name=rule_data.name,
        category_id=rule_data.category_id,
        threshold_percent=rule_data.threshold_percent,
        is_active=rule_data.is_active
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.patch("/rules/{rule_id}")
def update_alert_rule(rule_id: int, rule_data: AlertRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(AlertRule).get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    updates = rule_data.dict(exclude_unset=True)
    if "threshold_percent" in updates and updates["threshold_percent"] <= 0:
        raise HTTPException(status_code=400, detail="Threshold must be greater than 0")

    for key, value in updates.items():
        setattr(rule, key, value)

    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/rules/{rule_id}")
def delete_alert_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(AlertRule).get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    db.delete(rule)
    db.commit()
    return {"success": True}


@router.get("/budget")
def get_budget_alerts_endpoint(
    month: Optional[date] = None,
    include_unconfigured: bool = True,
    db: Session = Depends(get_db)
):
    if not month:
        today = date.today()
        month = date(today.year, today.month, 1)
    alerts = get_budget_alerts(db, month, include_unconfigured=include_unconfigured)
    return {
        "month": month.isoformat(),
        "count": len(alerts),
        "alerts": alerts
    }
