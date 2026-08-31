"""
Transaction service for CRUD operations.
"""
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, joinedload
from typing import Optional, Literal
from uuid import uuid4
from finance_app.models import (
    Transaction, Account, Category, Payee, Currency, Debt, DebtPayment,
    TransactionSplit
)
from finance_app.services.debt.balance_service import refresh_mortgage_current_balance
from finance_app.services.debt.helpers import (
    effective_monthly_interest_rate,
    payment_principal_amount,
)
from finance_app.services.exchange_rate_service import convert_currency, get_rate_for_date
from finance_app.services.transaction_allocation_service import (
    get_category_allocations,
    validate_splits_sum,
    validate_splits_categories_exist,
)

# Shared import_id prefix linking both legs of a transfer (no schema migration).
TRANSFER_PAIR_IMPORT_PREFIX = "transfer_pair:"

# Fields that can change DebtPayment / debt balance when a transaction is patched.
_DEBT_TOUCH_KEYS = frozenset({
    "amount",
    "account_id",
    "date",
    "debt_id",
    "category_id",
    "currency_id",
    "original_amount",
    "original_currency_id",
})


def transaction_affects_balance(account: Account, transaction_date: date) -> bool:
    """Check whether a transaction should update the account balance.

    Transactions dated before the account's creation date are ignored.
    """
    if not account or not transaction_date:
        return True
    if not account.created_at:
        return True
    return transaction_date >= account.created_at.date()


def is_budget_cover_adjustment(transaction: Transaction) -> bool:
    """True for category-to-category 'Cubrir exceso' / 'Cubierto desde' pairs.

    These are virtual budget movements: they must change category available
    but must NOT touch the denormalized account.balance (create already skips it).
    """
    if not transaction or not transaction.is_adjustment:
        return False
    memo = (transaction.memo or "").strip()
    return memo.startswith("Cubrir exceso:") or memo.startswith("Cubierto desde:")


CC_PAYMENT_MOVE_SOURCE = "cc_payment_move"


def _apply_cc_payment_budget_move(db: Session, transaction: Transaction, account: Account | None) -> None:
    """YNAB-style: after a CC purchase, credit the debt payment category.

    Spending category already lost available via activity. This only adds
    available to the linked Pago TC category so the future card payment is funded.
    """
    if not account or account.type != "credit_card":
        return
    if not transaction or (transaction.amount or 0) >= 0:
        return
    if transaction.transfer_account_id or transaction.is_adjustment:
        return

    debt = db.query(Debt).filter_by(account_id=account.id).first()
    if not debt or not debt.category_id:
        return

    # Don't move when the spend itself is already on the payment category
    spending_category_id = transaction.category_id
    if transaction.splits:
        # Use first split category for labeling; still move full amount once
        spending_category_id = transaction.splits[0].category_id
    if not spending_category_id or spending_category_id == debt.category_id:
        return

    # Idempotent: remove previous move for this transaction if re-applying
    _reverse_cc_payment_budget_move(db, transaction)

    spending_cat = db.get(Category, spending_category_id)
    payment_cat = db.get(Category, debt.category_id)
    if not spending_cat or not payment_cat:
        return

    amount = abs(float(transaction.amount or 0))
    if amount <= 0:
        return

    # Prefer a budget account in the same currency as the transaction
    budget_account = db.query(Account).filter(
        Account.is_budget == True,
        Account.is_closed == False,
        Account.currency_id == transaction.currency_id,
        Account.type.notin_(["credit_card", "credit_loan", "mortgage"]),
    ).first()
    if not budget_account:
        budget_account = db.query(Account).filter(
            Account.is_budget == True,
            Account.is_closed == False,
        ).first()
    if not budget_account:
        return

    move_tx = Transaction(
        date=transaction.date,
        amount=amount,
        account_id=budget_account.id,
        category_id=debt.category_id,
        currency_id=transaction.currency_id,
        original_amount=amount,
        original_currency_id=transaction.currency_id,
        memo=f"Cubierto desde: Cargo TC — {spending_cat.name}",
        is_adjustment=True,
        source=CC_PAYMENT_MOVE_SOURCE,
        source_id=str(transaction.id),
        cleared=True,
        approved=True,
    )
    db.add(move_tx)
    db.flush()

    month_date = date(transaction.date.year, transaction.date.month, 1)
    from finance_app.services.budget_service import get_or_create_budget_month, recalculate_budget_available
    budget = get_or_create_budget_month(db, debt.category_id, month_date, transaction.currency_id)
    recalculate_budget_available(db, budget)


def _reverse_cc_payment_budget_move(db: Session, transaction: Transaction) -> None:
    """Delete the Pago TC coverage adjustment linked to a CC spend."""
    if not transaction or not transaction.id:
        return
    moves = db.query(Transaction).filter(
        Transaction.source == CC_PAYMENT_MOVE_SOURCE,
        Transaction.source_id == str(transaction.id),
    ).all()
    if not moves:
        return

    from finance_app.services.budget_service import get_or_create_budget_month, recalculate_budget_available

    cats_months = set()
    for move in moves:
        if move.category_id and move.date:
            cats_months.add((move.category_id, date(move.date.year, move.date.month, 1), move.currency_id))
        db.delete(move)
    db.flush()
    for cat_id, month_date, currency_id in cats_months:
        budget = get_or_create_budget_month(db, cat_id, month_date, currency_id)
        recalculate_budget_available(db, budget)


CC_PAYMENT_MOVE_SOURCE = "cc_payment_move"


def _apply_cc_payment_budget_move(db: Session, transaction: Transaction, account: Account | None) -> None:
    """YNAB-style: when spending on a credit card, credit the linked Pago TC category.

    Spending category already loses available via activity. This only adds available
    to the debt payment category so the card can be paid later from budget.
    """
    if not account or account.type != "credit_card":
        return
    if not transaction or (transaction.amount or 0) >= 0:
        return
    if transaction.transfer_account_id or transaction.is_adjustment:
        return

    debt = db.query(Debt).filter_by(account_id=account.id, is_active=True).first()
    if not debt or not debt.category_id:
        return

    # Resolve spending category: header or first split
    spending_cat_id = transaction.category_id
    spending_cat_name = transaction.category.name if transaction.category else None
    amount = abs(float(transaction.amount or 0))
    if transaction.splits:
        amount = sum(abs(float(s.amount or 0)) for s in transaction.splits)
        # Prefer first split category for labeling; still move full total to Pago TC
        first = transaction.splits[0]
        spending_cat_id = first.category_id
        spending_cat_name = first.category.name if first.category else spending_cat_name

    if not spending_cat_id or spending_cat_id == debt.category_id:
        return
    if amount <= 0:
        return

    # Find a budget account in the transaction currency for the virtual adjustment
    budget_account = db.query(Account).filter(
        Account.is_budget == True,
        Account.is_closed == False,
        Account.currency_id == transaction.currency_id,
    ).first()
    if not budget_account:
        budget_account = db.query(Account).filter(
            Account.is_budget == True,
            Account.is_closed == False,
        ).first()
    if not budget_account:
        return

    cat_label = spending_cat_name or f"categoría {spending_cat_id}"
    move = Transaction(
        account_id=budget_account.id,
        date=transaction.date,
        category_id=debt.category_id,
        memo=f"Cubierto desde: Cargo TC — {cat_label}",
        amount=amount,
        currency_id=transaction.currency_id,
        original_amount=amount,
        original_currency_id=transaction.currency_id,
        cleared=True,
        approved=True,
        is_adjustment=True,
        source=CC_PAYMENT_MOVE_SOURCE,
        source_id=str(transaction.id),
    )
    db.add(move)
    db.flush()


