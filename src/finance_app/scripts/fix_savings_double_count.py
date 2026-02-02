#!/usr/bin/env python3
"""
Script para corregir el problema de doble conteo en categorías de savings (accumulate).

PROBLEMA CORREGIDO:
Cuando una categoría de savings tiene presupuestos en múltiples monedas (COP y USD),
el initial_amount se estaba aplicando a CADA moneda, causando duplicación.

Ejemplo del bug:
- Categoría "Ahorros" con initial_amount = $1,000,000 COP
- Presupuesto enero COP: available incluía $1,000,000
- Presupuesto enero USD: available incluía $1,000,000 convertido ($250 USD)
- Total contado: $2,000,000 COP (¡duplicado!)

SOLUCIÓN:
Ahora el initial_amount solo se aplica al presupuesto de la moneda original
(initial_currency_id). Este script recalcula todos los presupuestos existentes.
"""

from datetime import date
from sqlalchemy.orm import Session
from finance_app.database import SessionLocal
from finance_app.models import BudgetMonth, Category
from finance_app.services.budget_service import calculate_available


def fix_savings_double_count():
    """
    Recalcula todos los budgets de categorías tipo 'accumulate' para corregir
    el problema del doble conteo del initial_amount.
    """
    db: Session = SessionLocal()

    try:
        # Obtener todas las categorías tipo 'accumulate'
        accumulate_categories = db.query(Category).filter(
            Category.rollover_type == 'accumulate'
        ).all()

        print(f"Encontradas {len(accumulate_categories)} categorías tipo 'accumulate'")

        total_budgets_fixed = 0

        for category in accumulate_categories:
            print(f"\nProcesando categoría: {category.name}")

            # Obtener todos los budgets de esta categoría, ordenados por mes
            budgets = db.query(BudgetMonth).filter(
                BudgetMonth.category_id == category.id
            ).order_by(BudgetMonth.month.asc()).all()

            print(f"  - {len(budgets)} presupuestos encontrados")

            for budget in budgets:
                # Guardar el valor anterior para comparar
                old_available = budget.available

                # Recalcular con la nueva lógica
                calculate_available(db, budget)

                # Verificar si cambió
                if abs(old_available - budget.available) > 0.01:  # Tolerancia para flotantes
                    print(f"  - {budget.month.strftime('%Y-%m')}: "
                          f"available cambió de {old_available:.2f} a {budget.available:.2f} "
                          f"({budget.currency.code if budget.currency else 'N/A'})")
                    total_budgets_fixed += 1

        # Guardar todos los cambios
        db.commit()

        print(f"\n✅ Proceso completado. {total_budgets_fixed} presupuestos fueron corregidos.")

    except Exception as e:
        print(f"\n❌ Error durante el proceso: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("CORRECCIÓN DE DOBLE CONTEO EN SAVINGS")
    print("=" * 70)
    print()
    print("Este script recalculará todos los presupuestos de categorías tipo")
    print("'accumulate' para corregir el problema del initial_amount contado")
    print("múltiples veces.")
    print()

    response = input("¿Deseas continuar? (s/n): ")
    if response.lower() == 's':
        fix_savings_double_count()
    else:
        print("Proceso cancelado.")
