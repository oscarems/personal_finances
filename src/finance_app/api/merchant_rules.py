import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models.category import Category
from finance_app.models.merchant_rule import MerchantRule
from finance_app.models.transaction import Transaction
from finance_app.services.merchant_rule_engine import match_rule

router = APIRouter()

VALID_FIELDS = {"payee", "memo"}
VALID_OPERATORS = {"contains", "equals", "starts_with", "regex"}


class MerchantRuleCreate(BaseModel):
    merchant_name: str
    category_id: int
    field: str = "payee"
    operator: str = "contains"
    priority: int = 0

    @field_validator("field")
    @classmethod
    def _valid_field(cls, v):
        if v not in VALID_FIELDS:
            raise ValueError(f"Campo inválido: {v}")
        return v

    @field_validator("operator")
    @classmethod
    def _valid_operator(cls, v):
        if v not in VALID_OPERATORS:
            raise ValueError(f"Operador inválido: {v}")
        return v


class MerchantRuleUpdate(BaseModel):
    merchant_name: str | None = None
    category_id: int | None = None
    field: str | None = None
    operator: str | None = None
    priority: int | None = None

    @field_validator("field")
    @classmethod
    def _valid_field(cls, v):
        if v is not None and v not in VALID_FIELDS:
            raise ValueError(f"Campo inválido: {v}")
        return v

    @field_validator("operator")
    @classmethod
    def _valid_operator(cls, v):
        if v is not None and v not in VALID_OPERATORS:
            raise ValueError(f"Operador inválido: {v}")
        return v


class MerchantRulePreview(BaseModel):
    field: str
    operator: str
    value: str

    @field_validator("field")
    @classmethod
    def _valid_field(cls, v):
        if v not in VALID_FIELDS:
            raise ValueError(f"Campo inválido: {v}")
        return v

    @field_validator("operator")
    @classmethod
    def _valid_operator(cls, v):
        if v not in VALID_OPERATORS:
            raise ValueError(f"Operador inválido: {v}")
        return v


def _normalize_value(value: str, operator: str) -> str:
    value = value.strip()
    # No forzamos mayúsculas en regex: podría romper patrones case-sensitive intencionales.
    if operator != "regex":
        value = value.upper()
    return value


def _check_duplicate(db: Session, field: str, operator: str, name: str, exclude_id: int | None = None):
    query = db.query(MerchantRule).filter(
        MerchantRule.field == field,
        MerchantRule.operator == operator,
        MerchantRule.merchant_name == name,
    )
    if exclude_id is not None:
        query = query.filter(MerchantRule.id != exclude_id)
    return query.first()


@router.get("")
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(MerchantRule).order_by(MerchantRule.merchant_name).all()
    return [r.to_dict() for r in rules]


@router.post("/preview")
def preview_rule(body: MerchantRulePreview, db: Session = Depends(get_db)):
    value = body.value.strip()
    if not value:
        return {"matches": [], "total": 0}

    if body.operator == "regex":
        try:
            re.compile(value)
        except re.error as exc:
            raise HTTPException(400, f"Expresión regular inválida: {exc}")

    class _FakeRule:
        field = body.field
        operator = body.operator
        merchant_name = value

    fake_rule = _FakeRule()

    transactions = (
        db.query(Transaction)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(500)
        .all()
    )

    matches = []
    for tx in transactions:
        payee_name = tx.payee.name if tx.payee else None
        if match_rule(fake_rule, payee_name, tx.memo):
            matches.append(tx)
        if len(matches) >= 15:
            break

    return {
        "matches": [
            {
                "date": tx.date.isoformat() if tx.date else None,
                "payee_name": tx.payee.name if tx.payee else None,
                "memo": tx.memo,
                "amount": tx.amount,
                "currency": tx.currency.code if tx.currency else None,
                "category_name": tx.category.name if tx.category else None,
            }
            for tx in matches
        ],
        "total": len(matches),
    }


@router.post("")
def create_rule(body: MerchantRuleCreate, db: Session = Depends(get_db)):
    name = _normalize_value(body.merchant_name, body.operator)
    if not name:
        raise HTTPException(400, "El valor de la regla no puede estar vacío")

    if body.operator == "regex":
        try:
            re.compile(name)
        except re.error as exc:
            raise HTTPException(400, f"Expresión regular inválida: {exc}")

    category = db.get(Category, body.category_id)
    if not category:
        raise HTTPException(400, "Categoría no encontrada")

    if _check_duplicate(db, body.field, body.operator, name):
        raise HTTPException(409, f"Ya existe una regla equivalente para '{name}'")

    rule = MerchantRule(
        merchant_name=name,
        category_id=body.category_id,
        field=body.field,
        operator=body.operator,
        priority=body.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: MerchantRuleUpdate, db: Session = Depends(get_db)):
    rule = db.get(MerchantRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")

    new_field = body.field if body.field is not None else rule.field
    new_operator = body.operator if body.operator is not None else rule.operator

    if body.merchant_name is not None or body.field is not None or body.operator is not None:
        raw_name = body.merchant_name if body.merchant_name is not None else rule.merchant_name
        name = _normalize_value(raw_name, new_operator)
        if not name:
            raise HTTPException(400, "El valor de la regla no puede estar vacío")

        if new_operator == "regex":
            try:
                re.compile(name)
            except re.error as exc:
                raise HTTPException(400, f"Expresión regular inválida: {exc}")

        if _check_duplicate(db, new_field, new_operator, name, exclude_id=rule_id):
            raise HTTPException(409, f"Ya existe una regla equivalente para '{name}'")

        rule.merchant_name = name
        rule.field = new_field
        rule.operator = new_operator

    if body.category_id is not None:
        category = db.get(Category, body.category_id)
        if not category:
            raise HTTPException(400, "Categoría no encontrada")
        rule.category_id = body.category_id

    if body.priority is not None:
        rule.priority = body.priority

    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(MerchantRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    db.delete(rule)
    db.commit()
    return {"deleted": True}
