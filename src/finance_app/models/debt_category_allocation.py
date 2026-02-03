from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from finance_app.database import Base


class DebtCategoryAllocation(Base):
    __tablename__ = 'debt_category_allocations'
    __table_args__ = (
        UniqueConstraint('debt_id', 'category_id', name='uq_debt_category_allocations'),
    )

    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey('debts.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
