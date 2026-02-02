#!/usr/bin/env python3
"""
Script para debuggear el problema específico de 45 USD que se muestra como 90 USD
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import date
from finance_app.database import SessionLocal
from finance_app.models import Category, BudgetMonth, Currency
from finance_app.services.budget_service import calculate_available, get_month_budget
from sqlalchemy.orm import joinedload

def debug_45_usd():
    db = SessionLocal()

    try:
        print("=" * 80)
        print("DEBUGGEAR PROBLEMA DE 45 USD → 90 USD")
        print("=" * 80)
        print()

        # Buscar categorías de savings con initial_amount = 45
        savings_45 = db.query(Category).filter(
            Category.rollover_type == 'accumulate',
            Category.initial_amount == 45.0
        ).all()

        if not savings_45:
            print("🔍 No se encontraron categorías con initial_amount = 45 USD")
            print("    Buscando todas las categorías de savings...")
            savings_45 = db.query(Category).filter(
                Category.rollover_type == 'accumulate'
            ).all()

        for category in savings_45:
            print(f"📁 Categoría: {category.name}")
            print(f"   ID: {category.id}")
            print(f"   Initial Amount: {category.initial_amount}")

            initial_currency = db.query(Currency).get(category.initial_currency_id) if category.initial_currency_id else None
            print(f"   Initial Currency ID: {category.initial_currency_id}")
            print(f"   Initial Currency Code: {initial_currency.code if initial_currency else 'NO ESPECIFICADA'}")
            print()

            # Obtener TODOS los budgets de esta categoría
            budgets = db.query(BudgetMonth).options(
                joinedload(BudgetMonth.currency)
            ).filter(
                BudgetMonth.category_id == category.id
            ).order_by(BudgetMonth.month, BudgetMonth.currency_id).all()

            print(f"   Total de presupuestos: {len(budgets)}")
            print()

            for i, budget in enumerate(budgets, 1):
                currency_code = budget.currency.code if budget.currency else "N/A"
                print(f"   [{i}] {budget.month.strftime('%Y-%m')} - {currency_code}")
                print(f"       Budget ID: {budget.id}")
                print(f"       Currency ID: {budget.currency_id}")
                print(f"       Assigned: {budget.assigned:,.2f}")
                print(f"       Activity: {budget.activity:,.2f}")
                print(f"       Available (ANTES de recalcular): {budget.available:,.2f}")

                # Recalcular para ver qué pasa
                old_available = budget.available
                calculate_available(db, budget)
                print(f"       Available (DESPUÉS de recalcular): {budget.available:,.2f}")

                if abs(old_available - budget.available) > 0.01:
                    print(f"       ⚠️  CAMBIÓ de {old_available:,.2f} a {budget.available:,.2f}")

                # Verificar si hay budget previo
                from finance_app.services.budget_service import get_previous_budget
                prev = get_previous_budget(db, category.id, budget.month, budget.currency_id)
                if prev:
                    print(f"       ℹ️  Hay budget previo: {prev.month.strftime('%Y-%m')} available={prev.available:,.2f}")
                else:
                    print(f"       ℹ️  NO hay budget previo")

                print()

        # Ahora verificar qué se muestra en el presupuesto actual
        print()
        print("=" * 80)
        print("VERIFICANDO GET_MONTH_BUDGET (lo que se muestra en la UI)")
        print("=" * 80)
        print()

        today = date.today()
        month_date = date(today.year, today.month, 1)

        # Obtener en USD
        budget_data_usd = get_month_budget(db, month_date, 'USD')

        print(f"Presupuesto del mes {month_date.strftime('%Y-%m')} en USD:")
        print()

        for group in budget_data_usd['groups']:
            for cat in group['categories']:
                if cat['rollover_type'] == 'accumulate' and cat['available'] > 0:
                    print(f"  - {cat['category_name']}:")
                    print(f"      Assigned: {cat['assigned']:,.2f} USD")
                    print(f"      Activity: {cat['activity']:,.2f} USD")
                    print(f"      Available: {cat['available']:,.2f} USD")

                    if abs(cat['available'] - 90.0) < 1.0:
                        print(f"      🔴 ¡PROBLEMA ENCONTRADO! Available = 90 USD (debería ser 45)")
                    print()

    finally:
        db.close()

if __name__ == "__main__":
    debug_45_usd()
