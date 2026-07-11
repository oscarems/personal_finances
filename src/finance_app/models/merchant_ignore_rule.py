from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from finance_app.database import Base


class MerchantIgnoreRule(Base):
    """Merchant names that should be skipped automatically during Gmail import."""

    __tablename__ = "merchant_ignore_rules"

    id = Column(Integer, primary_key=True)
    merchant_name = Column(String(500), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "merchant_name": self.merchant_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
