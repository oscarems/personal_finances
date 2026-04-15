from sqlalchemy import Column, Integer, Float, Date, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from finance_app.database import Base
from datetime import datetime

class BudgetMonth(Base):
    """
    Monthly budget: each category has a monthly allocation.
    """
    __tablename__ = 'budget_months'

    id = Column(Integer, primary_key=True)
    month = Column(Date, nullable=False, index=True)  # First day of month: 2026-01-01
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    assigned = Column(Float, default=0.0)  # Money assigned to category
    activity = Column(Float, default=0.0)  # Actual spending (calculated)
    available = Column(Float, default=0.0)  # Available = assigned - activity + previous balance
    initial_amount = Column(Float, default=0.0)  # Initial accumulated amount (for accumulate categories)
    initial_overridden = Column(Boolean, default=False)  # True = explicitly set by user; False = auto-derived from previous month
    assigned_overridden = Column(Boolean, default=False)  # True = explicitly set by user; False = inherited from previous month
    notes = Column(Text)

    # Relationships
    category = relationship('Category', back_populates='budget_months')
    currency = relationship('Currency', back_populates='budget_months')

    # Unique constraint: one budget per category per month per currency
    __table_args__ = (
        UniqueConstraint('month', 'category_id', 'currency_id', name='uq_budget_month_category_currency'),
    )

    def __repr__(self):
        return f'<BudgetMonth {self.month} {self.category.name if self.category else ""}>'

    def to_dict(self):
        return {
            'id': self.id,
            'month': self.month.isoformat() if self.month else None,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'currency': self.currency.to_dict() if self.currency else None,
            'assigned': self.assigned,
            'activity': self.activity,
            'available': self.available,
            'initial_amount': self.initial_amount,
            'notes': self.notes
        }
