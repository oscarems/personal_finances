from sqlalchemy import Column, Integer, Float, Date, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime

class BudgetMonth(Base):
    """
    YNAB-style budget: cada categoría tiene asignación mensual
    """
    __tablename__ = 'budget_months'

    id = Column(Integer, primary_key=True)
    month = Column(Date, nullable=False, index=True)  # First day of month: 2026-01-01
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    assigned = Column(Float, default=0.0)  # Money assigned to category
    activity = Column(Float, default=0.0)  # Actual spending (calculated)
    available = Column(Float, default=0.0)  # Available = assigned - activity + previous balance
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
            'notes': self.notes
        }
