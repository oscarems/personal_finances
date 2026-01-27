from datetime import datetime, date

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class WealthAsset(Base):
    __tablename__ = "wealth_assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    asset_class = Column(String(30), nullable=False)  # inmueble, activo, inversion
    investment_type = Column(String(60), nullable=True)
    value = Column(Float, default=0.0)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    as_of_date = Column(Date, default=date.today)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    currency = relationship("Currency")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "asset_class": self.asset_class,
            "investment_type": self.investment_type,
            "value": self.value,
            "currency_id": self.currency_id,
            "currency": self.currency.to_dict() if self.currency else None,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
