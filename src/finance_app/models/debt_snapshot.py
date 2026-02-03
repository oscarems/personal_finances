from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, Boolean
from finance_app.database import Base


class DebtSnapshotMonthly(Base):
    __tablename__ = 'debt_snapshots_monthly'
    __table_args__ = (
        UniqueConstraint('debt_id', 'as_of_date', name='uq_debt_snapshot_monthly'),
    )

    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey('debts.id'), nullable=False)
    snapshot_month = Column(String(7), nullable=False)  # YYYY-MM
    as_of_date = Column(Date, nullable=False)
    currency_code = Column(String(3), nullable=False)
    principal_original = Column(Float, nullable=False)
    principal_cop = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DebtSnapshotProjectedMonthly(Base):
    __tablename__ = 'debt_snapshots_projected_monthly'
    __table_args__ = (
        UniqueConstraint('debt_id', 'as_of_date', name='uq_debt_snapshot_projected_monthly'),
    )

    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey('debts.id'), nullable=False)
    snapshot_month = Column(String(7), nullable=False)  # YYYY-MM
    as_of_date = Column(Date, nullable=False)
    currency_code = Column(String(3), nullable=False)
    principal_original = Column(Float, nullable=True)
    principal_cop = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_projected = Column(Boolean, default=True)
