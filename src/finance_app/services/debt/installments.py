"""
Servicio para gestión de cuotas diferidas (compras en cuotas de tarjeta de crédito).
"""
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from finance_app.models.debt import Debt
from finance_app.models.debt_installment import DebtInstallment

_UPDATABLE_FIELDS = {
    'description',
    'total_amount',
    'installments_total',
    'installments_paid',
    'monthly_amount',
    'start_date',
    'has_interest',
    'is_active',
}


def _parse_date(value: Any) -> date:
    """Convierte un string ISO o un objeto date a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def get_installments(
    db: Session,
    debt_id: int,
    active_only: bool = True,
) -> list[dict]:
    """Retorna las cuotas diferidas de una deuda ordenadas por start_date descendente.

    Args:
        db: Sesión de base de datos.
        debt_id: ID de la deuda (tarjeta de crédito).
        active_only: Si True, retorna solo cuotas con is_active == True.

    Returns:
        Lista de dicts con los campos de cada DebtInstallment.
    """
    query = db.query(DebtInstallment).filter(DebtInstallment.debt_id == debt_id)
    if active_only:
        query = query.filter(DebtInstallment.is_active.is_(True))
    results = query.order_by(DebtInstallment.start_date.desc()).all()
    return [inst.to_dict() for inst in results]


def create_installment(db: Session, debt_id: int, data: dict) -> DebtInstallment:
    """Crea una nueva cuota diferida para una deuda.

    Args:
        db: Sesión de base de datos.
        debt_id: ID de la deuda a la que pertenece la cuota.
        data: Diccionario con los campos de la cuota:
            - description (str): Descripción de la compra.
            - total_amount (float): Monto total de la compra.
            - installments_total (int): Número total de cuotas.
            - monthly_amount (float): Valor de cada cuota mensual.
            - start_date (str | date): Fecha de la primera cuota (ISO 8601 o date).
            - has_interest (bool, opcional): Si tiene interés diferido. Default False.
            - installments_paid (int, opcional): Cuotas ya pagadas. Default 0.

    Returns:
        El objeto DebtInstallment recién creado.

    Raises:
        ValueError: Si la deuda no existe.
    """
    debt = db.get(Debt, debt_id)
    if debt is None:
        raise ValueError("Deuda no encontrada")

    inst = DebtInstallment(
        debt_id=debt_id,
        description=data['description'],
        total_amount=float(data['total_amount']),
        installments_total=int(data['installments_total']),
        monthly_amount=float(data['monthly_amount']),
        start_date=_parse_date(data['start_date']),
        has_interest=bool(data.get('has_interest', False)),
        installments_paid=int(data.get('installments_paid', 0)),
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def update_installment(db: Session, installment_id: int, data: dict) -> DebtInstallment:
    """Actualiza los campos de una cuota diferida existente.

    Solo se actualizan los campos presentes en `data` que pertenecen al conjunto
    de campos actualizables.

    Args:
        db: Sesión de base de datos.
        installment_id: ID del DebtInstallment a actualizar.
        data: Diccionario con los campos a actualizar (parcial).

    Returns:
        El objeto DebtInstallment actualizado.

    Raises:
        ValueError: Si la cuota no existe.
    """
    inst = db.get(DebtInstallment, installment_id)
    if inst is None:
        raise ValueError("Cuota no encontrada")

    for field, value in data.items():
        if field not in _UPDATABLE_FIELDS:
            continue
        if field == 'start_date' and value is not None:
            value = _parse_date(value)
        setattr(inst, field, value)

    db.commit()
    db.refresh(inst)
    return inst


def delete_installment(db: Session, installment_id: int) -> bool:
    """Elimina una cuota diferida de la base de datos.

    Args:
        db: Sesión de base de datos.
        installment_id: ID del DebtInstallment a eliminar.

    Returns:
        True si se eliminó, False si no existía.
    """
    inst = db.get(DebtInstallment, installment_id)
    if inst is None:
        return False
    db.delete(inst)
    db.commit()
    return True


def get_installments_summary(db: Session, debt_id: int) -> dict:
    """Retorna un resumen consolidado de las cuotas diferidas activas de una deuda.

    Args:
        db: Sesión de base de datos.
        debt_id: ID de la deuda.

    Returns:
        Diccionario con:
            - total_installment_count (int): Número de compras diferidas activas.
            - total_deferred_balance (float): Suma de amount_remaining de todas las activas.
            - total_monthly_installment_payment (float): Suma de monthly_amount de las
              activas que aún tienen cuotas pendientes.
            - installments (list[dict]): Lista de todas las cuotas activas.
    """
    active_installments = (
        db.query(DebtInstallment)
        .filter(
            DebtInstallment.debt_id == debt_id,
            DebtInstallment.is_active.is_(True),
        )
        .order_by(DebtInstallment.start_date.desc())
        .all()
    )

    total_deferred_balance: float = sum(inst.amount_remaining for inst in active_installments)
    total_monthly_payment: float = sum(
        inst.monthly_amount
        for inst in active_installments
        if inst.installments_remaining > 0
    )

    return {
        'total_installment_count': len(active_installments),
        'total_deferred_balance': round(total_deferred_balance, 2),
        'total_monthly_installment_payment': round(total_monthly_payment, 2),
        'installments': [inst.to_dict() for inst in active_installments],
    }
