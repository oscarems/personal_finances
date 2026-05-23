from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Account
from finance_app.models.category import Category, CategoryGroup
from finance_app.models.email_sender_rule import EmailSenderRule
from finance_app.services.email_sender_rule_service import extract_sender_pattern

router = APIRouter()


class RuleUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    confirmed_by_user: bool


class RuleCreate(BaseModel):
    sender_pattern: str
    match_type: str = "sender"       # "sender" | "keyword"
    rule_purpose: str = "account"    # "account" | "category"
    account_id: int | None = None
    category_id: int | None = None


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


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    groups = db.query(CategoryGroup).order_by(CategoryGroup.sort_order).all()
    return [
        {
            "id": g.id,
            "name": g.name,
            "categories": [{"id": c.id, "name": c.name} for c in g.categories if not c.is_hidden],
        }
        for g in groups
    ]


@router.patch("/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(EmailSenderRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")

    if rule.rule_purpose == "account":
        if body.account_id is None:
            raise HTTPException(400, "account_id requerido para reglas de cuenta")
        account = db.query(Account).get(body.account_id)
        if not account:
            raise HTTPException(400, "Account not found")
        rule.account_id = body.account_id
    else:
        if body.category_id is None:
            raise HTTPException(400, "category_id requerido para reglas de categoría")
        category = db.query(Category).get(body.category_id)
        if not category:
            raise HTTPException(400, "Category not found")
        rule.category_id = body.category_id

    rule.confirmed_by_user = body.confirmed_by_user
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.post("")
def create_rule(body: RuleCreate, db: Session = Depends(get_db)):
    match_type = body.match_type if body.match_type in ("sender", "keyword") else "sender"
    rule_purpose = body.rule_purpose if body.rule_purpose in ("account", "category") else "account"

    if match_type == "sender":
        pattern = extract_sender_pattern(body.sender_pattern) if "@" in body.sender_pattern else body.sender_pattern.strip().lower()
    else:
        keywords = [k.strip().lower() for k in body.sender_pattern.split(",") if k.strip()]
        if not keywords:
            raise HTTPException(400, "Debes ingresar al menos una palabra clave")
        pattern = ", ".join(dict.fromkeys(keywords))

    existing = db.query(EmailSenderRule).filter_by(sender_pattern=pattern, rule_purpose=rule_purpose).first()
    if existing:
        raise HTTPException(409, "Ya existe una regla con este patrón y propósito")

    account_id = None
    category_id = None

    if rule_purpose == "account":
        if body.account_id is None:
            raise HTTPException(400, "account_id requerido para reglas de cuenta")
        account = db.query(Account).get(body.account_id)
        if not account:
            raise HTTPException(400, "Account not found")
        account_id = body.account_id
    else:
        if body.category_id is None:
            raise HTTPException(400, "category_id requerido para reglas de categoría")
        category = db.query(Category).get(body.category_id)
        if not category:
            raise HTTPException(400, "Category not found")
        category_id = body.category_id

    rule = EmailSenderRule(
        sender_pattern=pattern,
        match_type=match_type,
        rule_purpose=rule_purpose,
        account_id=account_id,
        category_id=category_id,
        match_count=0,
        last_seen=datetime.utcnow(),
        confirmed_by_user=True,
    )
    db.add(rule)
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
