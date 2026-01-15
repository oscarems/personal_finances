#!/usr/bin/env python3
"""
Script para migrar la base de datos agregando la columna initial_amount
"""
import sqlite3
import sys
from pathlib import Path

# Database path
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / 'data' / 'finances.db'

def migrate_database():
    """Add initial_amount column to categories table"""

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

        conn.close()
        print("\n✓ Migración completada. Ahora puedes ejecutar 'python init_db.py'")

    except Exception as e:
        print(f"❌ Error al migrar la base de datos: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("MIGRACIÓN DE BASE DE DATOS")
    print("=" * 60)
    print("\nEsta migración agregará la columna 'initial_amount' a categories")

    response = input("\n¿Continuar? (s/n): ")
    if response.lower() == 's':
        migrate_database()
    else:
        print("❌ Migración cancelada")
