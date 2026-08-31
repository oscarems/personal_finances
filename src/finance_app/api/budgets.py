"""
Budgets API endpoints - Multi-currency with manual rollover.
"""
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date
from typing import Optional

from finance_app.database import get_db
from finance_app.services.budget_service import (
    get_month_budget,
    assign_money_to_category,
    get_budget_overview,
    get_assigned_totals_by_currency,
    recalculate_budget_available,
    get_spent_transactions_to_date,
    get_category_budget_history,
    recalculate_month,
    initialize_month,
    audit_ready_to_assign,
)
from finance_app.services.exchange_rate_service import convert_currency
from finance_app.models import BudgetMonth, Currency, Category, Transaction, Account

router = APIRouter()


class BudgetAssignment(BaseModel):
    """Schema for assigning a budget to a category."""
    category_id: int
    amount: float
    month: date
    currency_code: str = 'COP'
    rollover_type: Optional[str] = None  # 'accumulate' o 'reset' (opcional, actualiza categoría)
    initial_amount: Optional[float] = None  # Dinero acumulado inicial (for accumulate categories)


class CoverOverspendingRequest(BaseModel):
    """Schema for covering overspending between categories."""
    source_category_id: int
    target_category_id: int
    amount: float
    currency_code: str = 'COP'
    month: date


class UpdateCoverOverspendingRequest(BaseModel):
    """Schema for editing an existing coverage movement (amount/currency/counterpart)."""
    counterpart_category_id: int
    amount: float
    currency_code: str = 'COP'


@router.get("/current")
def current_budget(currency_code: str = 'COP', db: Session = Depends(get_db)):
    """Get current month budget"""
    return get_budget_overview(db, currency_code)


