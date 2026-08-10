"""
Transactions API endpoints
"""
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Literal
from pydantic import BaseModel
from decimal import Decimal
from datetime import date

from finance_app.database import get_db
from finance_app.models import Currency, Category, Account
from finance_app.models.transaction import Transaction
from finance_app.models.merchant_rule import MerchantRule
from finance_app.models.budget import BudgetMonth
from finance_app.services.transaction_service import (
    create_transaction, get_transactions, get_transaction_by_id,
    update_transaction, delete_transaction, create_transfer, create_adjustment,
    get_last_manual_transactions_by_account, amounts_in_cop_and_usd,
    is_budget_cover_adjustment, _reverse_debt_impact, _apply_debt_impact,
    _resolve_target_debt,
)
from finance_app.services.budget_service import (
    get_or_create_budget_month,
    recalculate_budget_available,
)
from finance_app.services.merchant_rule_engine import find_matching_rule

router = APIRouter()


# Pydantic schemas
class MortgageAllocation(BaseModel):
    loan_id: int
    payment_date: Optional[date] = None
    mode: Literal["manual", "auto"] = "auto"
    interest_paid: Optional[Decimal] = None
    principal_paid: Optional[Decimal] = None
    fees_paid: Optional[Decimal] = None
    escrow_paid: Optional[Decimal] = None
    extra_principal_paid: Optional[Decimal] = None
    period: Optional[str] = None
    notes: Optional[str] = None


class TransactionCreate(BaseModel):
    account_id: int
    date: date
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    debt_id: Optional[int] = None
    investment_asset_id: Optional[int] = None
    memo: Optional[str] = None
    amount: float
    currency_id: int
    type: Optional[Literal['expense', 'income']] = None
    cleared: bool = False
    mortgage_allocation: Optional[MortgageAllocation] = None


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    date: date
    amount: float
    from_currency_id: int
    to_currency_id: int
    memo: Optional[str] = None
    cleared: bool = False


class AdjustmentCreate(BaseModel):
    account_id: int
    date: date
    actual_balance: float  # Real balance from bank
    memo: Optional[str] = None


class TransactionUpdate(BaseModel):
    account_id: Optional[int] = None
    date: Optional[str] = None
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    debt_id: Optional[int] = None
    investment_asset_id: Optional[int] = None
    memo: Optional[str] = None
    amount: Optional[float] = None
    currency_id: Optional[int] = None
    type: Optional[Literal['expense', 'income']] = None
    cleared: Optional[bool] = None


class BulkUpdateBody(BaseModel):
    ids: List[int]
    category_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    notes: Optional[str] = None


class BulkDeleteBody(BaseModel):
    ids: List[int]


@router.patch("/bulk")
def bulk_update_transactions(body: BulkUpdateBody, db: Session = Depends(get_db)):
    """Bulk update category, tags, and/or notes on multiple transactions."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="No transaction IDs provided.")
    updated = 0
    # (category_id, month_first_day, currency_id) needing budget recalculation
    budgets_to_refresh: set[tuple[int, date, int]] = set()

    def _track_budget(tx: Transaction, category_id: int | None) -> None:
        if category_id is None or not tx.date or not tx.currency_id:
            return
        month_date = date(tx.date.year, tx.date.month, 1)
        budgets_to_refresh.add((category_id, month_date, tx.currency_id))

    for tx in db.query(Transaction).filter(Transaction.id.in_(body.ids)).all():
        if body.category_id is not None:
            new_category_id = body.category_id if body.category_id != 0 else None
            old_category_id = tx.category_id
            if new_category_id != old_category_id:
                account = db.get(Account, tx.account_id)
                old_debt = (
                    _resolve_target_debt(db, tx, account)
                    if account and not is_budget_cover_adjustment(tx)
                    else None
                )
                _track_budget(tx, old_category_id)
                tx.category_id = new_category_id
                new_debt = (
                    _resolve_target_debt(db, tx, account)
                    if account and not is_budget_cover_adjustment(tx)
                    else None
                )
                old_debt_id = old_debt.id if old_debt else None
                new_debt_id = new_debt.id if new_debt else None
                # Only reverse/apply when category reassignment changes debt linkage
                if old_debt_id != new_debt_id and account and not is_budget_cover_adjustment(tx):
                    if old_debt_id is not None:
                        tx.category_id = old_category_id
                        _reverse_debt_impact(db, tx, account)
                        tx.category_id = new_category_id
                    if new_debt_id is not None:
                        _apply_debt_impact(db, tx, account)
                _track_budget(tx, new_category_id)
        if body.notes is not None:
            tx.memo = body.notes or None
        if body.tag_ids is not None:
            from finance_app.models.tag import Tag, TransactionTag
            db.query(TransactionTag).filter_by(transaction_id=tx.id).delete()
            for tag_id in body.tag_ids:
                tag = db.query(Tag).filter_by(id=tag_id).first()
                if tag:
                    db.add(TransactionTag(transaction_id=tx.id, tag_id=tag_id))
        updated += 1

    db.flush()
    for category_id, month_date, currency_id in budgets_to_refresh:
        budget = get_or_create_budget_month(db, category_id, month_date, currency_id)
        existing = db.query(BudgetMonth).filter_by(
            category_id=category_id,
            month=month_date,
        ).all()
        has_multi = len({b.currency_id for b in existing}) > 1
        recalculate_budget_available(db, budget, include_all_currencies=not has_multi)

    db.commit()
    return {"success": True, "updated": updated}


@router.delete("/bulk")
def bulk_delete_transactions(body: BulkDeleteBody, db: Session = Depends(get_db)):
    """Bulk delete multiple transactions by ID."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="No transaction IDs provided.")
    deleted = 0
    errors = []
    for tx in db.query(Transaction).filter(Transaction.id.in_(body.ids)).all():
        reason = tx.delete_block_reason() if hasattr(tx, 'delete_block_reason') else None
        if reason:
            errors.append({"id": tx.id, "reason": reason})
            continue
        try:
            success = delete_transaction(db, tx.id)
            if success:
                deleted += 1
        except (ValueError, Exception) as exc:
            errors.append({"id": tx.id, "reason": str(exc)})
    db.commit()
    return {"success": True, "deleted": deleted, "errors": errors}


