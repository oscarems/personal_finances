from sqlalchemy import Column, Integer, String, Float, Date, DateTime, UniqueConstraint
from finance_app.database import Base
from datetime import datetime


class ExchangeRate(Base):
    __tablename__ = 'exchange_rates'

    id = Column(Integer, primary_key=True)
    from_currency = Column(String(3), nullable=False, index=True)
    to_currency = Column(String(3), nullable=False, index=True)
    rate = Column(Float, nullable=False)  # 1 from_currency = rate to_currency
    date = Column(Date, nullable=False, index=True)
    source = Column(String(50))  # 'api_primary', 'api_fallback', 'average', 'default'
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('from_currency', 'to_currency', 'date', name='uq_exchange_rate_pair_date'),
    )

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
