"""
DebtInstallment — compras diferidas en cuotas vinculadas a una tarjeta de crédito.
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Date
from sqlalchemy.orm import relationship
from finance_app.database import Base


class DebtInstallment(Base):
    """Compra diferida en cuotas asociada a una deuda (tarjeta de crédito)."""
    __tablename__ = 'debt_installments'

    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey('debts.id'), nullable=False)

    description = Column(String(300), nullable=False)
    total_amount = Column(Float, nullable=False)      # Monto total de la compra
    installments_total = Column(Integer, nullable=False)   # Número total de cuotas
    installments_paid = Column(Integer, default=0)    # Cuotas ya pagadas
    monthly_amount = Column(Float, nullable=False)    # Monto por cuota
    start_date = Column(Date, nullable=False)         # Fecha de la primera cuota
    has_interest = Column(Boolean, default=False)     # Si tiene interés diferido

    is_active = Column(Boolean, default=True)

    debt = relationship('Debt', back_populates='installments')

    def __repr__(self):
        return f'<DebtInstallment {self.description}: {self.installments_paid}/{self.installments_total}>'

    @property
    def installments_remaining(self) -> int:
        return max(0, self.installments_total - self.installments_paid)

    @property
    def amount_remaining(self) -> float:
        return self.monthly_amount * self.installments_remaining

    @property
    def amount_paid(self) -> float:
        return self.monthly_amount * self.installments_paid

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'debt_id': self.debt_id,
            'description': self.description,
            'total_amount': self.total_amount,
            'installments_total': self.installments_total,
            'installments_paid': self.installments_paid,
            'installments_remaining': self.installments_remaining,
            'monthly_amount': self.monthly_amount,
            'amount_remaining': self.amount_remaining,
            'amount_paid': self.amount_paid,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'has_interest': self.has_interest,
            'is_active': self.is_active,
        }
