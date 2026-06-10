from datetime import date, datetime

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from finance_app.database import Base


class AssetPriceHistory(Base):
    __tablename__ = "asset_price_history"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("investment_assets.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    precio = Column(Float, nullable=False)
    fuente = Column(String(20), nullable=False, default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)

    asset = relationship("InvestmentAsset")

    __table_args__ = (
        UniqueConstraint("asset_id", "fecha", name="uq_asset_price_history_asset_fecha"),
    )