def _reverse_cc_payment_budget_move(db: Session, transaction_id: int) -> None:
    """Remove virtual Pago TC credits linked to a CC spend."""
    moves = (
        db.query(Transaction)
        .filter(
            Transaction.source == CC_PAYMENT_MOVE_SOURCE,
            Transaction.source_id == str(transaction_id),
        )
        .all()
    )
    for move in moves:
        db.delete(move)


def _assign_transfer_pair_link(from_tx: Transaction, to_tx: Transaction) -> str:
    """Stamp both transfer legs with the same import_id pair key."""
    pair_id = f"{TRANSFER_PAIR_IMPORT_PREFIX}{uuid4().hex}"
    from_tx.import_id = pair_id
    to_tx.import_id = pair_id
    return pair_id


def find_linked_transfer(db: Session, transaction: Transaction) -> Transaction | None:
    """Locate the counterpart of a transfer transaction.

    Prefer the stable ``import_id`` pair stamped by ``create_transfer``. Fall back
    to accounts+date plus ``abs(amount)`` (and ``base_amount`` for FX) so two same-
    day transfers between the same accounts are not confused.
    """
    if not transaction or not transaction.transfer_account_id:
        return None

    if transaction.import_id and str(transaction.import_id).startswith(TRANSFER_PAIR_IMPORT_PREFIX):
        linked = (
            db.query(Transaction)
            .filter(
                Transaction.id != transaction.id,
                Transaction.import_id == transaction.import_id,
                Transaction.transfer_account_id.isnot(None),
            )
            .first()
        )
        if linked:
            return linked

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.id != transaction.id,
            Transaction.account_id == transaction.transfer_account_id,
            Transaction.transfer_account_id == transaction.account_id,
            Transaction.date == transaction.date,
        )
        .all()
    )
    if not candidates:
        return None

    abs_amt = abs(float(transaction.amount or 0))
    opposite = [c for c in candidates if (float(c.amount or 0) * float(transaction.amount or 0)) < 0]
    pool = opposite or candidates

    same_currency = [
        c for c in pool
        if c.currency_id == transaction.currency_id
        and abs(float(c.amount or 0)) == abs_amt
    ]
    if len(same_currency) == 1:
        return same_currency[0]
    if len(same_currency) > 1:
        return same_currency[0]

    if transaction.base_amount is not None:
        base_abs = abs(float(transaction.base_amount))
        base_matches = [
            c for c in pool
            if c.base_amount is not None
            and abs(abs(float(c.base_amount)) - base_abs) < 0.01
        ]
        if len(base_matches) == 1:
            return base_matches[0]
        if len(base_matches) > 1:
            return base_matches[0]

    abs_matches = [c for c in pool if abs(float(c.amount or 0)) == abs_amt]
    if len(abs_matches) == 1:
        return abs_matches[0]

    return pool[0]


def _update_touches_debt(
    transaction: Transaction,
    data: dict,
    transaction_type,
    splits,
) -> bool:
    """True when a patch can change DebtPayment or debt balance (not memo-only)."""
    if transaction_type is not None:
        return True
    if splits is not None:
        return True
    for key in _DEBT_TOUCH_KEYS:
        if key not in data:
            continue
        new_val = data[key]
        old_val = getattr(transaction, key, None)
        if key in ("amount", "original_amount"):
            if float(new_val or 0) != float(old_val or 0):
                return True
            continue
        if new_val != old_val:
            return True
    return False


def get_monthly_coverage_net(
    db: Session,
    category_id,
    month,
    year,
    currency_id,
    include_all_currencies: bool = True,
) -> float:
    """Net cover-adjustment amount for a category in a month (target currency).

    Positive = covered from another category; negative = gave cover to another.
    Excluded from activity (real spending) but included in available.
    """
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1)

    filters = [
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.is_adjustment.is_(True),
        Transaction.category_id == category_id,
        or_(
            Transaction.memo.like("Cubrir exceso:%"),
            Transaction.memo.like("Cubierto desde:%"),
        ),
    ]
    if not include_all_currencies:
        filters.append(Transaction.currency_id == currency_id)

    transactions = (
        db.query(Transaction)
        .options(joinedload(Transaction.currency))
        .filter(and_(*filters))
        .all()
    )

    target_currency = db.get(Currency, currency_id)
    if not target_currency:
        return sum(float(t.amount or 0) for t in transactions)

    total = 0.0
    for t in transactions:
        total += convert_currency(
            float(t.amount or 0),
            t.currency.code if t.currency else target_currency.code,
            target_currency.code,
            db,
            rate_date=t.date,
        )
    return total


def normalize_transaction_amount(
    amount: float,
    transaction_type: Optional[Literal['expense', 'income', 'loan']] = None
) -> float:
    """Normalize amount sign using the app convention: expenses negative, income positive."""
    normalized = abs(float(amount or 0))
    if transaction_type in ('expense', 'loan'):
        return -normalized
    if transaction_type == 'income':
        return normalized
    return float(amount or 0)


def normalize_transaction_currency(
    db: Session,
    amount: float,
    currency_id: int,
    account: Account,
    transaction_date: date
) -> tuple[float, int, float | None]:
    """Convert amount to the account's currency if they differ.

    Returns:
        Tuple of (converted_amount, effective_currency_id, fx_rate_or_None).
    """
    if not account or currency_id is None:
        return amount, currency_id, None

    if account.currency_id == currency_id:
        return amount, currency_id, None

    from_currency = db.get(Currency, currency_id)
    to_currency = db.get(Currency, account.currency_id)

    if not from_currency or not to_currency:
        return amount, currency_id, None

    fx_rate = get_rate_for_date(db, transaction_date)
    converted_amount = convert_currency(
        amount=amount,
        from_currency=from_currency.code,
        to_currency=to_currency.code,
        db=db,
        rate_date=transaction_date
    )

    return converted_amount, account.currency_id, fx_rate


