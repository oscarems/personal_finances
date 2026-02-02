#!/usr/bin/env python3
"""
Script para recalcular todos los presupuestos de categorías de ahorro.

Este script actualiza los valores de 'available' en todos los presupuestos
de categorías tipo 'accumulate' para asegurar que el initial_amount se
aplique correctamente.

Uso:
    python3 recalculate_savings.py
"""
from sqlalchemy import create_engine, distinct
from sqlalchemy.orm import sessionmaker
from finance_app.models import Category, BudgetMonth, Currency
from finance_app.services.budget_service import calculate_available
from finance_app.database import get_db_url

def recalculate():
    # Conectar a la base de datos
    engine = create_engine(get_db_url())
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Encontrar todas las categorías de ahorro
        savings_categories = db.query(Category).filter(
            Category.rollover_type == 'accumulate'
        ).all()

        print(f"Encontradas {len(savings_categories)} categorías de ahorro")
        print("-" * 60)

        for category in savings_categories:
            print(f"\nCategoría: {category.name}")
            print(f"  Monto inicial: {category.initial_amount or 0}")

            # Obtener todas las monedas usadas para esta categoría
            budget_currencies = db.query(distinct(BudgetMonth.currency_id)).filter(
                BudgetMonth.category_id == category.id
            ).all()

            for (currency_id,) in budget_currencies:
                currency = db.query(Currency).get(currency_id)
                print(f"\n  Moneda: {currency.code}")

                # Obtener todos los presupuestos de esta categoría en esta moneda
                budgets = db.query(BudgetMonth).filter(
                    BudgetMonth.category_id == category.id,
                    BudgetMonth.currency_id == currency_id
                ).order_by(BudgetMonth.month).all()

                print(f"    Presupuestos a recalcular: {len(budgets)}")

                updated_count = 0
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

                    if old_available != budget.available:
                        print(f"      {budget.month.strftime('%Y-%m')}: {old_available:,.2f} -> {budget.available:,.2f}")
                        updated_count += 1

                if updated_count > 0:
                    print(f"    ✓ {updated_count} presupuestos actualizados")
                else:
                    print(f"    ✓ Todos los presupuestos ya estaban correctos")

        # Guardar cambios
        db.commit()
        print("\n" + "=" * 60)
        print("✓ Recálculo completado exitosamente")

    except Exception as e:
        db.rollback()
        print(f"\n✗ Error: {e}")
        raise
    finally:
        db.close()

if __name__ == '__main__':
    recalculate()