@router.get("/export")
def export_budget_csv(
    year: Optional[int] = None,
    month: Optional[int] = None,
    currency_code: str = "COP",
    db: Session = Depends(get_db),
):
    """Export monthly budget as CSV (asignado / gastado / disponible)."""
    today = date.today()
    y = year or today.year
    m = month or today.month
    month_date = date(y, m, 1)
    data = get_month_budget(db, month_date, currency_code=currency_code)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Mes", "Grupo", "Categoría", "Asignado", "Actividad", "Disponible", "Moneda"])
    month_label = f"{y:04d}-{m:02d}"
    for group in data.get("groups", []):
        group_name = group.get("name", "")
        for cat in group.get("categories", []):
            writer.writerow([
                month_label,
                group_name,
                cat.get("category_name") or cat.get("name", ""),
                cat.get("assigned", 0),
                cat.get("activity", 0),
                cat.get("available", 0),
                currency_code,
            ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="presupuesto-{month_label}.csv"'},
    )


@router.get("/assigned-totals")
def assigned_totals(year: Optional[int] = None, month: Optional[int] = None, db: Session = Depends(get_db)):
    """Get total assigned by currency for a month"""
    if year and month:
        month_date = date(year, month, 1)
    else:
        today = date.today()
        month_date = date(today.year, today.month, 1)

    return {
        "month": month_date.isoformat(),
        "totals": get_assigned_totals_by_currency(db, month_date)
    }


@router.get("/spent-transactions")
def spent_transactions(
    year: Optional[int] = None,
    month: Optional[int] = None,
    currency_code: str = 'COP',
    db: Session = Depends(get_db)
):
    """Get transactions used to calculate 'Gastado este mes'."""
    if year and month:
        month_date = date(year, month, 1)
    else:
        today = date.today()
        month_date = date(today.year, today.month, 1)

    currency = db.query(Currency).filter_by(code=currency_code).first()
    if not currency:
        raise HTTPException(status_code=404, detail="Currency not found")

    return get_spent_transactions_to_date(db, month_date, currency.id)


@router.get("/month/{year}/{month}")
def get_budget(year: int, month: int, currency_code: str = 'COP', db: Session = Depends(get_db)):
    """Get budget for a specific month"""
    month_date = date(year, month, 1)
    return get_month_budget(db, month_date, currency_code)


@router.get("/category/{category_id}/history")
def category_budget_history(
    category_id: int,
    months: int = 3,
    db: Session = Depends(get_db)
):
    """Historical budget data and transactions for a category over N months."""
    return get_category_budget_history(db, category_id, months)


@router.get("/category/{category_id}/{month}")
def get_category_budgets(category_id: int, month: str, db: Session = Depends(get_db)):
    """
    Get budgets for a category in a specific month across ALL currencies.

    GET /api/budgets/category/5/2025-01

    Returns:
        [
            {"currency_code": "COP", "assigned": 800000, ...},
            {"currency_code": "USD", "assigned": 200, ...}
        ]
    """
    # Parsear mes
    year, month_num = month.split('-')
    month_date = date(int(year), int(month_num), 1)

    # Obtener presupuestos en todas las monedas
    budgets = db.query(BudgetMonth).filter_by(
        category_id=category_id,
        month=month_date
    ).all()

    # Obtener información de monedas
    currencies = {c.id: c for c in db.query(Currency).all()}

    return [
        {
            "currency_code": currencies[b.currency_id].code,
            "currency_id": b.currency_id,
            "assigned": b.assigned,
            "activity": b.activity,
            "available": b.available,
            "initial_amount": b.initial_amount or 0.0
        }
        for b in budgets
    ]


@router.post("/assign")
def assign_budget(assignment: BudgetAssignment, db: Session = Depends(get_db)):
    """
    Assign money to a category for a specific month.

    If rollover_type is provided, updates the category's rollover behavior.
    """
    currency = db.query(Currency).filter_by(code=assignment.currency_code).first()
    if not currency:
        raise HTTPException(status_code=404, detail="Currency not found")

    # Si se proporciona rollover_type, actualizar la categoría
    if assignment.rollover_type:
        category = db.get(Category, assignment.category_id)
        if category:
            category.rollover_type = assignment.rollover_type
            db.commit()

    budget = assign_money_to_category(
        db,
        assignment.category_id,
        assignment.month,
        currency.id,
        assignment.amount,
        initial_amount=assignment.initial_amount
    )

    return {"success": True, "budget": budget.to_dict()}


def _get_category_currency(db: Session, category_id: int, month_date, fallback: Currency) -> Currency:
    """Return the currency a category's budget is actually tracked in for a given month.

    Prefers the row with non-zero `assigned` (the category's "real" currency);
    falls back to any existing row for that month, then to `fallback`.
    """
    budgets = db.query(BudgetMonth).filter_by(
        category_id=category_id, month=month_date
    ).all()
    if not budgets:
        return fallback
    primary = next((b for b in budgets if (b.assigned or 0.0) != 0.0), budgets[0])
    return db.get(Currency, primary.currency_id) or fallback


def _get_budget_account_for_currency(db: Session, currency_id: int):
    return db.query(Account).filter(
        Account.is_budget == True,
        Account.is_closed == False,
        Account.currency_id == currency_id
    ).first()


def _create_cover_overspending_pair(db: Session, request: CoverOverspendingRequest) -> dict:
    """Create cover tx pair + recalculate available. Does NOT commit.

    Cover txs are virtual budget movements: they do not update account.balance
    (delete/update must stay symmetric — see is_budget_cover_adjustment).
    """
    input_currency = db.query(Currency).filter_by(code=request.currency_code).first()
    if not input_currency:
        raise HTTPException(status_code=404, detail="Currency not found")

    source_cat = db.get(Category, request.source_category_id)
    target_cat = db.get(Category, request.target_category_id)
    if not source_cat or not target_cat:
        raise HTTPException(status_code=404, detail="Category not found")

    month_date = request.month

    # Each category keeps its own native currency; the amount entered by the
    # user is expressed in the target category's currency and must be
    # converted for the source side if they differ.
    target_currency = _get_category_currency(db, request.target_category_id, month_date, input_currency)
    source_currency = _get_category_currency(db, request.source_category_id, month_date, input_currency)

    target_budget_account = _get_budget_account_for_currency(db, target_currency.id)
    if not target_budget_account:
        raise HTTPException(
            status_code=400,
            detail=f"No budget account found for currency {target_currency.code}",
        )

    source_budget_account = _get_budget_account_for_currency(db, source_currency.id)
    if not source_budget_account:
        raise HTTPException(
            status_code=400,
            detail=f"No budget account found for currency {source_currency.code}",
        )

    target_amt = abs(request.amount)
    source_amt = (
        target_amt if source_currency.code == target_currency.code
        else convert_currency(target_amt, target_currency.code, source_currency.code, db)
    )

    # Create expense transaction in source category (reduces its available)
    source_tx = Transaction(
        date=month_date,
        amount=-source_amt,
        account_id=source_budget_account.id,
        category_id=request.source_category_id,
        currency_id=source_currency.id,
        original_amount=-source_amt,
        original_currency_id=source_currency.id,
        memo=f"Cubrir exceso: {target_cat.name}",
        is_adjustment=True,
    )
    db.add(source_tx)

    # Create income transaction in target category (increases its available)
    target_tx = Transaction(
        date=month_date,
        amount=target_amt,
        account_id=target_budget_account.id,
        category_id=request.target_category_id,
        currency_id=target_currency.id,
        original_amount=target_amt,
        original_currency_id=target_currency.id,
        memo=f"Cubierto desde: {source_cat.name}",
        is_adjustment=True,
    )
    db.add(target_tx)
    db.flush()

    # Recalculate available for both categories (includes coverage net)
    source_budgets = db.query(BudgetMonth).filter_by(
        category_id=request.source_category_id,
        month=month_date,
        currency_id=source_currency.id
    ).all()
    target_budgets = db.query(BudgetMonth).filter_by(
        category_id=request.target_category_id,
        month=month_date,
        currency_id=target_currency.id
    ).all()

    for b in source_budgets + target_budgets:
        recalculate_budget_available(db, b)

    return {
        "success": True,
        "amount": request.amount,
        "currency_code": request.currency_code,
        "source_currency_code": source_currency.code,
        "source_amount": source_amt,
    }


@router.post("/cover-overspending")
def cover_overspending(request: CoverOverspendingRequest, db: Session = Depends(get_db)):
    """
    Cover overspending by moving available funds from source to target category.
    Does NOT modify 'assigned' for either category.
    Creates two internal transactions (expense in source, income in target). Each
    transaction is recorded in its own category's native currency — `amount` is
    given in the target category's currency (`currency_code`) and converted to the
    source category's currency when they differ.
    """
    result = _create_cover_overspending_pair(db, request)
    db.commit()
    return result


@router.put("/cover-overspending/{transaction_id}")
def update_cover_overspending(
    transaction_id: int,
    request: UpdateCoverOverspendingRequest,
    db: Session = Depends(get_db),
):
    """
    Edit an existing coverage movement (amount, currency, and/or counterpart
    category). Recreate happens in the same DB transaction as the delete so a
    failed recreate rolls back and preserves the original pair.
    """
    tx = db.get(Transaction, transaction_id)
    if not tx or not tx.is_adjustment or not tx.memo:
        raise HTTPException(status_code=404, detail="Movimiento de cobertura no encontrado")

    is_cubrir = tx.memo.startswith("Cubrir exceso:")
    is_cubierto = tx.memo.startswith("Cubierto desde:")
    if not (is_cubrir or is_cubierto):
        raise HTTPException(status_code=400, detail="La transacción no es un movimiento de cobertura")

    own_category = db.get(Category, tx.category_id)
    if not own_category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    complementary_prefix = "Cubierto desde:" if is_cubrir else "Cubrir exceso:"

    pair_tx = (
        db.query(Transaction)
        .filter(
            Transaction.id != tx.id,
            Transaction.date == tx.date,
            Transaction.is_adjustment.is_(True),
            Transaction.memo == f"{complementary_prefix} {own_category.name}",
        )
        .first()
    )

    month_date = tx.date

    # Delete + recreate in one transaction (no intermediate commit).
    db.delete(tx)
    if pair_tx:
        db.delete(pair_tx)
    db.flush()

    if is_cubrir:
        source_category_id = own_category.id
        target_category_id = request.counterpart_category_id
    else:
        source_category_id = request.counterpart_category_id
        target_category_id = own_category.id

    try:
        result = _create_cover_overspending_pair(
            db,
            CoverOverspendingRequest(
                source_category_id=source_category_id,
                target_category_id=target_category_id,
                amount=request.amount,
                currency_code=request.currency_code,
                month=month_date,
            ),
        )
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@router.post("/recalculate-savings")
def recalculate_savings_budgets(db: Session = Depends(get_db)):
    """
    Recalculate all budgets for savings (accumulate) categories.

    Fixes cases where initial_amount was not applied correctly due to a race
    condition. Recalculates all budgets in chronological order to ensure
    rollover works correctly.
    """
    from sqlalchemy import distinct

    # Encontrar todas las categorías de ahorro
    savings_categories = db.query(Category).filter(
        Category.rollover_type == 'accumulate'
    ).all()

    results = []

    for category in savings_categories:
        category_result = {
            "category_id": category.id,
            "category_name": category.name,
            "initial_amount": category.initial_amount,
            "currencies": []
        }

        # Obtener todas las monedas usadas para esta categoría
        budget_currencies = db.query(distinct(BudgetMonth.currency_id)).filter(
            BudgetMonth.category_id == category.id
        ).all()

        for (currency_id,) in budget_currencies:
            currency = db.get(Currency, currency_id)

            # Obtener todos los presupuestos de esta categoría en esta moneda
            budgets = db.query(BudgetMonth).filter(
                BudgetMonth.category_id == category.id,
                BudgetMonth.currency_id == currency_id
            ).order_by(BudgetMonth.month).all()

            updated_budgets = []

            # Recalcular cada presupuesto en orden cronológico
            for budget in budgets:
                old_available = budget.available

                # Determinar si hay múltiples monedas en este mes
                existing_budgets = db.query(BudgetMonth).filter_by(
                    category_id=category.id,
                    month=budget.month
                ).all()
                has_multiple_currencies = len({b.currency_id for b in existing_budgets}) > 1

                # Recalcular available
                recalculate_budget_available(
                    db,
                    budget,
                    include_all_currencies=not has_multiple_currencies
                )

                if old_available != budget.available:
                    updated_budgets.append({
                        "month": budget.month.isoformat(),
                        "old_available": old_available,
                        "new_available": budget.available,
                        "assigned": budget.assigned,
                        "activity": budget.activity
                    })

            if updated_budgets:
                category_result["currencies"].append({
                    "currency_code": currency.code,
                    "budgets_updated": len(updated_budgets),
                    "updates": updated_budgets
                })

        if category_result["currencies"]:
            results.append(category_result)

    # Hacer commit de todos los cambios
    db.commit()

    return {
        "success": True,
        "categories_processed": len(savings_categories),
        "categories_updated": len(results),
        "details": results
    }


@router.post("/recalculate/{year}/{month}")
def recalculate_budget_month(year: int, month: int, db: Session = Depends(get_db)):
    """
    Force recalculation of assigned (inherited from prior month if not overridden)
    and available for all categories in a given month.

    Useful when reviewing a future month and wanting to sync with changes made in
    prior months.
    """
    month_date = date(year, month, 1)
    result = recalculate_month(db, month_date)
    return {"success": True, **result}


@router.post("/initialize/{year}/{month}")
def initialize_budget_month(year: int, month: int, db: Session = Depends(get_db)):
    """
    Initialize budget for a target month from the previous month.

    - 'accumulate' (savings) categories: new assigned = max(0, prev_assigned + prev_activity)
    - 'reset' (spending) categories: new assigned = prev_assigned

    Only creates rows that don't already exist. Existing rows are not modified.
    """
    result = initialize_month(db, year, month)
    return {"success": True, **result}


@router.get("/audit/ready-to-assign/{year}/{month}")
def audit_ready_to_assign_endpoint(
    year: int,
    month: int,
    currency: str = "COP",
    db: Session = Depends(get_db),
):
    """
    Auditoría detallada del valor 'Listo para asignar'.

    Desglosa:
    - Cuentas presupuestadas incluidas (con saldo y conversión)
    - Cuentas excluidas (deudas)
    - Disponible por categoría
    - Categorías de ingreso omitidas
    - Resultado final y sus componentes

    Útil para diagnosticar discrepancias entre lo que muestra el dashboard
    y lo que esperaría el usuario.
    """
    currency_obj = db.query(Currency).filter_by(code=currency.upper()).first()
    if not currency_obj:
        raise HTTPException(status_code=404, detail=f"Moneda '{currency}' no encontrada")

    month_date = date(year, month, 1)
    return audit_ready_to_assign(db, month_date, currency_obj.id)
