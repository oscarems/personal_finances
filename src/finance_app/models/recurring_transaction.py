from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from finance_app.database import Base


class RecurringTransaction(Base):
    __tablename__ = 'recurring_transactions'

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    payee_id = Column(Integer, ForeignKey('payees.id'))
    category_id = Column(Integer, ForeignKey('categories.id'))
    description = Column(String(200))  # User-friendly name for this recurring transaction
    amount = Column(Float, nullable=False)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    transaction_type = Column(String(20), default='expense')  # expense or income

    # Recurrence settings
    frequency = Column(String(20), nullable=False)  # daily, weekly, monthly, yearly
    interval = Column(Integer, default=1)  # Every N days/weeks/months/years
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)  # Optional end date

    # For weekly: which day of week (0=Monday, 6=Sunday)
    day_of_week = Column(Integer)

    # For monthly: which day of month (1-31)
    day_of_month = Column(Integer)

    # Status
    is_active = Column(Boolean, default=True)
    last_generated_date = Column(Date)  # Last date a transaction was generated

    # Relationships
    account = relationship('Account', backref='recurring_transactions')
    payee = relationship('Payee', backref='recurring_transactions')
    category = relationship('Category', backref='recurring_transactions')
    currency = relationship('Currency', backref='recurring_transactions')

    def __repr__(self):
        return f'<RecurringTransaction {self.description} {self.frequency}>'

    def to_dict(self):
        inferred_type = self.transaction_type or ('income' if self.amount > 0 else 'expense')
        return {
            'id': self.id,
            'account_id': self.account_id,
            'account_name': self.account.name if self.account else None,
            'payee_id': self.payee_id,
            'payee_name': self.payee.name if self.payee else None,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'description': self.description,
            'amount': self.amount,
            'currency': self.currency.to_dict() if self.currency else None,
            'transaction_type': inferred_type,
            'frequency': self.frequency,
            'interval': self.interval,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'day_of_week': self.day_of_week,
            'day_of_month': self.day_of_month,
            'is_active': self.is_active,
            'last_generated_date': self.last_generated_date.isoformat() if self.last_generated_date else None
        }
