#!/usr/bin/env python3
"""
Script para actualizar categorías de savings que tienen initial_amount
pero no tienen initial_currency_id especificado.

PROBLEMA:
Si una categoría tiene initial_amount pero no initial_currency_id, el código
anterior aplicaba ese monto a TODAS las monedas, causando duplicación.

SOLUCIÓN:
Este script identifica esas categorías y les asigna la moneda correspondiente.

Heurística:
- Si initial_amount < 10,000: probablemente USD
- Si initial_amount >= 10,000: probablemente COP
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from finance_app.database import SessionLocal
from finance_app.models import Category, Currency

def fix_missing_initial_currency():
    db = SessionLocal()

    try:
        # Obtener monedas
        usd_currency = db.query(Currency).filter_by(code='USD').first()
        cop_currency = db.query(Currency).filter_by(code='COP').first()

        if not usd_currency or not cop_currency:
            print("❌ Error: No se encontraron las monedas USD o COP en la base de datos")
            return

        print("=" * 80)
        print("ACTUALIZAR CATEGORÍAS DE SAVINGS SIN MONEDA INICIAL ESPECIFICADA")
        print("=" * 80)
        print()

        # Buscar categorías con initial_amount > 0 pero sin initial_currency_id
        categories_without_currency = db.query(Category).filter(
            Category.rollover_type == 'accumulate',
            Category.initial_amount > 0,
            Category.initial_currency_id == None
        ).all()

        if not categories_without_currency:
            print("✅ No se encontraron categorías que necesiten actualización")
            return

        print(f"Encontradas {len(categories_without_currency)} categorías sin moneda inicial:")
        print()

        for category in categories_without_currency:
            # Heurística para determinar la moneda
            # Montos < 10,000 probablemente son USD
            # Montos >= 10,000 probablemente son COP
            suggested_currency = usd_currency if category.initial_amount < 10000 else cop_currency

            print(f"📁 {category.name}")
            print(f"   Initial Amount: {category.initial_amount:,.2f}")
            print(f"   Moneda sugerida: {suggested_currency.code}")
            print(f"   (Heurística: {'< 10,000 = USD' if category.initial_amount < 10000 else '>= 10,000 = COP'})")
            print()

        print()
        print("¿Deseas aplicar estas sugerencias automáticamente?")
        print("Si no, puedes actualizar manualmente desde la UI de categorías.")
        print()
        response = input("Aplicar sugerencias automáticamente? (s/n): ")

        if response.lower() != 's':
            print()
            print("❌ Proceso cancelado.")
            print()
            print("IMPORTANTE: Debes especificar la moneda inicial para cada categoría")
            print("de savings desde la UI para evitar duplicación del initial_amount.")
            print()
            print("Ve a cada categoría de savings y:")
            print("1. Haz clic en 'Editar'")
            print("2. Especifica la 'Moneda inicial'")
            print("3. Guarda los cambios")
            return

        print()
        print("Aplicando cambios...")
        print()

        updated_count = 0
        for category in categories_without_currency:
            suggested_currency = usd_currency if category.initial_amount < 10000 else cop_currency
            category.initial_currency_id = suggested_currency.id
            updated_count += 1
            print(f"✓ {category.name}: initial_currency_id = {suggested_currency.code}")

        db.commit()

        print()
        print(f"✅ Se actualizaron {updated_count} categorías exitosamente")
        print()
        print("Ahora ejecuta el script de recálculo para actualizar los presupuestos:")
        print("  python fix_savings_double_count.py")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_missing_initial_currency()
