#!/usr/bin/env python3
"""
Script para debugear el problema de duplicación del initial_amount
"""
from datetime import date
from finance_app.database import SessionLocal
from finance_app.models import Category, BudgetMonth, Currency
from sqlalchemy.orm import joinedload

def debug_savings_issue():
    db = SessionLocal()

    try:
        print("=" * 80)
        print("ANÁLISIS DE SAVINGS CON INITIAL_AMOUNT")
        print("=" * 80)
        print()

        # Obtener categorías de tipo accumulate con initial_amount
        savings_categories = db.query(Category).filter(
            Category.rollover_type == 'accumulate',
            Category.initial_amount > 0
        ).all()

        if not savings_categories:
            print("No se encontraron categorías de savings con initial_amount > 0")
            return

        print(f"Encontradas {len(savings_categories)} categorías de savings con initial_amount\n")

        for category in savings_categories:
            print(f"📁 Categoría: {category.name}")
            print(f"   Initial Amount: {category.initial_amount}")

            initial_currency = db.query(Currency).get(category.initial_currency_id) if category.initial_currency_id else None
            print(f"   Initial Currency: {initial_currency.code if initial_currency else 'N/A'}")
            print()

            # Obtener todos los budgets de esta categoría
            budgets = db.query(BudgetMonth).options(
                joinedload(BudgetMonth.currency)
            ).filter(
                BudgetMonth.category_id == category.id
            ).order_by(BudgetMonth.month, BudgetMonth.currency_id).all()

            if not budgets:
                print("   No hay presupuestos para esta categoría\n")
                continue

            # Agrupar por mes
            budgets_by_month = {}
            for budget in budgets:
                month_key = budget.month.strftime('%Y-%m')
                if month_key not in budgets_by_month:
                    budgets_by_month[month_key] = []
                budgets_by_month[month_key].append(budget)

            print(f"   Presupuestos por mes:")
            for month_key in sorted(budgets_by_month.keys()):
                month_budgets = budgets_by_month[month_key]
                print(f"\n   📅 {month_key}:")

                if len(month_budgets) > 1:
                    print(f"      ⚠️  MÚLTIPLES MONEDAS DETECTADAS ({len(month_budgets)} presupuestos)")

                for budget in month_budgets:
                    currency = budget.currency.code if budget.currency else "N/A"
                    print(f"      - {currency}: assigned={budget.assigned:,.2f}, available={budget.available:,.2f}")

                # Si hay múltiples monedas, verificar si el available suma correctamente
                if len(month_budgets) > 1:
                    total_available = sum(b.available for b in month_budgets)
                    print(f"      💡 Total available (suma simple): {total_available:,.2f}")

                    # Verificar si initial_amount se está contando en ambos
                    if category.initial_amount and len(month_budgets) == 2:
                        # Buscar si hay un budget previo
                        prev_month_budgets = db.query(BudgetMonth).filter(
                            BudgetMonth.category_id == category.id,
                            BudgetMonth.month < month_budgets[0].month
                        ).first()

                        if not prev_month_budgets:
                            print(f"      ⚠️  POSIBLE DUPLICACIÓN: Este es el primer mes y tiene {len(month_budgets)} monedas")
                            print(f"          El initial_amount de {category.initial_amount:,.2f} podría estar aplicándose a ambas")

            print()
            print("-" * 80)
            print()

    finally:
        db.close()

if __name__ == "__main__":
    debug_savings_issue()
