from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from finance_app.database import Base


class MerchantRule(Base):
    __tablename__ = "merchant_rules"

    id = Column(Integer, primary_key=True)
    merchant_name = Column(String(500), nullable=False)
    # 'payee' | 'memo' — campo de la transacción contra el que se evalúa la regla.
    field = Column(String(20), nullable=False, default="payee", server_default="payee")
    # 'contains' | 'equals' | 'starts_with' | 'regex'
    operator = Column(String(20), nullable=False, default="contains", server_default="contains")
    # Reglas con prioridad más alta ganan cuando varias coinciden.
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("Category")

    def to_dict(self):
        cat = self.category
        return {
            "id": self.id,
            "merchant_name": self.merchant_name,
            "field": self.field,
            "operator": self.operator,
            "priority": self.priority,
            "category_id": self.category_id,
            "category_name": cat.name if cat else None,
            "category_group": cat.category_group.name if cat and cat.category_group else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
