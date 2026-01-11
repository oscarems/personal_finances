from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime

class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # checking, savings, credit_card, cash
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    balance = Column(Float, default=0.0)
    is_budget = Column(Boolean, default=True)  # Include in budget
    is_closed = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    currency = relationship('Currency', back_populates='accounts')
    transactions = relationship('Transaction',
                                  foreign_keys='Transaction.account_id',
                                  back_populates='account',
                                  lazy=True)
    transfer_transactions = relationship('Transaction',
                                          foreign_keys='Transaction.transfer_account_id',
                                          lazy=True)

    def __repr__(self):
        return f'<Account {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'currency': self.currency.to_dict() if self.currency else None,
            'balance': self.balance,
            'is_budget': self.is_budget,
            'is_closed': self.is_closed,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
