from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Account
from finance_app.models.email_sender_rule import EmailSenderRule

router = APIRouter()


class RuleUpdate(BaseModel):
    account_id: int
    confirmed_by_user: bool


@router.get("")
def list_rules(confirmed: bool | None = None, db: Session = Depends(get_db)):
    q = db.query(EmailSenderRule)
    if confirmed is not None:
        q = q.filter_by(confirmed_by_user=confirmed)
    rules = q.order_by(
        EmailSenderRule.confirmed_by_user.asc(),
        EmailSenderRule.match_count.desc(),
    ).all()
    return [r.to_dict() for r in rules]


@router.patch("/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(EmailSenderRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    account = db.query(Account).get(body.account_id)
    if not account:
        raise HTTPException(400, "Account not found")
    rule.account_id = body.account_id
    rule.confirmed_by_user = body.confirmed_by_user
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(EmailSenderRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    db.delete(rule)
    db.commit()
    return {"deleted": True}
