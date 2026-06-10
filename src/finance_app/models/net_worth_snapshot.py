from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime

from finance_app.database import Base


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(String(7), nullable=False, unique=True)  # YYYY-MM
    assets_cop = Column(Float, nullable=False, default=0.0)
    liabilities_cop = Column(Float, nullable=False, default=0.0)
    net_cop = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "month": self.month,
            "assets_cop": self.assets_cop,
            "liabilities_cop": self.liabilities_cop,
            "net_cop": self.net_cop,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
