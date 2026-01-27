#!/usr/bin/env python3
"""
Script para migrar la base de datos agregando columnas nuevas.
"""
import sqlite3
import sys
from pathlib import Path

# Database path
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / 'data' / 'finances.db'

def migrate_database():
    """Add missing columns to categories/accounts tables"""

    if not DATABASE_PATH.exists():
        print("❌ Base de datos no encontrada. Ejecuta 'python init_db.py' primero.")
        sys.exit(1)

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(categories)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'initial_amount' in columns:
            print("✓ La columna 'initial_amount' ya existe")
        else:
            print("🔧 Agregando columna 'initial_amount' a la tabla categories...")
            cursor.execute("ALTER TABLE categories ADD COLUMN initial_amount FLOAT DEFAULT 0.0")
            conn.commit()
            print("✅ Columna agregada exitosamente")

        if 'initial_currency_id' in columns:
            print("✓ La columna 'initial_currency_id' ya existe")
        else:
            print("🔧 Agregando columna 'initial_currency_id' a la tabla categories...")
            cursor.execute("ALTER TABLE categories ADD COLUMN initial_currency_id INTEGER")
            conn.commit()
            print("✅ Columna agregada exitosamente")

        cursor.execute("PRAGMA table_info(accounts)")
        account_columns = [row[1] for row in cursor.fetchall()]

        if 'loan_years' in account_columns:
            print("✓ La columna 'loan_years' ya existe")
        else:
            print("🔧 Agregando columna 'loan_years' a la tabla accounts...")
            cursor.execute("ALTER TABLE accounts ADD COLUMN loan_years INTEGER")
            conn.commit()
            print("✅ Columna agregada exitosamente")

        if 'loan_start_date' in account_columns:
            print("✓ La columna 'loan_start_date' ya existe")
        else:
            print("🔧 Agregando columna 'loan_start_date' a la tabla accounts...")
            cursor.execute("ALTER TABLE accounts ADD COLUMN loan_start_date DATE")
            conn.commit()
            print("✅ Columna agregada exitosamente")

        cursor.execute("PRAGMA table_info(debts)")
        debt_columns = [row[1] for row in cursor.fetchall()]

        if 'loan_years' in debt_columns:
            print("✓ La columna 'loan_years' ya existe en debts")
        else:
            print("🔧 Agregando columna 'loan_years' a la tabla debts...")
            cursor.execute("ALTER TABLE debts ADD COLUMN loan_years INTEGER")
            conn.commit()
            print("✅ Columna agregada exitosamente en debts")

        cursor.execute("PRAGMA table_info(recurring_transactions)")
        recurring_columns = [row[1] for row in cursor.fetchall()]

        if 'transaction_type' in recurring_columns:
            print("✓ La columna 'transaction_type' ya existe")
        else:
            print("🔧 Agregando columna 'transaction_type' a la tabla recurring_transactions...")
            cursor.execute("ALTER TABLE recurring_transactions ADD COLUMN transaction_type VARCHAR(20) DEFAULT 'expense'")
            conn.commit()
            print("✅ Columna agregada exitosamente")

        cursor.execute("PRAGMA table_info(transactions)")
        transaction_columns = [row[1] for row in cursor.fetchall()]

        if 'investment_asset_id' in transaction_columns:
            print("✓ La columna 'investment_asset_id' ya existe en transactions")
        else:
            print("🔧 Agregando columna 'investment_asset_id' a la tabla transactions...")
            cursor.execute("ALTER TABLE transactions ADD COLUMN investment_asset_id INTEGER")
            conn.commit()
            print("✅ Columna agregada exitosamente en transactions")

        cursor.execute("PRAGMA table_info(wealth_assets)")
        wealth_columns = [row[1] for row in cursor.fetchall()]

        if 'return_rate' in wealth_columns:
            print("✓ La columna 'return_rate' ya existe en wealth_assets")
        else:
            print("🔧 Agregando columna 'return_rate' a la tabla wealth_assets...")
            cursor.execute("ALTER TABLE wealth_assets ADD COLUMN return_rate FLOAT")
            conn.commit()
            print("✅ Columna agregada exitosamente en wealth_assets")

        if 'return_amount' in wealth_columns:
            print("✓ La columna 'return_amount' ya existe en wealth_assets")
        else:
            print("🔧 Agregando columna 'return_amount' a la tabla wealth_assets...")
            cursor.execute("ALTER TABLE wealth_assets ADD COLUMN return_amount FLOAT")
            conn.commit()
            print("✅ Columna agregada exitosamente en wealth_assets")

        if 'mortgage_debt_id' in wealth_columns:
            print("✓ La columna 'mortgage_debt_id' ya existe en wealth_assets")
        else:
            print("🔧 Agregando columna 'mortgage_debt_id' a la tabla wealth_assets...")
            cursor.execute("ALTER TABLE wealth_assets ADD COLUMN mortgage_debt_id INTEGER")
            conn.commit()
            print("✅ Columna agregada exitosamente en wealth_assets")

        conn.close()
        print("\n✓ Migración completada. Ahora puedes ejecutar 'python init_db.py'")

    except Exception as e:
        print(f"❌ Error al migrar la base de datos: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("MIGRACIÓN DE BASE DE DATOS")
    print("=" * 60)
    print("\nEsta migración agregará columnas nuevas a categories, accounts y recurring_transactions")

    response = input("\n¿Continuar? (s/n): ")
    if response.lower() == 's':
        migrate_database()
    else:
        print("❌ Migración cancelada")
