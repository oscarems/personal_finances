from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Date
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime

class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # checking, savings, credit_card, cash, credit_loan, mortgage, cdt, investment
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    balance = Column(Float, default=0.0)
    is_budget = Column(Boolean, default=True)  # Include in budget
    is_closed = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Campos adicionales opcionales según tipo de cuenta
    # Para créditos, hipotecas, ahorros
    interest_rate = Column(Float)  # Tasa de interés anual (%)

    # Para tarjetas de crédito
    credit_limit = Column(Float)  # Cupo de la tarjeta

    # Para créditos e hipotecas
    monthly_payment = Column(Float)  # Cuota mensual
    original_amount = Column(Float)  # Monto original del préstamo

    # Para fechas de pago o vencimiento
    payment_due_day = Column(Integer)  # Día del mes de pago (1-31)
    maturity_date = Column(Date)  # Fecha de vencimiento (CDT)

    # Relationships
    currency = relationship('Currency', back_populates='accounts')
    transactions = relationship('Transaction',
                                  foreign_keys='Transaction.account_id',
                                  back_populates='account',
                                  lazy=True)
    transfer_transactions = relationship('Transaction',
                                          foreign_keys='Transaction.transfer_account_id',
                                          overlaps="transfer_account",
                                          lazy=True)

    def __repr__(self):
        return f'<Account {self.name}>'

    def to_dict(self):
        result = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'currency': self.currency.to_dict() if self.currency else None,
            'balance': self.balance,
            'is_budget': self.is_budget,
            'is_closed': self.is_closed,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

        # Agregar campos opcionales si existen
        if self.interest_rate is not None:
            result['interest_rate'] = self.interest_rate
        if self.credit_limit is not None:
            result['credit_limit'] = self.credit_limit
        if self.monthly_payment is not None:
            result['monthly_payment'] = self.monthly_payment
        if self.original_amount is not None:
            result['original_amount'] = self.original_amount
        if self.payment_due_day is not None:
            result['payment_due_day'] = self.payment_due_day
        if self.maturity_date is not None:
            result['maturity_date'] = self.maturity_date.isoformat()

        return result
