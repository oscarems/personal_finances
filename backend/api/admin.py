"""
API endpoints for administrative operations
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import (
    Transaction, Category, CategoryGroup, BudgetMonth,
    RecurringTransaction, Account, Payee, ExchangeRate
)
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class ResetOptions(BaseModel):
    """Options for database reset"""
    keep_accounts: bool = True
    keep_categories: bool = True
    confirm: bool = False


class ResetResponse(BaseModel):
    """Response from reset operation"""
    success: bool
    message: str
    deleted: dict


@router.post("/reset", response_model=ResetResponse)
def reset_database(options: ResetOptions, db: Session = Depends(get_db)):
    """
    Reset database by deleting transactions, budgets, and optionally accounts and categories

    Args:
        options: Reset options (keep_accounts, keep_categories, confirm)
        db: Database session

    Returns:
        ResetResponse with operation results
    """
    if not options.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must confirm reset operation by setting 'confirm: true'"
        )

    try:
        deleted_counts = {}

        # 1. Delete all transactions
        deleted_counts['transactions'] = db.query(Transaction).delete()
        db.commit()

        # 2. Delete all recurring transactions
        deleted_counts['recurring_transactions'] = db.query(RecurringTransaction).delete()
        db.commit()

        # 3. Delete all budgets
        deleted_counts['budgets'] = db.query(BudgetMonth).delete()
        db.commit()

        # 4. Delete payees
        deleted_counts['payees'] = db.query(Payee).delete()
        db.commit()

        # 5. Reset account balances or delete them
        if options.keep_accounts:
            accounts = db.query(Account).all()
            for account in accounts:
                account.balance = 0
            db.commit()
            deleted_counts['accounts_reset'] = len(accounts)
        else:
            deleted_counts['accounts'] = db.query(Account).delete()
            db.commit()

        # 6. Delete categories and groups if requested
        if not options.keep_categories:
            deleted_counts['categories'] = db.query(Category).delete()
            deleted_counts['category_groups'] = db.query(CategoryGroup).delete()
            db.commit()

        # 7. Clean old exchange rates (keep only last 30 days)
        db.execute(text("""
            DELETE FROM exchange_rates
            WHERE date < date('now', '-30 days')
        """))
        db.commit()

        # 8. Reset ID sequences
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='transactions'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='recurring_transactions'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='budget_months'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='payees'"))
        if not options.keep_accounts:
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='accounts'"))
        if not options.keep_categories:
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='categories'"))
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='category_groups'"))
        db.commit()

        message = "Database reset successfully"
        if options.keep_accounts and options.keep_categories:
            message += " (accounts and categories kept)"
        elif options.keep_accounts:
            message += " (accounts kept)"
        elif options.keep_categories:
            message += " (categories kept)"

        return ResetResponse(
            success=True,
            message=message,
            deleted=deleted_counts
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error resetting database: {str(e)}")


@router.get("/stats")
def get_database_stats(db: Session = Depends(get_db)):
    """
    Get database statistics

    Returns:
        Dict with counts of all entities
    """
    try:
        stats = {
            'transactions': db.query(Transaction).count(),
            'recurring_transactions': db.query(RecurringTransaction).count(),
            'accounts': db.query(Account).count(),
            'categories': db.query(Category).count(),
            'category_groups': db.query(CategoryGroup).count(),
            'budgets': db.query(BudgetMonth).count(),
            'payees': db.query(Payee).count(),
            'exchange_rates': db.query(ExchangeRate).count(),
        }

        # Calculate total balance across all accounts
        accounts = db.query(Account).all()
        total_balance = {
            'COP': sum(acc.balance for acc in accounts if acc.currency_code == 'COP'),
            'USD': sum(acc.balance for acc in accounts if acc.currency_code == 'USD')
        }

        return {
            'counts': stats,
            'total_balance': total_balance
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")