def get_base_currency(db: Session) -> Currency | None:
    """Return the system's base currency (is_base=True)."""
    return db.query(Currency).filter_by(is_base=True).first()


def build_transaction_audit_fields(
    db: Session,
    original_amount: float,
    original_currency_id: int,
    transaction_date: date
) -> tuple[float | None, int | None]:
    """Compute base_amount and base_currency_id for audit tracking.

    Converts the original amount to the base currency if different.

    Returns:
        Tuple of (base_amount, base_currency_id).
    """
    base_currency = get_base_currency(db)
    base_currency_id = base_currency.id if base_currency else None
    base_amount = None

    if base_currency:
        original_currency = db.get(Currency, original_currency_id)
        if original_currency and original_currency.code != base_currency.code:
            base_amount = convert_currency(
                amount=original_amount,
                from_currency=original_currency.code,
                to_currency=base_currency.code,
                db=db,
                rate_date=transaction_date
            )
        else:
            base_amount = original_amount

    return base_amount, base_currency_id


def _resolve_target_debt(db: Session, transaction: Transaction, account: Account) -> Debt | None:
    """Find the Debt record linked to a transaction by explicit debt_id, account type, or payment category."""
    if transaction.debt_id:
        return db.query(Debt).filter_by(id=transaction.debt_id).first()
    if account and account.type in {'credit_card', 'credit_loan', 'mortgage'}:
        return db.query(Debt).filter_by(account_id=account.id).first()
    # Match by payment category: if the transaction's category is linked to a debt's payment category
    # This covers paying a mortgage/loan from a checking account with the debt's category.
    if transaction.category_id:
        return db.query(Debt).filter(
            Debt.category_id == transaction.category_id,
            Debt.is_active == True,
            Debt.debt_type.in_(['mortgage', 'credit_loan'])
        ).first()
    return None


def _apply_debt_impact(db: Session, transaction: Transaction, account: Account) -> None:
    """Update debt balances when a transaction affects a debt account."""
    if not transaction_affects_balance(account, transaction.date):
        return

    debt = _resolve_target_debt(db, transaction, account)
    if not debt:
        return

    amount = transaction.amount or 0
    if amount == 0:
        return

    if debt.debt_type == "credit_card":
        debt.current_balance = _cc_balance_in_debt_currency(db, account, debt)
        debt.is_active = debt.current_balance > 0
        # Track transfers into the CC account as explicit payment records for history
        if amount > 0 and transaction.transfer_account_id:
            existing = db.query(DebtPayment).filter_by(transaction_id=transaction.id).first()
            if not existing:
                payment = DebtPayment(
                    debt_id=debt.id,
                    transaction_id=transaction.id,
                    payment_date=transaction.date,
                    amount=amount,
                    principal=amount,
                    interest=0.0,
                    fees=0.0,
                    balance_after=debt.current_balance,
                    notes="Pago registrado desde transferencia"
                )
                db.add(payment)
        return

    payment_amount = abs(amount)
    if amount < 0:
        estimated_interest = _estimate_period_interest(debt, payment_amount)
        estimated_principal = max(0.0, payment_amount - estimated_interest)

        payment = DebtPayment(
            debt_id=debt.id,
            transaction_id=transaction.id,
            payment_date=transaction.date,
            amount=payment_amount,
            principal=estimated_principal,
            interest=estimated_interest,
            fees=0.0,
            balance_after=None,
            notes="Pago registrado desde transacción"
        )
        db.add(payment)
        db.flush()
        if debt.debt_type == "mortgage":
            debt.current_balance = refresh_mortgage_current_balance(db, debt, as_of_date=transaction.date)
            payment.balance_after = debt.current_balance
        else:
            debt.current_balance = max(0.0, debt.current_balance - estimated_principal)
            payment.balance_after = debt.current_balance
        if debt.current_balance <= 0:
            debt.is_active = False
    else:
        debt.current_balance += payment_amount
        debt.is_active = True


def _cc_balance_in_debt_currency(db: Session, account: Account, debt: Debt) -> float:
    """Compute credit-card debt balance from account, converting currency if needed."""
    """Compute credit-card debt balance, converting currency if needed."""
    raw_balance = max(0.0, -(account.balance or 0.0))
    acct_currency = db.query(Currency).filter_by(id=account.currency_id).first()
    acct_code = acct_currency.code if acct_currency else "COP"
    debt_code = debt.currency_code or "COP"
    if acct_code != debt_code:
        raw_balance = convert_currency(raw_balance, acct_code, debt_code, db)
    return raw_balance


def _estimate_period_interest(debt: Debt, payment_amount: float) -> float:
    """Estimate the interest portion of a debt payment based on the debt's rate and balance.

    For debts without an interest rate, returns 0.0 (all payment goes to principal).
    Uses the shared rate priority (monthly → annual → interest_rate).
    The estimated interest is capped at the payment amount.
    """
    if debt.debt_type == "credit_card":
        return 0.0

    monthly_rate = effective_monthly_interest_rate(debt)
    if monthly_rate <= 0:
        return 0.0

    balance = debt.current_balance or 0.0
    if balance <= 0:
        return 0.0

    interest = round(balance * monthly_rate, 2)
    return min(interest, payment_amount)


def _reverse_debt_impact(db: Session, transaction: Transaction, account: Account) -> None:
    """Reverse the debt balance changes when a transaction is deleted or updated."""
    if not transaction_affects_balance(account, transaction.date):
        return

    debt = _resolve_target_debt(db, transaction, account)
    if not debt:
        return

    if debt.debt_type == "credit_card":
        debt.current_balance = _cc_balance_in_debt_currency(db, account, debt)
        debt.is_active = debt.current_balance > 0
        # Delete any transfer payment record linked to this transaction
        payment = db.query(DebtPayment).filter_by(transaction_id=transaction.id, debt_id=debt.id).first()
        if payment:
            db.delete(payment)
        return

    payment = db.query(DebtPayment).filter_by(transaction_id=transaction.id).first()
    if payment:
        principal = payment_principal_amount(payment)
        db.delete(payment)
        if debt.debt_type == "mortgage":
            debt.current_balance = refresh_mortgage_current_balance(db, debt, as_of_date=transaction.date)
        else:
            # Apply reduced balance by principal only; reverse must restore principal, not full payment.
            debt.current_balance += principal
        debt.is_active = True
        return

    amount = transaction.amount or 0
    payment_amount = abs(amount)
    if amount < 0:
        if debt.debt_type == "mortgage":
            debt.current_balance = refresh_mortgage_current_balance(db, debt, as_of_date=transaction.date)
        else:
            # Legacy txs without DebtPayment: cannot recover exact principal vs interest.
            # Restore the full outflow (interest portion stays as residual risk for old data).
            debt.current_balance += payment_amount
        debt.is_active = True
    elif amount > 0:
        if debt.debt_type == "mortgage":
            debt.current_balance = refresh_mortgage_current_balance(db, debt, as_of_date=transaction.date)
        else:
            debt.current_balance = max(0.0, debt.current_balance - payment_amount)
        if debt.current_balance <= 0:
            debt.is_active = False



