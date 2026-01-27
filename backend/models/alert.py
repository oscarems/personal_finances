from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class AlertRule(Base):
    __tablename__ = 'alert_rules'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    rule_type = Column(String(50), default="budget_threshold")
    category_id = Column(Integer, ForeignKey('categories.id'))
    threshold_percent = Column(Float, default=1.0)  # 1.0 = 100% of assigned
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship('Category', lazy=True)

    def __repr__(self):
        return f'<AlertRule {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'rule_type': self.rule_type,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'threshold_percent': self.threshold_percent,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
