from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint

from finance_app.database import Base


class DebtAmortizationMonthly(Base):
    __tablename__ = "debt_amortization_monthly"
    __table_args__ = (
        UniqueConstraint("debt_id", "as_of_date", name="uq_debt_amortization_monthly"),
    )

    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey("debts.id"), nullable=False)
    snapshot_month = Column(String(7), nullable=False)  # YYYY-MM
    as_of_date = Column(Date, nullable=False)
    currency_code = Column(String(3), nullable=False)
    principal_payment = Column(Float, nullable=False, default=0.0)
    interest_payment = Column(Float, nullable=False, default=0.0)
    total_payment = Column(Float, nullable=False, default=0.0)
    principal_remaining = Column(Float, nullable=False, default=0.0)
    interest_rate_calculated = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