def _apply_tags_to_transaction(db: Session, transaction: Transaction, tag_ids: list[int] | None) -> None:
    """Tags are intentionally ignored to keep transactions fully independent from tag data."""
    return


def _apply_splits_to_transaction(db: Session, transaction: Transaction, splits_data: list[dict] | None) -> None:
    """Replace transaction splits with new split data, validating sums and categories."""
    if splits_data is None:
        return
    if transaction.transfer_account_id:
        raise ValueError("Transfer transactions cannot have splits")
    transaction.splits.clear()
    if not splits_data:
        return

    split_amounts = [float(split.get("amount") or 0.0) for split in splits_data]
    if not validate_splits_sum(transaction.amount, split_amounts):
        raise ValueError("Split amounts must add up exactly to transaction amount")

    category_ids = [split.get("category_id") for split in splits_data]
    categories = db.query(Category).filter(Category.id.in_(category_ids)).all()
    category_map = {category.id: category for category in categories}
    if not validate_splits_categories_exist(category_map, category_ids):
        raise ValueError("One or more split categories are invalid")

    for split in splits_data:
        transaction.splits.append(
            TransactionSplit(
                category_id=split["category_id"],
                amount=float(split["amount"]),
                note=split.get("note"),
            )
        )


def original_outflow_abs(transaction: Transaction) -> float:
    return abs(float(transaction.amount or 0))


def reimbursed_total(db: Session, original_id: int, exclude_id: int | None = None) -> float:
    """Sum of inflows already linked to an original expense/loan."""
    query = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.related_transaction_id == original_id,
        Transaction.amount > 0,
        Transaction.transfer_account_id.is_(None),
        Transaction.is_adjustment.is_(False),
    )
    if exclude_id is not None:
        query = query.filter(Transaction.id != exclude_id)
    return float(query.scalar() or 0.0)


def reimbursement_remaining(db: Session, original: Transaction, exclude_id: int | None = None) -> float:
    remaining = original_outflow_abs(original) - reimbursed_total(db, original.id, exclude_id=exclude_id)
    return round(remaining, 2)


def _default_reimbursement_category_id(original: Transaction) -> int | None:
    if original.category_id:
        return original.category_id
    if original.splits:
        return original.splits[0].category_id
    return None


def _validate_reimbursement_link(
    db: Session,
    original_id: int,
    amount: float,
    exclude_id: int | None = None,
) -> Transaction:
    original = db.get(Transaction, original_id)
    if not original:
        raise ValueError("Transacción original no encontrada")
    if original.transfer_account_id:
        raise ValueError("No se puede registrar una devolución sobre una transferencia")
    if original.related_transaction_id:
        raise ValueError("No se puede vincular una devolución a otra devolución")
    if float(original.amount or 0) >= 0:
        raise ValueError("La devolución debe vincularse a un gasto o préstamo")
    remaining = reimbursement_remaining(db, original, exclude_id=exclude_id)
    requested = abs(float(amount or 0))
    if requested <= 0:
        raise ValueError("El monto de la devolución debe ser mayor a 0")
    if requested - remaining > 0.01:
        raise ValueError(
            f"El monto supera lo pendiente por devolver ({remaining:.2f})"
        )
    return original


def create_reimbursement(db: Session, original_id: int, data: dict) -> Transaction:
    """Create an inflow linked to an expense or personal loan.

    Uses the original expense category so it reduces net spending and does
    not count as income.
    """
    original = _validate_reimbursement_link(db, original_id, data.get("amount") or 0)
    category_id = data.get("category_id") or _default_reimbursement_category_id(original)
    if not category_id:
        raise ValueError("El gasto original no tiene categoría; asígnala antes de registrar la devolución")

    kind = "loan_repayment" if original.kind == "loan" else "reimbursement"
    payee_name = (data.get("payee_name") or "").strip() or None
    memo = (data.get("memo") or "").strip()
    if not memo:
        origin_label = original.payee.name if original.payee else (original.memo or "gasto")
        origin_date = original.date.isoformat()[:10] if original.date else ""
        prefix = "Devolución de préstamo" if kind == "loan_repayment" else "Reembolso"
        memo = f"{prefix}: {origin_label} {origin_date}".strip()

    payload = {
        "account_id": data.get("account_id") or original.account_id,
        "date": data.get("date", date.today()),
        "payee_name": payee_name,
        "category_id": category_id,
        "memo": memo,
        "amount": abs(float(data["amount"])),
        "currency_id": data.get("currency_id") or original.original_currency_id or original.currency_id,
        "type": "income",
        "cleared": data.get("cleared", False),
        "kind": kind,
        "related_transaction_id": original.id,
    }
    return create_transaction(db, payload)


def enrich_transactions_reimbursement(db: Session, rows: list[dict]) -> list[dict]:
    """Attach reimbursed_total / remaining / related summary to serialized txs."""
    if not rows:
        return rows
    ids = [row["id"] for row in rows if row.get("id")]
    related_ids = [row["related_transaction_id"] for row in rows if row.get("related_transaction_id")]

    totals: dict[int, float] = {}
    if ids:
        grouped = (
            db.query(Transaction.related_transaction_id, func.coalesce(func.sum(Transaction.amount), 0.0))
            .filter(
                Transaction.related_transaction_id.in_(ids),
                Transaction.amount > 0,
            )
            .group_by(Transaction.related_transaction_id)
            .all()
        )
        totals = {int(oid): float(total) for oid, total in grouped if oid is not None}

    originals: dict[int, Transaction] = {}
    if related_ids:
        originals = {
            tx.id: tx
            for tx in db.query(Transaction).options(joinedload(Transaction.payee)).filter(Transaction.id.in_(related_ids))
        }

    for row in rows:
        oid = row.get("id")
        amount = float(row.get("amount") or 0)
        reimbursed = round(totals.get(oid, 0.0), 2)
        if amount < 0:
            remaining = round(abs(amount) - reimbursed, 2)
            row["reimbursed_total"] = reimbursed
            row["reimbursement_remaining"] = remaining
        else:
            row["reimbursed_total"] = 0.0
            row["reimbursement_remaining"] = 0.0

        related = originals.get(row.get("related_transaction_id"))
        if related:
            row["related_payee_name"] = related.payee.name if related.payee else None
            row["related_date"] = related.date.isoformat()[:10] if related.date else None
            row["related_amount"] = related.amount
        else:
            row["related_payee_name"] = None
            row["related_date"] = None
            row["related_amount"] = None
    return rows


