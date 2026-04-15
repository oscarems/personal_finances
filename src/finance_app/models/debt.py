"""
Debt Model - Manages debts (credit cards, loans, mortgages).
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Date, Numeric
from sqlalchemy.orm import relationship
from finance_app.database import Base
from datetime import date


class Debt(Base):
    """
    Model for managing debts of different types:
    - Credit cards (credit_card)
    - Personal loans (credit_loan)
    - Mortgages (mortgage)
    """
    __tablename__ = 'debts'

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'))

    # Basic information
    name = Column(String(200), nullable=False)  # Descriptive debt name
    debt_type = Column(String(50), nullable=False)  # 'credit_card', 'credit_loan', 'mortgage'
    currency_code = Column(String(3), ForeignKey('currencies.code'), nullable=False, default='COP')

    # Amounts
    original_amount = Column(Float, nullable=False)  # Original debt amount
    current_balance = Column(Float, nullable=False)  # Current balance
    credit_limit = Column(Float)  # Credit limit (credit cards only)

    # Rates and payments
    interest_rate = Column(Float)  # Annual interest rate (%)
    monthly_payment = Column(Float)  # Monthly payment amount
    minimum_payment = Column(Float)  # Minimum payment (credit cards)
    loan_years = Column(Integer)  # Term in years (loans and mortgages)

    # Dates
    start_date = Column(Date, nullable=False)  # Debt start date
    due_date = Column(Date)  # Full loan maturity date
    payment_day = Column(Integer)  # Day of month for payment (1-31)
    last_accrual_date = Column(Date)  # Date of last interest accrual

    # Additional information
    institution = Column(String(200))  # Financial institution
    account_number = Column(String(100))  # Account/card number (last 4 digits)
    notes = Column(String(500))  # Additional notes

    # Status
    is_active = Column(Boolean, default=True)  # Whether the debt is active
    is_consolidated = Column(Boolean, default=False)  # Whether consolidated into another debt
    has_insurance = Column(Boolean, default=False)  # Whether the payment includes insurance

    # Detailed balances (optional for loans/mortgages)
    principal_balance = Column(Numeric(18, 6))
    interest_balance = Column(Numeric(18, 6))
    annual_interest_rate = Column(Numeric(10, 6))  # Decimal (0.12) or percentage (12)
    term_months = Column(Integer)
    next_due_date = Column(Date)

    # Relationships
    account = relationship('Account', back_populates='debts')
    category = relationship('Category')
    currency = relationship('Currency')
    payments = relationship('DebtPayment', back_populates='debt',
                           lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Debt {self.name} ({self.debt_type}): {self.currency_code} {self.current_balance}>'

    def to_dict(self, include_payments=False):
        """Convert the debt to a dictionary."""
        data = {
            'id': self.id,
            'account_id': self.account_id,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'name': self.name,
            'debt_type': self.debt_type,
            'currency_code': self.currency_code,
            'original_amount': self.original_amount,
            'current_balance': self.current_balance,
            'credit_limit': self.credit_limit,
            'interest_rate': self.interest_rate,
            'monthly_payment': self.monthly_payment,
            'minimum_payment': self.minimum_payment,
            'loan_years': self.loan_years,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'payment_day': self.payment_day,
            'institution': self.institution,
            'account_number': self.account_number,
            'notes': self.notes,
            'is_active': self.is_active,
            'is_consolidated': self.is_consolidated,
            'has_insurance': self.has_insurance,
        }

        # Additional calculations
        if self.original_amount and self.original_amount > 0:
            data['paid_percentage'] = ((self.original_amount - self.current_balance) / self.original_amount) * 100
        else:
            data['paid_percentage'] = 0

        # Effective credit limit: use debt.credit_limit, fallback to account
        effective_credit_limit = None
        if self.credit_limit and self.credit_limit > 0:
            effective_credit_limit = self.credit_limit
        elif self.debt_type == 'credit_card':
            try:
                if self.account:
                    acct_limit = getattr(self.account, 'credit_limit', None)
                    if acct_limit and acct_limit > 0:
                        effective_credit_limit = acct_limit
                    elif self.account.balance and self.account.balance > 0:
                        effective_credit_limit = self.account.balance
            except Exception:
                pass
        data['effective_credit_limit'] = effective_credit_limit

        if effective_credit_limit and effective_credit_limit > 0:
            data['utilization_percentage'] = (self.current_balance / effective_credit_limit) * 100
        else:
            data['utilization_percentage'] = None

        if include_payments:
            data['payments'] = [payment.to_dict() for payment in self.payments]

        return data

    def calculate_remaining_months(self):
        """Calculate remaining months until the debt is paid off."""
        if not self.monthly_payment or self.monthly_payment <= 0:
            return None
        if self.current_balance <= 0:
            return 0

        # Simple calculation without interest
        return int(self.current_balance / self.monthly_payment) + 1

    def calculate_total_interest(self):
        """Calculate total estimated interest to pay."""
        if not self.interest_rate or not self.monthly_payment:
            return None

        months = self.calculate_remaining_months()
        if months is None:
            return None

        total_to_pay = self.monthly_payment * months
        return total_to_pay - self.current_balance


class DebtPayment(Base):
    """
    Record of payments made toward a debt.
    """
    __tablename__ = 'debt_payments'

    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey('debts.id'), nullable=False)
    transaction_id = Column(Integer, ForeignKey('transactions.id'))  # Linked transaction if exists

    # Payment information
    payment_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)  # Total payment amount
    principal = Column(Float)  # Principal portion
    interest = Column(Float)  # Interest portion
    fees = Column(Float, default=0)  # Additional fees/charges

    # Balance after payment
    balance_after = Column(Float)  # Balance remaining after payment

    notes = Column(String(500))

    # Relaciones
    debt = relationship('Debt', back_populates='payments')
    transaction = relationship('Transaction')

    def __repr__(self):
        return f'<DebtPayment {self.payment_date}: {self.amount}>'

    def to_dict(self):
        return {
            'id': self.id,
            'debt_id': self.debt_id,
            'transaction_id': self.transaction_id,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'amount': self.amount,
            'principal': self.principal,
            'interest': self.interest,
            'fees': self.fees,
            'balance_after': self.balance_after,
            'notes': self.notes
        }
