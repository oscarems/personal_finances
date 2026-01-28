"""
Transaction service for CRUD operations
"""
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from backend.models import Transaction, Account, Category, Payee, Currency, Debt, DebtPayment
from backend.services.exchange_rate_service import convert_currency, get_rate_for_date


def transaction_affects_balance(account: Account, transaction_date: date) -> bool:
    if not account or not transaction_date:
        return True
    if not account.created_at:
        return True
    return transaction_date >= account.created_at.date()


def normalize_transaction_currency(
    db: Session,
    amount: float,
    currency_id: int,
    account: Account,
    transaction_date: date
):
    if not account or currency_id is None:
        return amount, currency_id, None

    if account.currency_id == currency_id:
        return amount, currency_id, None

    from_currency = db.query(Currency).get(currency_id)
    to_currency = db.query(Currency).get(account.currency_id)

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


def get_base_currency(db: Session) -> Optional[Currency]:
    return db.query(Currency).filter_by(is_base=True).first()


def build_transaction_audit_fields(
    db: Session,
    original_amount: float,
    original_currency_id: int,
    transaction_date: date
):
    base_currency = get_base_currency(db)
    base_currency_id = base_currency.id if base_currency else None
    base_amount = None

    if base_currency:
        original_currency = db.query(Currency).get(original_currency_id)
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


def _apply_debt_impact(db: Session, transaction: Transaction, account: Account) -> None:
    if not account or account.type not in {'credit_card', 'credit_loan', 'mortgage'}:
        return
    if not transaction_affects_balance(account, transaction.date):
        return

    debt = db.query(Debt).filter_by(account_id=account.id).first()
    if not debt:
        return

    amount = transaction.amount or 0
    if amount == 0:
        return

    payment_amount = abs(amount)
    if amount < 0:
        debt.current_balance = max(0.0, debt.current_balance - payment_amount)
        if debt.current_balance <= 0:
            debt.is_active = False
        payment = DebtPayment(
            debt_id=debt.id,
            transaction_id=transaction.id,
            payment_date=transaction.date,
            amount=payment_amount,
            principal=payment_amount,
            interest=0.0,
            fees=0.0,
            balance_after=debt.current_balance,
            notes="Pago registrado desde transacción"
        )
        db.add(payment)
    else:
        debt.current_balance += payment_amount
        debt.is_active = True


def _reverse_debt_impact(db: Session, transaction: Transaction, account: Account) -> None:
    if not account or account.type not in {'credit_card', 'credit_loan', 'mortgage'}:
        return
    if not transaction_affects_balance(account, transaction.date):
        return

    debt = db.query(Debt).filter_by(account_id=account.id).first()
    if not debt:
        return

    payment = db.query(DebtPayment).filter_by(transaction_id=transaction.id).first()
    if payment:
        debt.current_balance += payment.amount
        debt.is_active = True
        db.delete(payment)
        return

    amount = transaction.amount or 0
    payment_amount = abs(amount)
    if amount < 0:
        debt.current_balance += payment_amount
        debt.is_active = True
    elif amount > 0:
        debt.current_balance = max(0.0, debt.current_balance - payment_amount)
        if debt.current_balance <= 0:
            debt.is_active = False


def create_transaction(db: Session, data):
    """
    Create a new transaction
    Args:
        data: dict with transaction fields
    Returns:
        Transaction object
    """
    # Get or create payee
    payee = None
    if data.get('payee_name'):
        payee = db.query(Payee).filter_by(name=data['payee_name']).first()
        if not payee:
            payee = Payee(name=data['payee_name'])
            db.add(payee)
            db.flush()

    transaction_date = data.get('date', date.today())
    account = db.query(Account).get(data['account_id'])
    normalized_amount, normalized_currency_id, fx_rate = normalize_transaction_currency(
        db,
        data['amount'],
        data['currency_id'],
        account,
        transaction_date
    )
    base_amount, base_currency_id = build_transaction_audit_fields(
        db,
        data['amount'],
        data['currency_id'],
        transaction_date
    )
    # Create transaction
    transaction = Transaction(
        account_id=data['account_id'],
        date=transaction_date,
        payee_id=payee.id if payee else None,
        category_id=data.get('category_id'),
        memo=data.get('memo', ''),
        amount=normalized_amount,
        currency_id=normalized_currency_id,
        original_amount=data['amount'],
        original_currency_id=data['currency_id'],
        fx_rate=fx_rate,
        base_amount=base_amount,
        base_currency_id=base_currency_id,
        cleared=data.get('cleared', False),
        approved=data.get('approved', True),
        transfer_account_id=data.get('transfer_account_id'),
        investment_asset_id=data.get('investment_asset_id')
    )

    db.add(transaction)

    # Update account balance
    if account and transaction_affects_balance(account, transaction_date):
        account.balance += normalized_amount

    _apply_debt_impact(db, transaction, account)

    db.commit()
    return transaction