def create_transaction(db: Session, data):
    """
    Create a new transaction
    Args:
        data: dict with transaction fields
    Returns:
        Transaction object
    """
    data.pop('mortgage_allocation', None)  # Deprecated: mortgages no longer track real-payment allocations.
    transaction_type = data.pop('type', None)
    tag_ids = data.pop('tag_ids', None)
    splits = data.pop('splits', None)
    source = data.get('source')
    source_id = data.get('source_id')
    if transaction_type == 'loan':
        data['kind'] = data.get('kind') or 'loan'
        transaction_type = 'expense'

    related_id = data.get('related_transaction_id')
    if related_id:
        original = _validate_reimbursement_link(db, related_id, float(data.get('amount') or 0), exclude_id=None)
        transaction_type = 'income'
        data['kind'] = data.get('kind') or (
            'loan_repayment' if original.kind == 'loan' else 'reimbursement'
        )

    transaction_context = db.begin_nested() if db.in_transaction() else db.begin()
    with transaction_context:
        # Get or create payee
        payee = None
        if data.get('payee_name'):
            payee = db.query(Payee).filter_by(name=data['payee_name']).first()
            if not payee:
                payee = Payee(name=data['payee_name'])
                db.add(payee)
                db.flush()

        transaction_date = data.get('date', date.today())
        account = db.get(Account, data['account_id'])
        signed_amount = normalize_transaction_amount(data['amount'], transaction_type)
        normalized_amount, normalized_currency_id, fx_rate = normalize_transaction_currency(
            db,
            signed_amount,
            data['currency_id'],
            account,
            transaction_date
        )
        base_amount, base_currency_id = build_transaction_audit_fields(
            db,
            signed_amount,
            data['currency_id'],
            transaction_date
        )
        # Create transaction
        transaction = Transaction(
            account_id=data['account_id'],
            date=transaction_date,
            payee_id=payee.id if payee else None,
            category_id=data.get('category_id'),
            debt_id=data.get('debt_id'),
            memo=data.get('memo', ''),
            amount=normalized_amount,
            currency_id=normalized_currency_id,
            original_amount=signed_amount,
            original_currency_id=data['currency_id'],
            fx_rate=fx_rate,
            base_amount=base_amount,
            base_currency_id=base_currency_id,
            cleared=data.get('cleared', False),
            approved=data.get('approved', True),
            transfer_account_id=data.get('transfer_account_id'),
            investment_asset_id=data.get('investment_asset_id'),
            source=source,
            source_id=source_id,
            kind=data.get('kind'),
            related_transaction_id=data.get('related_transaction_id'),
        )

        db.add(transaction)
        db.flush()

        _apply_tags_to_transaction(db, transaction, tag_ids)
        _apply_splits_to_transaction(db, transaction, splits)

        # Update account balance
        if account and transaction_affects_balance(account, transaction_date):
            account.balance += normalized_amount

        _apply_debt_impact(db, transaction, account)
        _apply_cc_payment_budget_move(db, transaction, account)

    # Always persist. When a prior query opened a session transaction (e.g. merchant
    # rule lookup), the block above only commits a SAVEPOINT via begin_nested().
    db.commit()
    db.refresh(transaction)
    return transaction


