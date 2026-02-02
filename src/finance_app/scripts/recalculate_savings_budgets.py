#!/usr/bin/env python3
"""
Script para recalcular todos los presupuestos de categorías de ahorro (accumulate).

Este script corrige el problema donde el initial_amount no se aplicó correctamente
debido a un race condition en el frontend. Recalcula todos los presupuestos en orden
cronológico para asegurar que el rollover funcione correctamente.
"""

from finance_app.database import SessionLocal
from finance_app.models import Category, BudgetMonth
from finance_app.services.budget_service import calculate_available
from sqlalchemy import distinct

def recalculate_all_savings_budgets():
    """
    Recalcula todos los presupuestos de categorías con rollover_type='accumulate'
    """
    db = SessionLocal()

    try:
        # Encontrar todas las categorías de ahorro
        savings_categories = db.query(Category).filter(
            Category.rollover_type == 'accumulate'
        ).all()

        print(f"Encontradas {len(savings_categories)} categorías de ahorro")
        print()

        for category in savings_categories:
            print(f"Recalculando: {category.name}")
            print(f"  - Monto inicial: {category.initial_amount}")

            if category.initial_currency_id:
                from finance_app.models import Currency
                initial_currency = db.query(Currency).get(category.initial_currency_id)
                print(f"  - Moneda inicial: {initial_currency.code}")
            else:
                print(f"  - Moneda inicial: No configurada (usará fallback)")

            # Obtener todas las monedas usadas para esta categoría
            budget_currencies = db.query(distinct(BudgetMonth.currency_id)).filter(
                BudgetMonth.category_id == category.id
            ).all()

            for (currency_id,) in budget_currencies:
                from finance_app.models import Currency
                currency = db.query(Currency).get(currency_id)
                print(f"\n  Procesando moneda: {currency.code}")

                # Obtener todos los presupuestos de esta categoría en esta moneda, ordenados por fecha
                budgets = db.query(BudgetMonth).filter(
                    BudgetMonth.category_id == category.id,
                    BudgetMonth.currency_id == currency_id
                ).order_by(BudgetMonth.month).all()

                print(f"    - {len(budgets)} presupuestos encontrados")

                # Recalcular cada presupuesto en orden cronológico
                for budget in budgets:
                    old_available = budget.available

                    # Determinar si hay múltiples monedas en este mes
                    existing_budgets = db.query(BudgetMonth).filter_by(
                        category_id=category.id,
                        month=budget.month
                    ).all()
                    has_multiple_currencies = len({b.currency_id for b in existing_budgets}) > 1

                    # Recalcular available
                    calculate_available(
                        db,
                        budget,
                        include_all_currencies=not has_multiple_currencies
                    )

                    new_available = budget.available

                    if old_available != new_available:
                        print(f"    - {budget.month.strftime('%Y-%m')}: "
                              f"Asignado={budget.assigned}, "
                              f"Actividad={budget.activity}, "
                              f"Disponible: {old_available} → {new_available}")
                    else:
                        print(f"    - {budget.month.strftime('%Y-%m')}: Sin cambios (Disponible={new_available})")

                # Hacer commit después de procesar cada moneda
                db.commit()

            print()

        print("✓ Recálculo completado exitosamente")

    except Exception as e:
        print(f"✗ Error durante el recálculo: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("RECALCULANDO PRESUPUESTOS DE AHORRO")
    print("=" * 60)
    print()

    recalculate_all_savings_budgets()
