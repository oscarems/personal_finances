"""
Recurring Transaction Service
Handles generation of transactions from recurring rules.
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from finance_app.models import RecurringTransaction, Transaction, Account, Payee, Debt, DebtPayment
from finance_app.services.debt.balance_service import refresh_mortgage_current_balance
from finance_app.services.transaction_service import build_transaction_audit_fields


def get_next_occurrence_date(recurring: RecurringTransaction, from_date: date) -> date:
    """
    Calculate the next occurrence date for a recurring transaction
    """
    if recurring.frequency == 'daily':
        return from_date + timedelta(days=recurring.interval)

    elif recurring.frequency == 'weekly':
        # Move to next interval week
        next_date = from_date + timedelta(weeks=recurring.interval)
        # Adjust to correct day of week if specified
        if recurring.day_of_week is not None:
            days_ahead = recurring.day_of_week - next_date.weekday()
            if days_ahead < 0:
                days_ahead += 7
            next_date = next_date + timedelta(days=days_ahead)
        return next_date

    elif recurring.frequency == 'monthly':
        next_date = from_date + relativedelta(months=recurring.interval)
        # Adjust to correct day of month if specified
        if recurring.day_of_month is not None:
            try:
                next_date = next_date.replace(day=recurring.day_of_month)
            except ValueError:
                # Day doesn't exist in this month (e.g., Feb 30), use last day
                next_date = next_date.replace(day=1) + relativedelta(months=1) - timedelta(days=1)
        return next_date

    elif recurring.frequency == 'yearly':
        return from_date + relativedelta(years=recurring.interval)

    return from_date


def get_next_scheduled_date(recurring: RecurringTransaction) -> Optional[date]:
    """
    Calculate the next scheduled date based on the recurrence settings.
    """
    if recurring.last_generated_date:
        next_date = get_next_occurrence_date(recurring, recurring.last_generated_date)
        if recurring.end_date and next_date > recurring.end_date:
            return None
        return next_date

    start_date = recurring.start_date

    if recurring.frequency == 'weekly' and recurring.day_of_week is not None:
        days_ahead = recurring.day_of_week - start_date.weekday()
        candidate = start_date + timedelta(days=days_ahead)
        if candidate < start_date:
            candidate += timedelta(weeks=recurring.interval)
        if recurring.end_date and candidate > recurring.end_date:
            return None
        return candidate

    if recurring.frequency == 'monthly' and recurring.day_of_month is not None:
        try:
            candidate = start_date.replace(day=recurring.day_of_month)
        except ValueError:
            candidate = start_date.replace(day=1) + relativedelta(months=1) - timedelta(days=1)

        if candidate < start_date:
            candidate = candidate + relativedelta(months=recurring.interval)
            try:
                candidate = candidate.replace(day=recurring.day_of_month)
            except ValueError:
                candidate = candidate.replace(day=1) + relativedelta(months=1) - timedelta(days=1)
        if recurring.end_date and candidate > recurring.end_date:
            return None
        return candidate

    if recurring.end_date and start_date > recurring.end_date:
        return None
    return start_date


def should_generate_transaction(recurring: RecurringTransaction, check_date: date) -> bool:
    """
    Check if a transaction should be generated for the given date
    """
    # Not active
    if not recurring.is_active:
        return False

    # Haven't started yet
    if check_date < recurring.start_date:
        return False

    # Past end date
    if recurring.end_date and check_date > recurring.end_date:
        return False

    # Already generated for this date or later
    if recurring.last_generated_date and check_date <= recurring.last_generated_date:
        return False

    # Snoozed: skip dates on or before snoozed_until
    if recurring.snoozed_until and check_date <= recurring.snoozed_until:
        return False

    return True


def get_existing_auto_transaction_date(
    db: Session,
    recurring: RecurringTransaction,
    check_date: date,
    signed_amount: float
) -> Optional[date]:
    """
    Check if an automatic transaction already exists in the calendar month.
    Returns the most recent auto transaction date in that month if found.
    """
    month_start = check_date.replace(day=1)
    month_end = month_start + relativedelta(months=1) - timedelta(days=1)

    query = db.query(Transaction.date).filter(
        Transaction.account_id == recurring.account_id,
        Transaction.date >= month_start,
        Transaction.date <= month_end,
        Transaction.amount == signed_amount,
        or_(
            Transaction.memo == "Transacción automática",
            Transaction.memo.like("Auto:%")
        )
    )

    if recurring.payee_id is None:
        query = query.filter(Transaction.payee_id.is_(None))
    else:
        query = query.filter(Transaction.payee_id == recurring.payee_id)

    if recurring.category_id is None:
        query = query.filter(Transaction.category_id.is_(None))
    else:
        query = query.filter(Transaction.category_id == recurring.category_id)

    existing = query.order_by(Transaction.date.desc()).first()
    return existing[0] if existing else None


def advance_to_next_month(recurring: RecurringTransaction, from_date: date) -> date:
    """
    Advance to the next scheduled occurrence that falls in a different month.
    """
    next_date = get_next_occurrence_date(recurring, from_date)
    while next_date.month == from_date.month and next_date.year == from_date.year:
        next_date = get_next_occurrence_date(recurring, next_date)
    return next_date


def generate_due_transactions(db: Session, up_to_date: date = None) -> dict:
    """
    Generate all due recurring transactions up to the specified date
    Returns statistics about generated transactions
    """
    if up_to_date is None:
        up_to_date = date.today()

    stats = {
        'checked': 0,
        'generated': 0,
        'skipped': 0,
        'errors': []
    }

    # Get all active recurring transactions
    recurring_txs = db.query(RecurringTransaction).filter(
        RecurringTransaction.is_active == True
    ).all()

    stats['checked'] = len(recurring_txs)

    for recurring in recurring_txs:
        try:
            # Determine the date to start checking from
            if recurring.last_generated_date:
                check_date = get_next_occurrence_date(recurring, recurring.last_generated_date)
            else:
                check_date = recurring.start_date

            # Generate all transactions up to today
            while check_date <= up_to_date:
                if not should_generate_transaction(recurring, check_date):
                    stats['skipped'] += 1
                    check_date = get_next_occurrence_date(recurring, check_date)
                    continue

                signed_amount = recurring.amount
                if recurring.transaction_type:
                    base_amount = abs(recurring.amount)
                    signed_amount = base_amount if recurring.transaction_type == 'income' else -base_amount

                existing_auto_date = get_existing_auto_transaction_date(
                    db,
                    recurring,
                    check_date,
                    signed_amount
                )
                if existing_auto_date:
                    recurring.last_generated_date = existing_auto_date
                    stats['skipped'] += 1
                    check_date = advance_to_next_month(recurring, check_date)
                    continue

                audit_base_amount, audit_base_currency_id = build_transaction_audit_fields(
                    db,
                    signed_amount,
                    recurring.currency_id,
                    check_date
                )
                # Create the transaction
                transaction = Transaction(
                    account_id=recurring.account_id,
                    date=check_date,
                    payee_id=recurring.payee_id,
                    category_id=recurring.category_id,
                    memo=f"Auto: {recurring.description}" if recurring.description else "Transacción automática",
                    amount=signed_amount,
                    currency_id=recurring.currency_id,
                    original_amount=signed_amount,
                    original_currency_id=recurring.currency_id,
                    fx_rate=None,
                    base_amount=audit_base_amount,
                    base_currency_id=audit_base_currency_id,
                    cleared=False,
                    approved=True
                )

                db.add(transaction)
                db.flush()

                # Update account balance
                account = db.get(Account, recurring.account_id)
                if account:
                    account.balance += signed_amount
                    if account.type in {'credit_card', 'credit_loan', 'mortgage'}:
                        debt = db.query(Debt).filter_by(account_id=account.id).first()
                        if debt:
                            payment_amount = abs(signed_amount)
                            if signed_amount < 0:
                                payment = DebtPayment(
                                    debt_id=debt.id,
                                    transaction_id=transaction.id,
                                    payment_date=check_date,
                                    amount=payment_amount,
                                    principal=payment_amount,
                                    interest=0.0,
                                    fees=0.0,
                                    balance_after=None,
                                    notes="Pago automático"
                                )
                                db.add(payment)
                                db.flush()
                                if debt.debt_type == "mortgage":
                                    debt.current_balance = refresh_mortgage_current_balance(
                                        db, debt, as_of_date=check_date
                                    )
                                    payment.balance_after = debt.current_balance
                                else:
                                    debt.current_balance = max(0.0, debt.current_balance - payment_amount)
                                    payment.balance_after = debt.current_balance
                                if debt.current_balance <= 0:
                                    debt.is_active = False
                            else:
                                debt.current_balance += payment_amount
                                debt.is_active = True

                # Update last generated date
                recurring.last_generated_date = check_date

                stats['generated'] += 1

                # Move to next occurrence
                check_date = get_next_occurrence_date(recurring, check_date)

                # Safety check to avoid infinite loops
                if check_date > up_to_date + relativedelta(years=10):
                    break

        except Exception as e:
            stats['errors'].append(f"Error processing recurring ID {recurring.id}: {str(e)}")
            continue

    db.commit()

    return stats


def preview_next_occurrences(recurring: RecurringTransaction, count: int = 5) -> List[date]:
    """
    Preview the next N occurrences of a recurring transaction
    """
    occurrences = []

    if recurring.last_generated_date:
        current_date = get_next_occurrence_date(recurring, recurring.last_generated_date)
    else:
        current_date = recurring.start_date

    for _ in range(count):
        if recurring.end_date and current_date > recurring.end_date:
            break

        occurrences.append(current_date)
        current_date = get_next_occurrence_date(recurring, current_date)

    return occurrences


def list_upcoming_occurrences(db: Session, days: int = 14, as_of: date | None = None) -> list[dict]:
    """Return upcoming due occurrences across all active recurring rules."""
    as_of = as_of or date.today()
    until = as_of + timedelta(days=days)
    items = []

    active = db.query(RecurringTransaction).filter(RecurringTransaction.is_active == True).all()
    for recurring in active:
        next_date = get_next_scheduled_date(recurring)
        if next_date is None:
            continue
        current = next_date
        iterations = 0
        while current <= until and iterations < 60:
            iterations += 1
            if current >= as_of:
                snoozed = bool(recurring.snoozed_until and current <= recurring.snoozed_until)
                items.append({
                    "recurring_id": recurring.id,
                    "description": recurring.description,
                    "payee_name": recurring.payee.name if recurring.payee else None,
                    "account_id": recurring.account_id,
                    "account_name": recurring.account.name if recurring.account else None,
                    "category_id": recurring.category_id,
                    "category_name": recurring.category.name if recurring.category else None,
                    "amount": recurring.amount,
                    "transaction_type": recurring.transaction_type or ("income" if recurring.amount > 0 else "expense"),
                    "currency": recurring.currency.to_dict() if recurring.currency else None,
                    "occurrence_date": current.isoformat(),
                    "snoozed": snoozed,
                    "snoozed_until": recurring.snoozed_until.isoformat() if recurring.snoozed_until else None,
                })
            current = get_next_occurrence_date(recurring, current)

    items.sort(key=lambda x: x["occurrence_date"])
    return items


def _signed_amount_for(recurring: RecurringTransaction) -> float:
    signed = recurring.amount
    if recurring.transaction_type:
        base = abs(recurring.amount)
        signed = base if recurring.transaction_type == "income" else -base
    return signed


def approve_occurrence(db: Session, recurring_id: int, occurrence_date: date | None = None) -> dict:
    """Generate a single occurrence now (or for the given date) and advance last_generated_date."""
    recurring = db.get(RecurringTransaction, recurring_id)
    if not recurring:
        raise ValueError("Recurring transaction not found")

    target = occurrence_date or get_next_scheduled_date(recurring)
    if target is None:
        raise ValueError("No hay próxima ocurrencia para aprobar")

    signed_amount = _signed_amount_for(recurring)
    existing = get_existing_auto_transaction_date(db, recurring, target, signed_amount)
    if existing:
        recurring.last_generated_date = existing
        recurring.snoozed_until = None
        db.commit()
        return {"generated": False, "skipped_existing": True, "date": existing.isoformat()}

    audit_base_amount, audit_base_currency_id = build_transaction_audit_fields(
        db, signed_amount, recurring.currency_id, target
    )
    transaction = Transaction(
        account_id=recurring.account_id,
        date=target,
        payee_id=recurring.payee_id,
        category_id=recurring.category_id,
        memo=f"Auto: {recurring.description}" if recurring.description else "Transacción automática",
        amount=signed_amount,
        currency_id=recurring.currency_id,
        original_amount=signed_amount,
        original_currency_id=recurring.currency_id,
        fx_rate=None,
        base_amount=audit_base_amount,
        base_currency_id=audit_base_currency_id,
        cleared=False,
        approved=True,
    )
    db.add(transaction)
    db.flush()

    account = db.get(Account, recurring.account_id)
    if account:
        account.balance += signed_amount

    recurring.last_generated_date = target
    recurring.snoozed_until = None
    db.commit()
    db.refresh(transaction)
    return {"generated": True, "transaction_id": transaction.id, "date": target.isoformat()}


def skip_occurrence(db: Session, recurring_id: int, occurrence_date: date | None = None) -> dict:
    """Advance past an occurrence without creating a transaction."""
    recurring = db.get(RecurringTransaction, recurring_id)
    if not recurring:
        raise ValueError("Recurring transaction not found")

    target = occurrence_date or get_next_scheduled_date(recurring)
    if target is None:
        raise ValueError("No hay próxima ocurrencia para saltar")

    recurring.last_generated_date = target
    recurring.snoozed_until = None
    db.commit()
    next_date = get_next_scheduled_date(recurring)
    return {
        "skipped": True,
        "date": target.isoformat(),
        "next_occurrence_date": next_date.isoformat() if next_date else None,
    }


def snooze_occurrence(db: Session, recurring_id: int, days: int = 7) -> dict:
    """Delay auto-generation until as_of + days."""
    if days < 1:
        raise ValueError("days must be >= 1")
    recurring = db.get(RecurringTransaction, recurring_id)
    if not recurring:
        raise ValueError("Recurring transaction not found")

    until = date.today() + timedelta(days=days)
    recurring.snoozed_until = until
    db.commit()
    return {"snoozed": True, "snoozed_until": until.isoformat()}
