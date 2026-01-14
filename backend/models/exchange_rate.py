from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from backend.database import Base
from datetime import datetime


class ExchangeRate(Base):
    __tablename__ = 'exchange_rates'

    id = Column(Integer, primary_key=True)
    from_currency = Column(String(3), nullable=False, index=True)  # USD
    to_currency = Column(String(3), nullable=False, index=True)    # COP
    rate = Column(Float, nullable=False)  # 1 USD = X COP
    date = Column(Date, nullable=False, unique=True, index=True)  # Fecha de la tasa
    source = Column(String(50))  # 'api', 'manual', 'average'
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ExchangeRate {self.from_currency}/{self.to_currency} {self.rate} on {self.date}>'

    def to_dict(self):
        return {
            'id': self.id,
            'from_currency': self.from_currency,
            'to_currency': self.to_currency,
            'rate': self.rate,
            'date': self.date.isoformat() if self.date else None,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
