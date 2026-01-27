"""
API endpoints for administrative operations
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from backend.database import (
    get_db,
    list_databases,
    normalize_db_name,
    is_valid_db_name,
    database_exists,
    delete_database,
    duplicate_database,
    rename_database,
    ensure_database_initialized,
    default_database_name,
    PRIMARY_DB_ALIAS,
    DEMO_DB_ALIAS
)
from backend.models import (
    Transaction, Category, CategoryGroup, BudgetMonth,
    RecurringTransaction, Account, Payee, ExchangeRate,
    Debt, DebtPayment
)
from sqlalchemy import text
from pydantic import BaseModel
from typing import Literal
from config import DEFAULT_DB_MODE

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


class DbModeRequest(BaseModel):
    """Request to switch database mode"""
    mode: Literal["primary", "demo"]


class DatabaseSelectionRequest(BaseModel):
    """Request to switch active database"""
    name: str


class DatabaseCreateRequest(BaseModel):
    """Request to create a new database"""
    name: str


class DatabaseDeleteRequest(BaseModel):
    """Request to delete a database"""
    name: str


class DatabaseDuplicateRequest(BaseModel):
    """Request to duplicate a database"""
    source: str
    target: str


class DatabaseRenameRequest(BaseModel):
    """Request to rename a database"""
    name: str
    new_name: str


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

        # 5. Delete debt payments and debts
        deleted_counts['debt_payments'] = db.query(DebtPayment).delete()
        db.commit()

        deleted_counts['debts'] = db.query(Debt).delete()
        db.commit()

        # 6. Reset account balances or delete them
        if options.keep_accounts:
            accounts = db.query(Account).all()
            for account in accounts:
                account.balance = 0
            db.commit()
            deleted_counts['accounts_reset'] = len(accounts)
        else:
            deleted_counts['accounts'] = db.query(Account).delete()
            db.commit()

        # 7. Delete categories and groups if requested
        if not options.keep_categories:
            deleted_counts['categories'] = db.query(Category).delete()
            deleted_counts['category_groups'] = db.query(CategoryGroup).delete()
            db.commit()

        # 8. Clean old exchange rates (keep only last 30 days)
        db.execute(text("""
            DELETE FROM exchange_rates
            WHERE date < date('now', '-30 days')
        """))
        db.commit()

        # 9. Reset ID sequences
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='transactions'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='recurring_transactions'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='budget_months'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='payees'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='debts'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='debt_payments'"))
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
            'debts': db.query(Debt).count(),
            'debt_payments': db.query(DebtPayment).count(),
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


@router.get("/db-mode")
def get_db_mode(request: Request):
    """Return active database mode based on cookie"""
    mode = request.cookies.get("db_mode", DEFAULT_DB_MODE)
    return {"mode": mode}


@router.post("/db-mode")
def set_db_mode(payload: DbModeRequest, response: Response):
    """Set active database mode in a cookie"""
    response.set_cookie(
        key="db_mode",
        value=payload.mode,
        httponly=False,
        samesite="lax"
    )
    return {"mode": payload.mode}


@router.get("/databases")
def get_databases(request: Request):
    """Return available databases and current selection"""
    current = request.cookies.get("db_name")
    if not current:
        current = request.cookies.get("db_mode", DEFAULT_DB_MODE)
    current = normalize_db_name(current)
    if not database_exists(current):
        current = default_database_name()
    ensure_database_initialized(current)
    return {
        "current": current,
        "databases": list_databases()
    }


@router.post("/databases/select")
def select_database(payload: DatabaseSelectionRequest, response: Response):
    """Select an existing database"""
    name = normalize_db_name(payload.name)
    if name not in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS} and not is_valid_db_name(name):
        raise HTTPException(status_code=400, detail="Nombre de base inválido.")
    if not database_exists(name) and name in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        ensure_database_initialized(name)
    elif not database_exists(name):
        raise HTTPException(status_code=404, detail="La base seleccionada no existe.")
    ensure_database_initialized(name)
    response.set_cookie(
        key="db_name",
        value=name,
        httponly=False,
        samesite="lax"
    )
    response.delete_cookie("db_mode")
    return {"name": name}


@router.post("/databases/create")
def create_database(payload: DatabaseCreateRequest, response: Response):
    """Create a new database and select it"""
    name = normalize_db_name(payload.name)
    if name in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        ensure_database_initialized(name)
    elif not is_valid_db_name(name):
        raise HTTPException(status_code=400, detail="Nombre de base inválido.")
    elif database_exists(name):
        raise HTTPException(status_code=409, detail="La base ya existe.")
    ensure_database_initialized(name)
    response.set_cookie(
        key="db_name",
        value=name,
        httponly=False,
        samesite="lax"
    )
    response.delete_cookie("db_mode")
    return {"name": name}


@router.post("/databases/delete")
def delete_database_api(payload: DatabaseDeleteRequest, request: Request, response: Response):
    """Delete a database"""
    name = normalize_db_name(payload.name)
    if name in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        raise HTTPException(status_code=400, detail="No se puede eliminar la base principal o demo.")
    if not is_valid_db_name(name):
        raise HTTPException(status_code=400, detail="Nombre de base inválido.")
    if not database_exists(name):
        raise HTTPException(status_code=404, detail="La base seleccionada no existe.")
    try:
        delete_database(name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    current = request.cookies.get("db_name")
    if current and normalize_db_name(current) == name:
        fallback = default_database_name()
        response.set_cookie(key="db_name", value=fallback, httponly=False, samesite="lax")
    return {"name": name, "deleted": True}


@router.post("/databases/duplicate")
def duplicate_database_api(payload: DatabaseDuplicateRequest):
    """Duplicate an existing database"""
    source = normalize_db_name(payload.source)
    target = normalize_db_name(payload.target)
    if not database_exists(source):
        raise HTTPException(status_code=404, detail="La base de origen no existe.")
    if target in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        raise HTTPException(status_code=400, detail="No se puede sobrescribir la base principal o demo.")
    if not is_valid_db_name(target):
        raise HTTPException(status_code=400, detail="Nombre de base destino inválido.")
    if database_exists(target):
        raise HTTPException(status_code=409, detail="La base destino ya existe.")
    try:
        duplicate_database(source, target)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"source": source, "target": target}


@router.post("/databases/rename")
def rename_database_api(payload: DatabaseRenameRequest, request: Request, response: Response):
    """Rename an existing database"""
    name = normalize_db_name(payload.name)
    new_name = normalize_db_name(payload.new_name)
    if name in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        raise HTTPException(status_code=400, detail="No se puede renombrar la base principal o demo.")
    if not is_valid_db_name(name) or not is_valid_db_name(new_name):
        raise HTTPException(status_code=400, detail="Nombre de base inválido.")
    if not database_exists(name):
        raise HTTPException(status_code=404, detail="La base de origen no existe.")
    if database_exists(new_name):
        raise HTTPException(status_code=409, detail="La base destino ya existe.")
    try:
        rename_database(name, new_name)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    current = request.cookies.get("db_name")
    if current and normalize_db_name(current) == name:
        response.set_cookie(key="db_name", value=new_name, httponly=False, samesite="lax")
    return {"name": name, "renamed_to": new_name}