def get_transactions(db: Session, account_id=None, category_id=None, tag_id=None, start_date=None,
                     end_date=None, search=None, transaction_type=None, limit=None, uncategorized=False):
    """
    Get transactions with optional filters
    """
    query = db.query(Transaction).options(
        joinedload(Transaction.category).joinedload(Category.category_group),
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    elif uncategorized:
        query = query.filter(Transaction.category_id.is_(None))

    # tag_id intentionally ignored: transactions no longer depend on tags

    if start_date:
        query = query.filter(Transaction.date >= start_date)

    if end_date:
        query = query.filter(Transaction.date <= end_date)

    if search:
        like = f"%{search}%"
        query = query.outerjoin(Payee, Transaction.payee_id == Payee.id).filter(
            or_(
                Payee.name.ilike(like),
                Transaction.memo.ilike(like),
            )
        )

    if transaction_type == 'expense':
        query = query.filter(Transaction.amount < 0, Transaction.transfer_account_id.is_(None))
    elif transaction_type == 'income':
        query = query.filter(
            Transaction.amount > 0,
            Transaction.transfer_account_id.is_(None),
            Transaction.related_transaction_id.is_(None),
            or_(Transaction.kind.is_(None), ~Transaction.kind.in_(('reimbursement', 'loan_repayment'))),
        )
    elif transaction_type == 'transfer':
        query = query.filter(Transaction.transfer_account_id.isnot(None))
    elif transaction_type == 'reimbursement':
        query = query.filter(
            Transaction.transfer_account_id.is_(None),
            or_(
                Transaction.related_transaction_id.isnot(None),
                Transaction.kind.in_(('reimbursement', 'loan_repayment')),
            ),
        )
    elif transaction_type == 'loan':
        query = query.filter(Transaction.kind == 'loan')

    query = query.order_by(
        Transaction.date.desc(),
        Transaction.currency_id,
        Transaction.amount.desc(),
        Transaction.id.desc()
    )

    if limit is not None and limit > 0:
        query = query.limit(limit)

    return query.all()


def get_last_manual_transactions_by_account(db: Session) -> list[dict]:
    """Return the most recent manual transaction creation date per account."""
    memo_value = func.coalesce(Transaction.memo, '')
    results = (
        db.query(
            Transaction.account_id,
            func.max(Transaction.created_at).label("last_manual_created_at")
        )
        .filter(
            Transaction.import_id.is_(None),
            Transaction.is_adjustment.is_(False),
            memo_value != "Transacción automática",
            ~memo_value.ilike("Auto:%")
        )
        .group_by(Transaction.account_id)
        .all()
    )

    return [
        {
            "account_id": account_id,
            "last_manual_created_at": last_manual_created_at.isoformat()
            if last_manual_created_at else None
        }
        for account_id, last_manual_created_at in results
    ]


def get_transaction_by_id(db: Session, transaction_id):
    """Get single transaction by ID"""
    return db.get(Transaction, transaction_id)


def update_transaction(db: Session, transaction_id, data):
    """Update existing transaction"""
    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        return None

    if transaction.locked:
        raise ValueError("Transacción bloqueada por reconciliación.")

    # Store old amount to update balance
    old_amount = transaction.amount
    old_account_id = transaction.account_id
    old_date = transaction.date
    old_account = db.get(Account, old_account_id)

    transaction_type = data.pop('type', None)

    # Update payee if needed
    if 'payee_name' in data:
        payee_name = (data.get('payee_name') or '').strip()
        if payee_name:
            payee = db.query(Payee).filter_by(name=payee_name).first()
            if not payee:
                payee = Payee(name=payee_name)
                db.add(payee)
                db.flush()
            transaction.payee_id = payee.id
        else:
            transaction.payee_id = None

    tag_ids = data.pop("tag_ids", None)
    splits = data.pop("splits", None)

    related_id = data.get("related_transaction_id", transaction.related_transaction_id)
    if related_id:
        candidate_amount = data.get("amount", transaction.original_amount)
        _validate_reimbursement_link(db, related_id, candidate_amount, exclude_id=transaction.id)

    # Memo/tags-only patches must not regenerate DebtPayment / re-estimate interest.
    touches_debt = _update_touches_debt(transaction, data, transaction_type, splits)
    if touches_debt:
        _reverse_debt_impact(db, transaction, old_account)

    # Update fields
    for key, value in data.items():
        if key not in ['payee_name'] and hasattr(transaction, key):
            setattr(transaction, key, value)

    candidate_amount = data.get('amount', transaction.original_amount)
    original_amount = normalize_transaction_amount(candidate_amount, transaction_type)
    original_currency_id = data.get('currency_id', transaction.original_currency_id)
    new_account = db.get(Account, transaction.account_id)
    normalized_amount, normalized_currency_id, fx_rate = normalize_transaction_currency(
        db,
        original_amount,
        original_currency_id,
        new_account,
        transaction.date
    )
    transaction.amount = normalized_amount
    transaction.currency_id = normalized_currency_id
    transaction.original_amount = original_amount
    transaction.original_currency_id = original_currency_id
    transaction.fx_rate = fx_rate
    base_amount, base_currency_id = build_transaction_audit_fields(
        db,
        original_amount,
        original_currency_id,
        transaction.date
    )
    transaction.base_amount = base_amount
    transaction.base_currency_id = base_currency_id

    # Update account balances (skip virtual budget-cover adjustments)
    touches_balance = not is_budget_cover_adjustment(transaction)
    amount_or_account_changed = (
        float(old_amount or 0) != float(transaction.amount or 0)
        or old_account_id != transaction.account_id
        or old_date != transaction.date
    )
    old_account = db.get(Account, old_account_id)
    if (
        touches_balance
        and amount_or_account_changed
        and old_account
        and transaction_affects_balance(old_account, old_date)
    ):
        old_account.balance -= old_amount

    if (
        touches_balance
        and amount_or_account_changed
        and new_account
        and transaction_affects_balance(new_account, transaction.date)
    ):
        new_account.balance += transaction.amount

    _apply_tags_to_transaction(db, transaction, tag_ids)
    _apply_splits_to_transaction(db, transaction, splits)

    if touches_debt and touches_balance:
        _apply_debt_impact(db, transaction, new_account)

    # Refresh CC payment budget move after edits
    _reverse_cc_payment_budget_move(db, transaction)
    _apply_cc_payment_budget_move(db, transaction, new_account)

    db.commit()
    return transaction


def delete_transaction(db: Session, transaction_id):
    """Delete transaction and update account balance"""
    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        return False

    delete_reason = transaction.delete_block_reason()
    if delete_reason:
        raise ValueError(delete_reason)

    _reverse_cc_payment_budget_move(db, transaction)

    # If this is a transfer, also delete the linked transaction
    if transaction.transfer_account_id:
        linked_transaction = find_linked_transfer(db, transaction)

        if linked_transaction:
            # Update linked account balance
            linked_account = db.get(Account, linked_transaction.account_id)
            if linked_account and transaction_affects_balance(linked_account, linked_transaction.date):
                linked_account.balance -= linked_transaction.amount
            _reverse_debt_impact(db, linked_transaction, linked_account)
            db.delete(linked_transaction)

    # Cover adjustments never touch account.balance on create — keep delete symmetrical
    account = db.get(Account, transaction.account_id)
    if (
        account
        and not is_budget_cover_adjustment(transaction)
        and transaction_affects_balance(account, transaction.date)
    ):
        account.balance -= transaction.amount
    if not is_budget_cover_adjustment(transaction):
        _reverse_debt_impact(db, transaction, account)

    db.query(Transaction).filter(Transaction.related_transaction_id == transaction_id).update(
        {Transaction.related_transaction_id: None},
        synchronize_session=False,
    )

    db.delete(transaction)
    db.commit()
    return True


def create_adjustment(db: Session, data):
    """
    Create a balance adjustment transaction to reconcile account balance with real bank balance.

    When your bank balance differs from the app balance, use this to create an adjustment
    transaction that brings them into sync.

    Args:
        db (Session): Database session
        data (dict): Adjustment data with keys:
            - account_id (int): ID of the account to adjust
            - date (date): Date of the adjustment
            - actual_balance (float): Real balance from your bank
            - memo (str, optional): Note explaining the adjustment

    Returns:
        Transaction: The adjustment transaction created

    Example:
        >>> # App shows 1,000,000 but bank shows 1,050,000
        >>> data = {
        ...     'account_id': 1,
        ...     'date': date(2026, 1, 16),
        ...     'actual_balance': 1050000,
        ...     'memo': 'Reconciliation adjustment - missing income'
        ... }
        >>> adjustment = create_adjustment(db, data)
        >>> print(adjustment.amount)  # 50000 (difference)
    """
    # Get the account
    account = db.get(Account, data['account_id'])
    if not account:
        raise ValueError("Invalid account ID")

    # Calculate the difference between app balance and real balance
    difference = data['actual_balance'] - account.balance

    # If no difference, no adjustment needed
    if difference == 0:
        raise ValueError("No adjustment needed - balances match")

    # Create or get the "Balance Adjustment" payee
    adjustment_payee_name = "Balance Adjustment"
    payee = db.query(Payee).filter_by(name=adjustment_payee_name).first()
    if not payee:
        payee = Payee(name=adjustment_payee_name)
        db.add(payee)
        db.flush()

    adjustment_date = data.get('date', date.today())

    base_amount, base_currency_id = build_transaction_audit_fields(
        db,
        difference,
        account.currency_id,
        adjustment_date
    )

    # Create the adjustment transaction
    adjustment = Transaction(
        account_id=data['account_id'],
        date=adjustment_date,
        payee_id=payee.id,
        category_id=None,  # Adjustments don't have categories
        memo=data.get('memo', f'Balance adjustment: {difference:+.2f}'),
        amount=difference,
        currency_id=account.currency_id,
        original_amount=difference,
        original_currency_id=account.currency_id,
        fx_rate=None,
        base_amount=base_amount,
        base_currency_id=base_currency_id,
        cleared=True,  # Adjustments are always cleared
        approved=True,
        is_adjustment=True
    )

    db.add(adjustment)

    # Update account balance
    if transaction_affects_balance(account, adjustment_date):
        account.balance += difference

    db.commit()
    db.refresh(adjustment)

    return adjustment


def create_transfer(db: Session, data):
    """
    Create a transfer between two accounts.

    A transfer is NOT a single transaction but TWO linked transactions:
        1. An OUTGOING transaction (negative) from the source account.
        2. An INCOMING transaction (positive) to the destination account.

    Both transactions are linked via the transfer_account_id field, which
    points to the opposing account. This allows them to be identified as
    transfers and deleted together when one is removed.

    Multi-currency: Supports transfers between accounts in different currencies.
    If currencies differ, the amount is automatically converted using the current rate.

        Example: Transfer $100 USD from a USD account to a COP account
            - USD account debit: -$100 USD
            - COP account credit: +$400,000 COP (at rate 4000)

    Args:
        db (Session): Database session.
        data (dict): Transfer data with keys:
            - from_account_id (int): Source account ID.
            - to_account_id (int): Destination account ID.
            - date (date): Transfer date.
            - amount (float): Amount in source currency (always positive).
            - from_currency_id (int): Source currency ID.
            - to_currency_id (int): Destination currency ID.
            - memo (str, optional): Note or description.
            - cleared (bool, optional): Whether cleared (default: False).

    Returns:
        list[Transaction, Transaction]: [outgoing_transaction, incoming_transaction]

    Raises:
        ValueError: If from_account_id or to_account_id do not exist.

    Examples:
        # Same-currency transfer
        >>> data = {
        ...     'from_account_id': 1,
        ...     'to_account_id': 2,
        ...     'date': date(2025, 1, 15),
        ...     'amount': 500000,
        ...     'from_currency_id': 1,  # COP
        ...     'to_currency_id': 1,    # COP
        ...     'memo': 'Monthly savings',
        ...     'cleared': True
        ... }
        >>> txns = create_transfer(db, data)
        >>> print(txns[0].amount)  # -500000 (salida)
        >>> print(txns[1].amount)  # +500000 (entrada)

        # Transferencia multi-moneda
        >>> data = {
        ...     'from_account_id': 1,   # Cuenta en COP
        ...     'to_account_id': 3,     # Cuenta en USD
        ...     'date': date(2025, 1, 15),
        ...     'amount': 4000000,      # 4 millones COP
        ...     'from_currency_id': 1,  # COP
        ...     'to_currency_id': 2,    # USD
        ...     'memo': 'Cambio a dólares'
        ... }
        >>> txns = create_transfer(db, data)
        >>> print(txns[0].amount)  # -4000000 COP
        >>> print(txns[1].amount)  # +1000 USD (convertido)

    Comportamiento especial:
        - Las transferencias NO tienen categoría (category_id = None)
        - El payee se crea automáticamente: "Transfer to: {nombre_cuenta}"
        - Actualiza los balances de ambas cuentas automáticamente
        - Si se elimina una transacción de transferencia, se elimina la otra también

    Efectos secundarios:
        - Crea 2 objetos Transaction en DB
        - Crea 2 objetos Payee si no existen
        - Actualiza balance de from_account (resta)
        - Actualiza balance de to_account (suma)
        - Hace commit a la base de datos

    Notas:
        - El campo amount en data siempre debe ser positivo
        - La función se encarga de hacerlo negativo para la salida
        - Para transferencias multi-moneda usa convert_currency() internamente
    """
    if data['from_account_id'] == data['to_account_id']:
        raise ValueError("Cannot transfer to the same account")

    transfer_amount = abs(data.get('amount') or 0)
    if transfer_amount <= 0:
        raise ValueError("Transfer amount must be positive")

    # Get accounts
    from_account = db.get(Account, data['from_account_id'])
    to_account = db.get(Account, data['to_account_id'])

    if not from_account or not to_account:
        raise ValueError("Invalid account IDs")

    # Get currencies
    from_currency_id = data.get('from_currency_id') or from_account.currency_id
    to_currency_id = data.get('to_currency_id') or to_account.currency_id
    from_currency = db.get(Currency, from_currency_id)
    to_currency = db.get(Currency, to_currency_id)
    if not from_currency or not to_currency:
        raise ValueError("Invalid currency IDs")

    transfer_date = data.get('date', date.today())
    # Calculate amounts
    from_amount = -transfer_amount  # Negative (outflow)
    fx_rate = None

    # If different currencies, convert
    if from_currency.code != to_currency.code:
        fx_rate = get_rate_for_date(db, transfer_date)
        to_amount = convert_currency(
            amount=transfer_amount,
            from_currency=from_currency.code,
            to_currency=to_currency.code,
            db=db,
            rate_date=transfer_date
        )
    else:
        to_amount = transfer_amount  # Positive (inflow)

    # Create payee for transfer
    transfer_payee_from = f"Transfer to: {to_account.name}"
    transfer_payee_to = f"Transfer from: {from_account.name}"

    payee_from = db.query(Payee).filter_by(name=transfer_payee_from).first()
    if not payee_from:
        payee_from = Payee(name=transfer_payee_from)
        db.add(payee_from)
        db.flush()

    payee_to = db.query(Payee).filter_by(name=transfer_payee_to).first()
    if not payee_to:
        payee_to = Payee(name=transfer_payee_to)
        db.add(payee_to)
        db.flush()

    from_base_amount, from_base_currency_id = build_transaction_audit_fields(
        db,
        from_amount,
        from_currency_id,
        transfer_date
    )
    to_base_amount, to_base_currency_id = build_transaction_audit_fields(
        db,
        to_amount,
        to_currency_id,
        transfer_date
    )

    # Create outflow transaction (from account)
    from_transaction = Transaction(
        account_id=data['from_account_id'],
        date=transfer_date,
        payee_id=payee_from.id,
        category_id=None,  # Transfers don't have categories
        memo=data.get('memo', ''),
        amount=from_amount,
        currency_id=from_currency_id,
        original_amount=from_amount,
        original_currency_id=from_currency_id,
        fx_rate=fx_rate,
        base_amount=from_base_amount,
        base_currency_id=from_base_currency_id,
        cleared=data.get('cleared', False),
        approved=True,
        transfer_account_id=data['to_account_id']
    )

    # Create inflow transaction (to account)
    to_transaction = Transaction(
        account_id=data['to_account_id'],
        date=transfer_date,
        payee_id=payee_to.id,
        category_id=None,  # Transfers don't have categories
        memo=data.get('memo', ''),
        amount=to_amount,
        currency_id=to_currency_id,
        original_amount=to_amount,
        original_currency_id=to_currency_id,
        fx_rate=fx_rate,
        base_amount=to_base_amount,
        base_currency_id=to_base_currency_id,
        cleared=data.get('cleared', False),
        approved=True,
        transfer_account_id=data['from_account_id']
    )

    db.add(from_transaction)
    db.add(to_transaction)
    _assign_transfer_pair_link(from_transaction, to_transaction)

    # Update account balances
    if transaction_affects_balance(from_account, transfer_date):
        from_account.balance += from_amount  # Subtract from source
    if transaction_affects_balance(to_account, transfer_date):
        to_account.balance += to_amount      # Add to destination

    _apply_debt_impact(db, from_transaction, from_account)
    _apply_debt_impact(db, to_transaction, to_account)

    db.commit()
    db.refresh(from_transaction)
    db.refresh(to_transaction)

    return [from_transaction, to_transaction]


def get_monthly_activity(
    db: Session,
    category_id,
    month,
    year,
    currency_id,
    include_all_currencies: bool = True
):
    """
    Calculate total activity (spending) for a category in a month.
    Returns negative number for expenses.

    Includes transaction_splits: when a transaction has splits, only the split
    amounts for this category count (header category_id alone is ignored).
    """
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1)

    category = db.get(Category, category_id)
    is_income = bool(category and category.category_group and category.category_group.is_income)

    split_tx_ids = db.query(TransactionSplit.transaction_id).filter(
        TransactionSplit.category_id == category_id
    )

    filters = [
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.is_adjustment.is_(False),
        Transaction.transfer_account_id.is_(None),
        or_(
            Transaction.category_id == category_id,
            Transaction.id.in_(split_tx_ids),
        ),
    ]
    if not include_all_currencies:
        filters.append(Transaction.currency_id == currency_id)

    transactions = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.currency),
            joinedload(Transaction.splits).joinedload(TransactionSplit.category),
        )
        .filter(and_(*filters))
        .all()
    )

    target_currency = db.get(Currency, currency_id)
    if not target_currency:
        total = 0.0
        for t in transactions:
            for alloc in get_category_allocations(t):
                if alloc["category_id"] != category_id:
                    continue
                amount = float(alloc["amount"] or 0)
                if is_income and amount <= 0:
                    continue
                if not is_income and amount == 0:
                    continue
                total += amount
        return total

    total = 0.0
    for t in transactions:
        for alloc in get_category_allocations(t):
            if alloc["category_id"] != category_id:
                continue
            amount = float(alloc["amount"] or 0)
            if is_income and amount <= 0:
                continue
            if not is_income and amount == 0:
                continue
            total += convert_currency(
                amount,
                t.currency.code if t.currency else target_currency.code,
                target_currency.code,
                db,
                rate_date=t.date,
            )
    return total


