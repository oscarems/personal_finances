from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from finance_app.database import Base


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    target_amount = Column(Float, nullable=False)
    target_date = Column(Date, nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    linked_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    start_date = Column(Date, nullable=False)
    start_amount = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), nullable=False, default="active")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    currency = relationship("Currency")
    linked_account = relationship("Account")
    contributions = relationship("GoalContribution", back_populates="goal", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "target_amount": self.target_amount,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "currency_id": self.currency_id,
            "currency_code": self.currency.code if self.currency else None,
            "linked_account_id": self.linked_account_id,
            "linked_account_name": self.linked_account.name if self.linked_account else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "start_amount": self.start_amount,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id = Column(Integer, primary_key=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    goal = relationship("Goal", back_populates="contributions")
    currency = relationship("Currency")
    account = relationship("Account")
    transaction = relationship("Transaction")

    def to_dict(self):
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "date": self.date.isoformat() if self.date else None,
            "amount": self.amount,
            "currency_id": self.currency_id,
            "currency_code": self.currency.code if self.currency else None,
            "account_id": self.account_id,
            "transaction_id": self.transaction_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
