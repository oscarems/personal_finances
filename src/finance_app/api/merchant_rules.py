from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models.category import Category
from finance_app.models.merchant_rule import MerchantRule

router = APIRouter()


class MerchantRuleCreate(BaseModel):
    merchant_name: str
    category_id: int


class MerchantRuleUpdate(BaseModel):
    merchant_name: str | None = None
    category_id: int | None = None


@router.get("")
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(MerchantRule).order_by(MerchantRule.merchant_name).all()
    return [r.to_dict() for r in rules]


@router.post("")
def create_rule(body: MerchantRuleCreate, db: Session = Depends(get_db)):
    name = body.merchant_name.strip().upper()
    if not name:
        raise HTTPException(400, "El nombre del comercio no puede estar vacío")

    category = db.query(Category).get(body.category_id)
    if not category:
        raise HTTPException(400, "Categoría no encontrada")

    existing = db.query(MerchantRule).filter_by(merchant_name=name).first()
    if existing:
        raise HTTPException(409, f"Ya existe una regla para '{name}'")

    rule = MerchantRule(merchant_name=name, category_id=body.category_id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: MerchantRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(MerchantRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")

    if body.merchant_name is not None:
        name = body.merchant_name.strip().upper()
        if not name:
            raise HTTPException(400, "El nombre no puede estar vacío")
        conflict = db.query(MerchantRule).filter(
            MerchantRule.merchant_name == name,
            MerchantRule.id != rule_id,
        ).first()
        if conflict:
            raise HTTPException(409, f"Ya existe una regla para '{name}'")
        rule.merchant_name = name

    if body.category_id is not None:
        category = db.query(Category).get(body.category_id)
        if not category:
            raise HTTPException(400, "Categoría no encontrada")
        rule.category_id = body.category_id

    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(MerchantRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    db.delete(rule)
    db.commit()
    return {"deleted": True}
