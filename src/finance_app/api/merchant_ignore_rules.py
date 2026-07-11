from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models.merchant_ignore_rule import MerchantIgnoreRule

router = APIRouter()


class MerchantIgnoreRuleCreate(BaseModel):
    merchant_name: str


@router.get("")
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(MerchantIgnoreRule).order_by(MerchantIgnoreRule.merchant_name).all()
    return [r.to_dict() for r in rules]


@router.post("")
def create_rule(body: MerchantIgnoreRuleCreate, db: Session = Depends(get_db)):
    name = body.merchant_name.strip().upper()
    if not name:
        raise HTTPException(400, "El nombre del comercio no puede estar vacío")

    existing = db.query(MerchantIgnoreRule).filter_by(merchant_name=name).first()
    if existing:
        raise HTTPException(409, f"Ya existe una regla para ignorar '{name}'")

    rule = MerchantIgnoreRule(merchant_name=name)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule.to_dict()


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(MerchantIgnoreRule, rule_id)
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    db.delete(rule)
    db.commit()
    return {"deleted": True}
