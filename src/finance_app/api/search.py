"""Global search across transactions, accounts, categories and debts."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from finance_app.database import get_db
from finance_app.models import Transaction, Account, Category, Debt, Payee

router = APIRouter()


@router.get("")
@router.get("/")
def global_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=25),
    db: Session = Depends(get_db),
):
    """Search transactions, accounts, categories and debts by name/memo."""
    term = q.strip()
    if not term:
        return {"query": q, "results": []}

    like = f"%{term}%"
    results = []

    accounts = (
        db.query(Account)
        .filter(Account.is_closed == False, Account.name.ilike(like))
        .order_by(Account.name)
        .limit(limit)
        .all()
    )
    for a in accounts:
        results.append({
            "type": "account",
            "id": a.id,
            "label": a.name,
            "subtitle": a.type,
            "path": "/accounts",
        })

    categories = (
        db.query(Category)
        .options(joinedload(Category.category_group))
        .filter(Category.is_hidden == False, Category.name.ilike(like))
        .order_by(Category.name)
        .limit(limit)
        .all()
    )
    for c in categories:
        group = c.category_group.name if c.category_group else ""
        results.append({
            "type": "category",
            "id": c.id,
            "label": c.name,
            "subtitle": group,
            "path": "/budget",
        })

    debts = (
        db.query(Debt)
        .filter(Debt.is_active == True, Debt.name.ilike(like))
        .order_by(Debt.name)
        .limit(limit)
        .all()
    )
    for d in debts:
        results.append({
            "type": "debt",
            "id": d.id,
            "label": d.name,
            "subtitle": d.debt_type,
            "path": "/debts",
        })

    txs = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.payee),
            joinedload(Transaction.category),
            joinedload(Transaction.account),
        )
        .outerjoin(Payee, Transaction.payee_id == Payee.id)
        .filter(
            or_(
                Payee.name.ilike(like),
                Transaction.memo.ilike(like),
            )
        )
        .order_by(Transaction.date.desc())
        .limit(limit)
        .all()
    )
    for t in txs:
        label = t.payee.name if t.payee else (t.memo or f"Tx #{t.id}")
        results.append({
            "type": "transaction",
            "id": t.id,
            "label": label,
            "subtitle": f"{t.date.isoformat() if t.date else ''} · {t.account.name if t.account else ''}",
            "path": f"/transactions?search={term}",
        })

    return {"query": term, "results": results[: limit * 2]}
