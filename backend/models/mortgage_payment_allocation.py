from sqlalchemy import Column, Integer, ForeignKey, Date, DateTime, String, Numeric, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from backend.database import Base


class MortgagePaymentAllocation(Base):
    __tablename__ = "mortgage_payment_allocations"
    __table_args__ = (
        UniqueConstraint("transaction_id", "loan_id", name="uq_mortgage_payment_allocation_tx_loan"),
    )

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    loan_id = Column(Integer, ForeignKey("debts.id", ondelete="CASCADE"), nullable=False)
    payment_date = Column(Date, nullable=False)
    period = Column(String(20))
    notes = Column(Text)
    interest_paid = Column(Numeric(18, 6), nullable=False)
    principal_paid = Column(Numeric(18, 6), nullable=False)
    fees_paid = Column(Numeric(18, 6), nullable=False, default=0)
    escrow_paid = Column(Numeric(18, 6), nullable=False, default=0)
    extra_principal_paid = Column(Numeric(18, 6), nullable=False, default=0)
    currency_code = Column(String(3), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transaction = relationship("Transaction")
    loan = relationship("Debt")

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "loan_id": self.loan_id,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "period": self.period,
            "notes": self.notes,
            "interest_paid": float(self.interest_paid) if self.interest_paid is not None else None,
            "principal_paid": float(self.principal_paid) if self.principal_paid is not None else None,
            "fees_paid": float(self.fees_paid) if self.fees_paid is not None else None,
            "escrow_paid": float(self.escrow_paid) if self.escrow_paid is not None else None,
            "extra_principal_paid": float(self.extra_principal_paid) if self.extra_principal_paid is not None else None,
            "currency_code": self.currency_code,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