@router.get("/")
def list_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    search: Optional[str] = None,
    transaction_type: Optional[str] = None,
    uncategorized: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get list of transactions"""
    transactions = get_transactions(
        db,
        account_id=account_id,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
        transaction_type=transaction_type,
        uncategorized=uncategorized,
        limit=limit
    )
    cop_currency = db.query(Currency).filter_by(code="COP").first()
    usd_currency = db.query(Currency).filter_by(code="USD").first()

    enriched_transactions = []
    for transaction in transactions:
        serialized = transaction.to_dict()
        cop_amount, usd_amount = amounts_in_cop_and_usd(transaction, db, cop_currency, usd_currency)
        serialized["cop_amount"] = cop_amount
        serialized["usd_amount"] = usd_amount
        enriched_transactions.append(serialized)

    return enriched_transactions


@router.get("/export")
def export_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    search: Optional[str] = None,
    transaction_type: Optional[str] = None,
    limit: int = 0,  # 0 = unlimited
    db: Session = Depends(get_db)
):
    """Export transactions as a CSV file with dual-currency columns."""
    transactions = get_transactions(
        db,
        account_id=account_id,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
        transaction_type=transaction_type,
        limit=limit if limit > 0 else None
    )
    cop_currency = db.query(Currency).filter_by(code="COP").first()
    usd_currency = db.query(Currency).filter_by(code="USD").first()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Fecha", "Beneficiario", "Cuenta", "Categoría", "Memo",
        "Monto (moneda original)", "Moneda", "Monto COP", "Monto USD"
    ])

    for transaction in transactions:
        serialized = transaction.to_dict()
        cop_amount, usd_amount = amounts_in_cop_and_usd(transaction, db, cop_currency, usd_currency)
        currency_code = serialized.get("currency", {}).get("code", "") if isinstance(serialized.get("currency"), dict) else ""
        writer.writerow([
            serialized.get("date", ""),
            serialized.get("payee_name", ""),
            serialized.get("account_name", ""),
            serialized.get("category_name", ""),
            serialized.get("memo", ""),
            serialized.get("amount", ""),
            currency_code,
            round(cop_amount, 2) if cop_amount is not None else "",
            round(usd_amount, 2) if usd_amount is not None else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=\"transacciones.csv\""}
    )


@router.get("/last-manual")
def last_manual_transactions(db: Session = Depends(get_db)):
    """Get last manual transaction creation date by account."""
    return get_last_manual_transactions_by_account(db)


@router.get("/{transaction_id}")
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Get single transaction"""
    transaction = get_transaction_by_id(db, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction.to_dict()


@router.post("/")
def create_new_transaction(transaction: TransactionCreate, db: Session = Depends(get_db)):
    """Create a new transaction"""
    data = transaction.dict()

    # Si el usuario no especificó categoría, intenta sugerirla automáticamente
    # con las reglas de comercio configuradas (no sobreescribe una elección explícita).
    if not data.get("category_id"):
        rules = db.query(MerchantRule).order_by(MerchantRule.id).all()
        matched = find_matching_rule(rules, data.get("payee_name"), data.get("memo"))
        if matched:
            data["category_id"] = matched.category_id

    try:
        new_transaction = create_transaction(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # create_transaction commits; refresh so serialization sees DB state.
    db.refresh(new_transaction)
    return new_transaction.to_dict()


@router.put("/{transaction_id}")
def update_existing_transaction(
    transaction_id: int,
    transaction: TransactionUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing transaction"""
    data = transaction.dict(exclude_unset=True)
    if "date" in data:
        if data["date"] is None:
            raise HTTPException(status_code=400, detail="Date cannot be empty.")
        try:
            data["date"] = date.fromisoformat(data["date"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.") from exc
    try:
        updated_transaction = update_transaction(db, transaction_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated_transaction.to_dict()


@router.delete("/{transaction_id}")
def remove_transaction(
    transaction_id: int,
    delete_pair: bool = False,
    db: Session = Depends(get_db),
):
    """Delete a transaction. If delete_pair=true and the transaction is an
    adjustment pair member (Cubrir exceso / Cubierto desde), delete both."""
    tx = db.query(Transaction).filter_by(id=transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if delete_pair and tx.is_adjustment and tx.memo:
        memo = tx.memo
        is_cubrir = memo.startswith("Cubrir exceso:")
        is_cubierto = memo.startswith("Cubierto desde:")

        if is_cubrir or is_cubierto:
            # The pair may live in a different currency/account than `tx` when the
            # source and target categories use different currencies, so match by
            # date + complementary memo naming the categories on both sides
            # (not account_id or negated amount, which no longer hold across
            # currencies).
            own_category = db.get(Category, tx.category_id) if tx.category_id else None
            own_prefix = "Cubrir exceso:" if is_cubrir else "Cubierto desde:"
            counterpart_name = memo[len(own_prefix):].strip()
            complementary_prefix = "Cubierto desde:" if is_cubrir else "Cubrir exceso:"

            pair_tx = None
            if own_category:
                candidates = (
                    db.query(Transaction)
                    .filter(
                        Transaction.id != tx.id,
                        Transaction.date == tx.date,
                        Transaction.is_adjustment.is_(True),
                        Transaction.memo == f"{complementary_prefix} {own_category.name}",
                    )
                    .all()
                )
                for c in candidates:
                    c_cat = db.get(Category, c.category_id) if c.category_id else None
                    if c_cat and c_cat.name == counterpart_name:
                        pair_tx = c
                        break
            if pair_tx:
                deleted_ids = [tx.id, pair_tx.id]
                db.delete(tx)
                db.delete(pair_tx)
                db.commit()
                return {"success": True, "deleted_ids": deleted_ids}

    # Default single delete
    try:
        success = delete_transaction(db, transaction_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True}


@router.post("/transfer")
def create_account_transfer(transfer: TransferCreate, db: Session = Depends(get_db)):
    """
    Create a transfer between two accounts.
    This creates two linked transactions (outflow from source, inflow to destination).
    Supports transfers between different currencies.
    """
    if transfer.from_account_id == transfer.to_account_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account")

    if transfer.amount <= 0:
        raise HTTPException(status_code=400, detail="Transfer amount must be positive")

    transactions = create_transfer(db, transfer.dict())
    return {
        "success": True,
        "from_transaction": transactions[0].to_dict(),
        "to_transaction": transactions[1].to_dict()
    }


@router.post("/adjustment")
def create_balance_adjustment(adjustment: AdjustmentCreate, db: Session = Depends(get_db)):
    """
    Create a balance adjustment transaction to reconcile app balance with real bank balance.

    Use this when your bank account balance differs from the balance shown in the app.
    This will create an adjustment transaction that brings the app balance in sync with
    your real bank balance.

    Example:
    - App shows: 1,000,000
    - Bank shows: 1,050,000
    - This creates a +50,000 adjustment transaction
    """
    try:
        adjustment_transaction = create_adjustment(db, adjustment.dict())
        return {
            "success": True,
            "adjustment": adjustment_transaction.to_dict(),
            "message": f"Balance adjusted by {adjustment_transaction.amount:+.2f}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
