"""
Transaction service for CRUD operations
"""
from datetime import datetime, date
from sqlalchemy import and_, or_, extract
from sqlalchemy.orm import Session
from backend.models import Transaction, Account, Category, Payee, Currency


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

    # Create transaction
    transaction = Transaction(
        account_id=data['account_id'],
        date=data.get('date', date.today()),
        payee_id=payee.id if payee else None,
        category_id=data.get('category_id'),
        memo=data.get('memo', ''),
        amount=data['amount'],
        currency_id=data['currency_id'],
        cleared=data.get('cleared', False),
        approved=data.get('approved', True),
        transfer_account_id=data.get('transfer_account_id')
    )

    db.add(transaction)

    # Update account balance
    account = db.query(Account).get(data['account_id'])
    if account:
        account.balance += data['amount']

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

    query = query.order_by(Transaction.date.desc(), Transaction.id.desc())

    if limit:
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

    # Update account balances
    old_account = db.query(Account).get(old_account_id)
    if old_account:
        old_account.balance -= old_amount

    new_account = db.query(Account).get(transaction.account_id)
    if new_account:
        new_account.balance += transaction.amount

    db.commit()
    return transaction


def delete_transaction(db: Session, transaction_id):
    """Delete transaction and update account balance"""
    transaction = db.query(Transaction).get(transaction_id)
    if not transaction:
        return False

    # Update account balance
    account = db.query(Account).get(transaction.account_id)
    if account:
        account.balance -= transaction.amount

    db.delete(transaction)
    db.commit()
    return True


def get_monthly_activity(db: Session, category_id, month, year, currency_id):
    """
    Calculate total activity (spending) for a category in a month
    Returns negative number for expenses
    """
    transactions = db.query(Transaction).filter(
        and_(
            Transaction.category_id == category_id,
            Transaction.currency_id == currency_id,
            extract('month', Transaction.date) == month,
            extract('year', Transaction.date) == year
        )
    ).all()

    return sum(t.amount for t in transactions)


def get_account_summary(db: Session):
    """
    Get summary of all accounts with total balances
    """
    accounts = db.query(Account).filter_by(is_closed=False).all()

    summary = {
        'accounts': [acc.to_dict() for acc in accounts],
        'total_by_currency': {}
    }

    for account in accounts:
        currency_code = account.currency.code
        if currency_code not in summary['total_by_currency']:
            summary['total_by_currency'][currency_code] = {
                'total': 0,
                'symbol': account.currency.symbol
            }
        summary['total_by_currency'][currency_code]['total'] += account.balance

    return summary
