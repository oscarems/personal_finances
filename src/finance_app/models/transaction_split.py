from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from finance_app.database import Base


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    amount = Column(Float, nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transaction = relationship("Transaction", back_populates="splits")
    category = relationship("Category")

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else None,
            "amount": self.amount,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
