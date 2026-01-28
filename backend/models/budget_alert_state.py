from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base


class BudgetAlertState(Base):
    __tablename__ = 'budget_alert_states'

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    period_key = Column(String(7), nullable=False)  # YYYY-MM
    last_state = Column(String(20), nullable=False, default='OK')
    last_notified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship('Category', lazy=True)

    __table_args__ = (
        UniqueConstraint('category_id', 'period_key', name='uq_budget_alert_state_category_period'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'period_key': self.period_key,
            'last_state': self.last_state,
            'last_notified_at': self.last_notified_at.isoformat() if self.last_notified_at else None
        }
