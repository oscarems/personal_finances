from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime

from finance_app.database import Base


class InvestmentPortfolio(Base):
    __tablename__ = "investment_portfolios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(String(500), nullable=True)
    target_allocation = Column(String(500), nullable=True)
    moneda = Column(String(10), nullable=False, default="COP")
    created_at = Column(DateTime, default=datetime.utcnow)
