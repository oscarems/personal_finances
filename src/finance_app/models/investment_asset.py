from datetime import date, datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from finance_app.database import Base


class InvestmentAsset(Base):
    __tablename__ = "investment_assets"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("investment_portfolios.id"), nullable=True)
    simbolo = Column(String(50), nullable=False)
    nombre = Column(String(200), nullable=False)
    tipo = Column(String(30), nullable=False)
    asset_class = Column(String(30), nullable=False)
    unidades = Column(Float, nullable=False)
    precio_compra = Column(Float, nullable=False)
    fecha_compra = Column(Date, nullable=False)
    moneda = Column(String(10), nullable=False, default="USD")
    notas = Column(String(500), nullable=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("InvestmentPortfolio")
