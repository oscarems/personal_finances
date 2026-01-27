from sqlalchemy import Column, Integer, Float, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class ReconciliationSession(Base):
    __tablename__ = 'reconciliation_sessions'

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    statement_date = Column(Date, nullable=False)
    statement_balance = Column(Float, nullable=False)
    cleared_balance = Column(Float, default=0.0)
    difference = Column(Float, default=0.0)
    notes = Column(Text)
    adjustment_transaction_id = Column(Integer, ForeignKey('transactions.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship('Account', lazy=True)
    adjustment_transaction = relationship('Transaction', lazy=True)

    def __repr__(self):
        return f'<ReconciliationSession {self.account_id} {self.statement_date}>'

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'account_name': self.account.name if self.account else None,
            'statement_date': self.statement_date.isoformat() if self.statement_date else None,
            'statement_balance': self.statement_balance,
            'cleared_balance': self.cleared_balance,
            'difference': self.difference,
            'notes': self.notes,
            'adjustment_transaction_id': self.adjustment_transaction_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