def get_transactions(db: Session, account_id=None, category_id=None, start_date=None,
                     end_date=None, limit=None):
    """
    Get transactions with optional filters
    """
    query = db.query(Transaction)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    if category_id:
        query = query.filter(Transaction.category_id == category_id)

    if start_date:
        query = query.filter(Transaction.date >= start_date)

    if end_date:
        query = query.filter(Transaction.date <= end_date)

    query = query.order_by(
        Transaction.date.desc(),
        Transaction.currency_id,
        Transaction.amount.desc(),
        Transaction.id.desc()
    )

    if limit is not None and limit > 0:
        query = query.limit(limit)

    return query.all()


def get_transaction_by_id(db: Session, transaction_id):
    """Get single transaction by ID"""
    return db.query(Transaction).get(transaction_id)


def update_transaction(db: Session, transaction_id, data):
    """Update existing transaction"""
    transaction = db.query(Transaction).get(transaction_id)
    if not transaction:
        return None

    # Store old amount to update balance
    old_amount = transaction.amount
    old_account_id = transaction.account_id
    old_date = transaction.date
    old_account = db.query(Account).get(old_account_id)

    _reverse_debt_impact(db, transaction, old_account)

    # Update payee if needed
    if data.get('payee_name'):
        payee = db.query(Payee).filter_by(name=data['payee_name']).first()
        if not payee:
            payee = Payee(name=data['payee_name'])
            db.add(payee)
            db.flush()
        transaction.payee_id = payee.id

    # Update fields
    for key, value in data.items():
        if key not in ['payee_name'] and hasattr(transaction, key):
            setattr(transaction, key, value)

    original_amount = data.get('amount', transaction.original_amount)
    original_currency_id = data.get('currency_id', transaction.original_currency_id)
    new_account = db.query(Account).get(transaction.account_id)
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

    # Update account balances
    old_account = db.query(Account).get(old_account_id)
    if old_account and transaction_affects_balance(old_account, old_date):
        old_account.balance -= old_amount

    if new_account and transaction_affects_balance(new_account, transaction.date):
        new_account.balance += transaction.amount

    _apply_debt_impact(db, transaction, new_account)

    db.commit()
    return transaction


