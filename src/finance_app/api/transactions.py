"""
Transactions API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List, Optional, Literal
from pydantic import BaseModel
from decimal import Decimal
from datetime import date
import csv
import io

from finance_app.database import get_db
from finance_app.models import Currency
from finance_app.services.exchange_rate_service import convert_currency
from finance_app.services.transaction_service import (
    create_transaction, get_transactions, get_transaction_by_id,
    update_transaction, delete_transaction, create_transfer, create_adjustment,
    get_last_manual_transactions_by_account
)

router = APIRouter()


def _amounts_in_cop_and_usd(transaction, db: Session, cop_currency: Optional[Currency], usd_currency: Optional[Currency]):
    """Return transaction amount converted to COP and USD using original values/date."""
    original_amount = transaction.original_amount
    original_currency_id = transaction.original_currency_id
    transaction_date = transaction.date

    cop_amount = None
    usd_amount = None

    if not original_currency_id or original_amount is None or not transaction_date:
        return cop_amount, usd_amount

    original_currency = db.query(Currency).get(original_currency_id)
    original_currency_code = original_currency.code if original_currency else None
    if not original_currency_code:
        return cop_amount, usd_amount

    if cop_currency:
        if original_currency_id == cop_currency.id:
            cop_amount = original_amount
        else:
            cop_amount = convert_currency(
                amount=original_amount,
                from_currency=original_currency_code,
                to_currency="COP",
                db=db,
                rate_date=transaction_date
            )

    if usd_currency:
        if original_currency_id == usd_currency.id:
            usd_amount = original_amount
        else:
            usd_amount = convert_currency(
                amount=original_amount,
                from_currency=original_currency_code,
                to_currency="USD",
                db=db,
                rate_date=transaction_date
            )

    return cop_amount, usd_amount


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


class TransactionSplitPayload(BaseModel):
    category_id: int
    amount: float
    note: Optional[str] = None


class TransactionCreate(BaseModel):
    account_id: int
    date: date
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    investment_asset_id: Optional[int] = None
    memo: Optional[str] = None
    amount: float
    currency_id: int
    type: Optional[Literal['expense', 'income']] = None
    cleared: bool = False
    tag_ids: list[int] = []
    splits: Optional[list[TransactionSplitPayload]] = None
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
    investment_asset_id: Optional[int] = None
    memo: Optional[str] = None
    amount: Optional[float] = None
    currency_id: Optional[int] = None
    type: Optional[Literal['expense', 'income']] = None
    cleared: Optional[bool] = None
    tag_ids: Optional[list[int]] = None
    splits: Optional[list[TransactionSplitPayload]] = None


@router.get("/")
def list_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get list of transactions"""
    transactions = get_transactions(
        db,
        account_id=account_id,
        category_id=category_id,
        tag_id=tag_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    cop_currency = db.query(Currency).filter_by(code="COP").first()
    usd_currency = db.query(Currency).filter_by(code="USD").first()

    enriched_transactions = []
    for transaction in transactions:
        serialized = transaction.to_dict()
        cop_amount, usd_amount = _amounts_in_cop_and_usd(transaction, db, cop_currency, usd_currency)
        serialized["cop_amount"] = cop_amount
        serialized["usd_amount"] = usd_amount
        enriched_transactions.append(serialized)

    return enriched_transactions


@router.get("/export")
def export_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 0,
    db: Session = Depends(get_db)
):
    """Export transactions as CSV with optional filters."""
    transactions = get_transactions(
        db,
        account_id=account_id,
        category_id=category_id,
        tag_id=tag_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )

    output = io.StringIO()
    writer = csv.writer(output)
    cop_currency = db.query(Currency).filter_by(code="COP").first()
    usd_currency = db.query(Currency).filter_by(code="USD").first()

    writer.writerow([
        "Fecha",
        "Cuenta",
        "Beneficiario",
        "Categoría",
        "COP",
        "USD",
        "Tipo"
    ])

    for transaction in transactions:
        is_transfer = transaction.transfer_account_id is not None
        is_inflow = transaction.amount >= 0
        tipo = "Transferencia" if is_transfer else ("Ingreso" if is_inflow else "Gasto")
        cop_amount, usd_amount = _amounts_in_cop_and_usd(transaction, db, cop_currency, usd_currency)

        writer.writerow([
            transaction.date.isoformat() if transaction.date else "",
            transaction.account.name if transaction.account else "",
            transaction.payee.name if transaction.payee else "",
            transaction.category.name if transaction.category else "",
            f"{cop_amount:.2f}" if cop_amount is not None else "",
            f"{usd_amount:.2f}" if usd_amount is not None else "",
            tipo
        ])

    filename = f"transacciones_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
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
    try:
        new_transaction = create_transaction(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
def remove_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Delete a transaction"""
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
