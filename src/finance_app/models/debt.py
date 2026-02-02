"""
Debt Model - Gestión de deudas (tarjetas de crédito, préstamos, hipotecas)
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Date, Numeric
from sqlalchemy.orm import relationship
from finance_app.database import Base
from datetime import date


class Debt(Base):
    """
    Modelo para gestionar deudas de diferentes tipos:
    - Tarjetas de crédito (credit_card)
    - Créditos de libre inversión (credit_loan)
    - Hipotecas (mortgage)
    """
    __tablename__ = 'debts'

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'))

    # Información básica
    name = Column(String(200), nullable=False)  # Nombre descriptivo de la deuda
    debt_type = Column(String(50), nullable=False)  # 'credit_card', 'credit_loan', 'mortgage'
    currency_code = Column(String(3), ForeignKey('currencies.code'), nullable=False, default='COP')

    # Montos
    original_amount = Column(Float, nullable=False)  # Monto original de la deuda
    current_balance = Column(Float, nullable=False)  # Saldo actual
    credit_limit = Column(Float)  # Cupo/límite (solo para tarjetas de crédito)

    # Tasas y pagos
    interest_rate = Column(Float)  # Tasa de interés anual (%)
    monthly_payment = Column(Float)  # Cuota mensual
    minimum_payment = Column(Float)  # Pago mínimo (para tarjetas de crédito)
    loan_years = Column(Integer)  # Plazo en años (créditos e hipotecas)

    # Fechas
    start_date = Column(Date, nullable=False)  # Fecha de inicio de la deuda
    due_date = Column(Date)  # Fecha de vencimiento total del préstamo
    payment_day = Column(Integer)  # Día del mes para pago (1-31)
    last_accrual_date = Column(Date)  # Fecha del último cálculo de intereses

    # Información adicional
    institution = Column(String(200))  # Entidad financiera
    account_number = Column(String(100))  # Número de cuenta/tarjeta (últimos 4 dígitos)
    notes = Column(String(500))  # Notas adicionales

    # Estado
    is_active = Column(Boolean, default=True)  # Si la deuda está activa
    is_consolidated = Column(Boolean, default=False)  # Si fue consolidada en otra deuda
    has_insurance = Column(Boolean, default=False)  # Si la cuota incluye seguros

    # Saldos detallados (opcional para préstamos/hipotecas)
    principal_balance = Column(Numeric(18, 6))
    interest_balance = Column(Numeric(18, 6))
    annual_interest_rate = Column(Numeric(10, 6))  # Decimal (0.12) o porcentaje (12)
    term_months = Column(Integer)
    next_due_date = Column(Date)

    # Relaciones
    account = relationship('Account', back_populates='debts')
    category = relationship('Category')
    currency = relationship('Currency')
    payments = relationship('DebtPayment', back_populates='debt',
                           lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Debt {self.name} ({self.debt_type}): {self.currency_code} {self.current_balance}>'

    def to_dict(self, include_payments=False):
        """Convierte la deuda a diccionario"""
        data = {
            'id': self.id,
            'account_id': self.account_id,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'name': self.name,
            'debt_type': self.debt_type,
            'currency_code': self.currency_code,
            'original_amount': self.original_amount,
            'current_balance': self.current_balance,
            'credit_limit': self.credit_limit,
            'interest_rate': self.interest_rate,
            'monthly_payment': self.monthly_payment,
            'minimum_payment': self.minimum_payment,
            'loan_years': self.loan_years,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'payment_day': self.payment_day,
            'institution': self.institution,
            'account_number': self.account_number,
            'notes': self.notes,
            'is_active': self.is_active,
            'is_consolidated': self.is_consolidated,
            'has_insurance': self.has_insurance,
        }

        # Cálculos adicionales
        if self.original_amount and self.original_amount > 0:
            data['paid_percentage'] = ((self.original_amount - self.current_balance) / self.original_amount) * 100
        else:
            data['paid_percentage'] = 0

        if self.credit_limit and self.credit_limit > 0:
            data['utilization_percentage'] = (self.current_balance / self.credit_limit) * 100
        else:
            data['utilization_percentage'] = None

        if include_payments:
            data['payments'] = [payment.to_dict() for payment in self.payments]

        return data

    def calculate_remaining_months(self):
        """Calcula los meses restantes de la deuda"""
        if not self.monthly_payment or self.monthly_payment <= 0:
            return None
        if self.current_balance <= 0:
            return 0

        # Cálculo simple sin intereses
        return int(self.current_balance / self.monthly_payment) + 1

    def calculate_total_interest(self):
        """Calcula el interés total a pagar (estimado)"""
        if not self.interest_rate or not self.monthly_payment:
            return None

        months = self.calculate_remaining_months()
        if months is None:
            return None

        total_to_pay = self.monthly_payment * months
        return total_to_pay - self.current_balance


class DebtPayment(Base):
    """
    Registro de pagos realizados a una deuda
    """
    __tablename__ = 'debt_payments'

    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey('debts.id'), nullable=False)
    transaction_id = Column(Integer, ForeignKey('transactions.id'))  # Vinculado a transacción si existe

    # Información del pago
    payment_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)  # Monto total del pago
    principal = Column(Float)  # Pago a capital
    interest = Column(Float)  # Pago a intereses
    fees = Column(Float, default=0)  # Comisiones/cargos adicionales

    # Balance después del pago
    balance_after = Column(Float)  # Saldo después del pago

    notes = Column(String(500))

    # Relaciones
    debt = relationship('Debt', back_populates='payments')
    transaction = relationship('Transaction')

    def __repr__(self):
        return f'<DebtPayment {self.payment_date}: {self.amount}>'

    def to_dict(self):
        return {
            'id': self.id,
            'debt_id': self.debt_id,
            'transaction_id': self.transaction_id,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'amount': self.amount,
            'principal': self.principal,
            'interest': self.interest,
            'fees': self.fees,
            'balance_after': self.balance_after,
            'notes': self.notes
        }