def delete_transaction(db: Session, transaction_id):
    """Delete transaction and update account balance"""
    transaction = db.query(Transaction).get(transaction_id)
    if not transaction:
        return False

    # If this is a transfer, also delete the linked transaction
    if transaction.transfer_account_id:
        # Find the linked transaction
        linked_transaction = db.query(Transaction).filter(
            and_(
                Transaction.account_id == transaction.transfer_account_id,
                Transaction.transfer_account_id == transaction.account_id,
                Transaction.date == transaction.date
            )
        ).first()

        if linked_transaction:
            # Update linked account balance
            linked_account = db.query(Account).get(linked_transaction.account_id)
            if linked_account and transaction_affects_balance(linked_account, linked_transaction.date):
                linked_account.balance -= linked_transaction.amount
            _reverse_debt_impact(db, linked_transaction, linked_account)
            db.delete(linked_transaction)

    # Update account balance
    account = db.query(Account).get(transaction.account_id)
    if account and transaction_affects_balance(account, transaction.date):
        account.balance -= transaction.amount
    _reverse_debt_impact(db, transaction, account)

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
    account = db.query(Account).get(data['account_id'])
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
    Crea una transferencia entre dos cuentas propias.

    Una transferencia NO es una sola transacción, sino DOS transacciones vinculadas:
        1. Transacción de SALIDA (negativa) en la cuenta origen
        2. Transacción de ENTRADA (positiva) en la cuenta destino

    Ambas transacciones están vinculadas mediante el campo transfer_account_id, que
    apunta al ID de la cuenta contraria. Esto permite identificarlas como transferencias
    y eliminarlas juntas si se borra una.

    IMPORTANTE - Multi-moneda:
        Soporta transferencias entre cuentas de diferentes monedas. Si las monedas son
        diferentes, convierte automáticamente usando la tasa de cambio actual.

        Ejemplo: Transferir $100 USD de cuenta USD a cuenta COP
            - Salida de cuenta USD: -$100 USD
            - Entrada a cuenta COP: +$400,000 COP (usando tasa 4000)

    Args:
        db (Session): Sesión de base de datos
        data (dict): Datos de la transferencia con claves:
            - from_account_id (int): ID de cuenta origen
            - to_account_id (int): ID de cuenta destino
            - date (date): Fecha de la transferencia
            - amount (float): Monto en moneda origen (siempre positivo)
            - from_currency_id (int): ID de moneda origen
            - to_currency_id (int): ID de moneda destino
            - memo (str, opcional): Nota o descripción
            - cleared (bool, opcional): Si está conciliada (default: False)

    Returns:
        list[Transaction, Transaction]: Lista con [transacción_salida, transacción_entrada]

    Raises:
        ValueError: Si from_account_id o to_account_id no existen

    Ejemplos:
        # Transferencia misma moneda
        >>> data = {
        ...     'from_account_id': 1,
        ...     'to_account_id': 2,
        ...     'date': date(2025, 1, 15),
        ...     'amount': 500000,
        ...     'from_currency_id': 1,  # COP
        ...     'to_currency_id': 1,    # COP
        ...     'memo': 'Ahorro mensual',
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
    # Get accounts
    from_account = db.query(Account).get(data['from_account_id'])
    to_account = db.query(Account).get(data['to_account_id'])

    if not from_account or not to_account:
        raise ValueError("Invalid account IDs")

    # Get currencies
    from_currency = db.query(Currency).get(data['from_currency_id'])
    to_currency = db.query(Currency).get(data['to_currency_id'])

    transfer_date = data.get('date', date.today())
    # Calculate amounts
    from_amount = -abs(data['amount'])  # Negative (outflow)
    fx_rate = None

    # If different currencies, convert
    if from_currency.code != to_currency.code:
        fx_rate = get_rate_for_date(db, transfer_date)
        to_amount = convert_currency(
            amount=abs(data['amount']),
            from_currency=from_currency.code,
            to_currency=to_currency.code,
            db=db,
            rate_date=transfer_date
        )
    else:
        to_amount = abs(data['amount'])  # Positive (inflow)

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
        data['from_currency_id'],
        transfer_date
    )
    to_base_amount, to_base_currency_id = build_transaction_audit_fields(
        db,
        to_amount,
        data['to_currency_id'],
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
        currency_id=data['from_currency_id'],
        original_amount=from_amount,
        original_currency_id=data['from_currency_id'],
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
        currency_id=data['to_currency_id'],
        original_amount=to_amount,
        original_currency_id=data['to_currency_id'],
        fx_rate=fx_rate,
        base_amount=to_base_amount,
        base_currency_id=to_base_currency_id,
        cleared=data.get('cleared', False),
        approved=True,
        transfer_account_id=data['from_account_id']
    )

    db.add(from_transaction)
    db.add(to_transaction)

    # Update account balances
    if transaction_affects_balance(from_account, transfer_date):
        from_account.balance += from_amount  # Subtract from source
    if transaction_affects_balance(to_account, transfer_date):
        to_account.balance += to_amount      # Add to destination

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
    Calculate total activity (spending) for a category in a month
    Returns negative number for expenses
    """
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1)

    filters = [
        Transaction.category_id == category_id,
        Transaction.date >= start_date,
        Transaction.date < end_date
    ]
    if not include_all_currencies:
        filters.append(Transaction.currency_id == currency_id)

    transactions = db.query(Transaction).options(joinedload(Transaction.currency)).filter(
        and_(*filters)
    ).all()

    target_currency = db.query(Currency).get(currency_id)

    if not target_currency:
        return sum(t.amount for t in transactions)

    return sum(
        convert_currency(
            t.amount,
            t.currency.code if t.currency else target_currency.code,
            target_currency.code,
            db
        )
        for t in transactions
    )


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
