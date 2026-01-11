from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime

class Currency(Base):
    __tablename__ = 'currencies'

    id = Column(Integer, primary_key=True)
    code = Column(String(3), unique=True, nullable=False)  # COP, USD
    symbol = Column(String(10), nullable=False)  # $, US$
    name = Column(String(100))
    exchange_rate_to_base = Column(Float, default=1.0)  # Tasa a COP
    is_base = Column(Boolean, default=False)
    decimals = Column(Integer, default=0)  # Decimales para mostrar
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    accounts = relationship('Account', back_populates='currency', lazy=True)
    transactions = relationship('Transaction', back_populates='currency', lazy=True)
    budget_months = relationship('BudgetMonth', back_populates='currency', lazy=True)

    def __repr__(self):
        return f'<Currency {self.code}>'

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'symbol': self.symbol,
            'name': self.name,
            'exchange_rate_to_base': self.exchange_rate_to_base,
            'is_base': self.is_base,
            'decimals': self.decimals
        }
