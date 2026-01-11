from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime

class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    payee_id = Column(Integer, ForeignKey('payees.id'))
    category_id = Column(Integer, ForeignKey('categories.id'))
    memo = Column(Text)
    amount = Column(Float, nullable=False)  # Positive=inflow, Negative=outflow
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    cleared = Column(Boolean, default=False)  # Reconciliation
    approved = Column(Boolean, default=True)
    transfer_account_id = Column(Integer, ForeignKey('accounts.id'))  # If transfer
    import_id = Column(String(100))  # YNAB import ID to avoid duplicates
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship('Account', foreign_keys=[account_id], back_populates='transactions')
    transfer_account = relationship('Account', foreign_keys=[transfer_account_id])
    payee = relationship('Payee', back_populates='transactions')
    category = relationship('Category', back_populates='transactions')
    currency = relationship('Currency', back_populates='transactions')

    def __repr__(self):
        return f'<Transaction {self.date} {self.amount}>'

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'account_name': self.account.name if self.account else None,
            'date': self.date.isoformat() if self.date else None,
            'payee_id': self.payee_id,
            'payee_name': self.payee.name if self.payee else None,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'memo': self.memo,
            'amount': self.amount,
            'currency': self.currency.to_dict() if self.currency else None,
            'cleared': self.cleared,
            'approved': self.approved,
            'transfer_account_id': self.transfer_account_id,
            'import_id': self.import_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