def get_monthly_spent(
    db: Session,
    category_id,
    month,
    year,
    currency_id,
    include_all_currencies: bool = True
):
    """
    Calculate total spending for a category in a month.
    Returns a negative number representing outflows only.

    Honors splits the same way as get_monthly_activity.
    """
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1)

    category = db.get(Category, category_id)
    if category and category.category_group and category.category_group.is_income:
        return 0.0

    split_tx_ids = db.query(TransactionSplit.transaction_id).filter(
        TransactionSplit.category_id == category_id
    )

    filters = [
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.is_adjustment.is_(False),
        Transaction.transfer_account_id.is_(None),
        or_(
            Transaction.category_id == category_id,
            Transaction.id.in_(split_tx_ids),
        ),
    ]
    if not include_all_currencies:
        filters.append(Transaction.currency_id == currency_id)

    transactions = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.currency),
            joinedload(Transaction.splits).joinedload(TransactionSplit.category),
        )
        .filter(and_(*filters))
        .all()
    )

    target_currency = db.get(Currency, currency_id)

    def _negative_portion(amount: float) -> float:
        return amount if amount < 0 else 0.0

    if not target_currency:
        return sum(
            _negative_portion(float(alloc["amount"] or 0))
            for t in transactions
            for alloc in get_category_allocations(t)
            if alloc["category_id"] == category_id
        )

    total = 0.0
    for t in transactions:
        for alloc in get_category_allocations(t):
            if alloc["category_id"] != category_id:
                continue
            amount = _negative_portion(float(alloc["amount"] or 0))
            if amount == 0:
                continue
            total += convert_currency(
                amount,
                t.currency.code if t.currency else target_currency.code,
                target_currency.code,
                db,
                rate_date=t.date,
            )
    return total


def get_account_summary(db: Session):
    """
    Get summary of all accounts with total balances
    """
    accounts = db.query(Account).filter_by(is_closed=False).all()
    excluded_account_types = {'credit_card', 'credit_loan', 'mortgage'}

    summary = {
        'accounts': [acc.to_dict() for acc in accounts],
        'total_by_currency': {}
    }

    for account in accounts:
        if account.type in excluded_account_types or not account.is_budget:
            continue
        currency_code = account.currency.code
        if currency_code not in summary['total_by_currency']:
            summary['total_by_currency'][currency_code] = {
                'total': 0,
                'symbol': account.currency.symbol
            }
        summary['total_by_currency'][currency_code]['total'] += account.balance

    return summary


def amounts_in_cop_and_usd(transaction, db: Session, cop_currency, usd_currency):
    """Return transaction amount converted to COP and USD using original values/date."""
    original_amount = transaction.original_amount
    original_currency_id = transaction.original_currency_id
    transaction_date = transaction.date

    cop_amount = None
    usd_amount = None

    if not original_currency_id or original_amount is None or not transaction_date:
        return cop_amount, usd_amount

    original_currency = db.get(Currency, original_currency_id)
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
