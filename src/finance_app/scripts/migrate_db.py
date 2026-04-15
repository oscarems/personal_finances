#!/usr/bin/env python3
"""
Script to migrate the database by adding new columns.
"""
import sqlite3
import sys
from pathlib import Path

# Database path - project root is three levels up from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATABASE_DIR = PROJECT_ROOT / 'data'
DATABASE_PATH = DATABASE_DIR / 'finances.db'


def _find_all_databases() -> list[Path]:
    """Find all .db files in the data directory."""
    dbs = []
    if DATABASE_PATH.exists():
        dbs.append(DATABASE_PATH)
    demo_path = DATABASE_DIR / 'finances_demo.db'
    if demo_path.exists():
        dbs.append(demo_path)
    if DATABASE_DIR.exists():
        for p in DATABASE_DIR.glob('*.db'):
            if p not in dbs:
                dbs.append(p)
    return dbs


def migrate_database(db_path: Path | None = None):
    """Add missing columns to categories/accounts tables"""
    target = db_path or DATABASE_PATH

    if not target.exists():
        print(f"❌ Base de datos no encontrada en {target}. Ejecuta 'python init_db.py' primero.")
        if db_path is None:
            sys.exit(1)
        return

    print(f"\n--- Migrando: {target.name} ---")

    try:
        conn = sqlite3.connect(target)
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

        if 'alerts_enabled' in columns:
            print("✓ La columna 'alerts_enabled' ya existe")
        else:
            print("🔧 Agregando columna 'alerts_enabled' a la tabla categories...")
            cursor.execute("ALTER TABLE categories ADD COLUMN alerts_enabled BOOLEAN DEFAULT 1")
            conn.commit()
            print("✅ Columna agregada exitosamente")

        if 'smart_notif_enabled' in columns:
            print("✓ La columna 'smart_notif_enabled' ya existe")
        else:
            print("🔧 Agregando columna 'smart_notif_enabled' a la tabla categories...")
            cursor.execute("ALTER TABLE categories ADD COLUMN smart_notif_enabled BOOLEAN DEFAULT 1")
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

        # Tags
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tags'")
        if cursor.fetchone():
            print("✓ La tabla 'tags' ya existe")
        else:
            print("🔧 Creando tabla 'tags'...")
            cursor.execute("""
                CREATE TABLE tags (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(80) NOT NULL UNIQUE,
                    color VARCHAR(20),
                    created_at DATETIME
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_tags_name ON tags(name)")
            conn.commit()
            print("✅ Tabla creada exitosamente en tags")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transaction_tags'")
        if cursor.fetchone():
            print("✓ La tabla 'transaction_tags' ya existe")
        else:
            print("🔧 Creando tabla 'transaction_tags'...")
            cursor.execute("""
                CREATE TABLE transaction_tags (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    created_at DATETIME,
                    CONSTRAINT uq_transaction_tag UNIQUE (transaction_id, tag_id),
                    FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
                    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_transaction_tags_transaction_id ON transaction_tags(transaction_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_transaction_tags_tag_id ON transaction_tags(tag_id)")
            conn.commit()
            print("✅ Tabla creada exitosamente en transaction_tags")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transaction_splits'")
        if cursor.fetchone():
            print("✓ La tabla 'transaction_splits' ya existe")
        else:
            print("🔧 Creando tabla 'transaction_splits'...")
            cursor.execute("""
                CREATE TABLE transaction_splits (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    amount FLOAT NOT NULL,
                    note TEXT,
                    created_at DATETIME,
                    FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
                    FOREIGN KEY(category_id) REFERENCES categories(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_transaction_splits_transaction_id ON transaction_splits(transaction_id)")
            conn.commit()
            print("✅ Tabla creada exitosamente en transaction_splits")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='goals'")
        if cursor.fetchone():
            print("✓ La tabla 'goals' ya existe")
        else:
            print("🔧 Creando tabla 'goals'...")
            cursor.execute("""
                CREATE TABLE goals (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    target_amount FLOAT NOT NULL,
                    target_date DATE NOT NULL,
                    currency_id INTEGER NOT NULL,
                    linked_account_id INTEGER,
                    start_date DATE NOT NULL,
                    start_amount FLOAT NOT NULL DEFAULT 0.0,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    notes TEXT,
                    created_at DATETIME,
                    FOREIGN KEY(currency_id) REFERENCES currencies(id),
                    FOREIGN KEY(linked_account_id) REFERENCES accounts(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_goals_target_date ON goals(target_date)")
            conn.commit()
            print("✅ Tabla creada exitosamente en goals")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='goal_contributions'")
        if cursor.fetchone():
            print("✓ La tabla 'goal_contributions' ya existe")
        else:
            print("🔧 Creando tabla 'goal_contributions'...")
            cursor.execute("""
                CREATE TABLE goal_contributions (
                    id INTEGER PRIMARY KEY,
                    goal_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    amount FLOAT NOT NULL,
                    currency_id INTEGER NOT NULL,
                    account_id INTEGER,
                    transaction_id INTEGER,
                    note TEXT,
                    created_at DATETIME,
                    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
                    FOREIGN KEY(currency_id) REFERENCES currencies(id),
                    FOREIGN KEY(account_id) REFERENCES accounts(id),
                    FOREIGN KEY(transaction_id) REFERENCES transactions(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_goal_contributions_goal_id ON goal_contributions(goal_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_goal_contributions_date ON goal_contributions(date)")
            conn.commit()
            print("✅ Tabla creada exitosamente en goal_contributions")

        # --- Country column on accounts ---
        cursor.execute("PRAGMA table_info(accounts)")
        account_columns_refreshed = [row[1] for row in cursor.fetchall()]

        if 'country' in account_columns_refreshed:
            print("✓ La columna 'country' ya existe en accounts")
        else:
            print("🔧 Agregando columna 'country' a la tabla accounts...")
            cursor.execute("ALTER TABLE accounts ADD COLUMN country VARCHAR(50)")
            conn.commit()
            print("✅ Columna agregada exitosamente en accounts")

        # Backfill country values
        print("🔧 Actualizando country en cuentas existentes...")
        cursor.execute("UPDATE accounts SET country = 'Colombia' WHERE lower(name) = 'cuenta corriente cop' AND (country IS NULL OR country = '')")
        cursor.execute("UPDATE accounts SET country = 'Panama' WHERE lower(name) = 'ahorros usd' AND (country IS NULL OR country = '')")
        conn.commit()
        updated = cursor.execute("SELECT name, country FROM accounts WHERE country IS NOT NULL").fetchall()
        for name, country in updated:
            print(f"  ✓ {name} → {country}")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='debt_amortization_monthly'")
        if cursor.fetchone():
            print("✓ La tabla 'debt_amortization_monthly' ya existe")
        else:
            print("🔧 Creando tabla 'debt_amortization_monthly'...")
            cursor.execute("""
                CREATE TABLE debt_amortization_monthly (
                    id INTEGER PRIMARY KEY,
                    debt_id INTEGER NOT NULL,
                    snapshot_month VARCHAR(7) NOT NULL,
                    as_of_date DATE NOT NULL,
                    currency_code VARCHAR(3) NOT NULL,
                    principal_payment FLOAT NOT NULL DEFAULT 0.0,
                    interest_payment FLOAT NOT NULL DEFAULT 0.0,
                    total_payment FLOAT NOT NULL DEFAULT 0.0,
                    principal_remaining FLOAT NOT NULL DEFAULT 0.0,
                    interest_rate_calculated FLOAT NOT NULL DEFAULT 0.0,
                    status VARCHAR(20) NOT NULL,
                    created_at DATETIME,
                    CONSTRAINT uq_debt_amortization_monthly UNIQUE (debt_id, as_of_date),
                    FOREIGN KEY(debt_id) REFERENCES debts(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
            print("✅ Tabla creada exitosamente en debt_amortization_monthly")

        # --- initial_amount column on budget_months ---
        cursor.execute("PRAGMA table_info(budget_months)")
        budget_columns = [row[1] for row in cursor.fetchall()]

        if 'initial_overridden' in budget_columns:
            print("✓ La columna 'initial_overridden' ya existe en budget_months")
        else:
            print("🔧 Agregando columna 'initial_overridden' a la tabla budget_months...")
            cursor.execute("ALTER TABLE budget_months ADD COLUMN initial_overridden BOOLEAN DEFAULT 0")
            conn.commit()
            print("✅ Columna agregada exitosamente")

            # Backfill: marcar como overridden solo los meses "semilla" (primer mes de la categoría/moneda con initial != 0)
            # Todos los demás se quedan en False para que se auto-deriven del mes anterior
            cursor.execute("""
                UPDATE budget_months
                SET initial_overridden = 1
                WHERE initial_amount != 0.0
                AND NOT EXISTS (
                    SELECT 1 FROM budget_months prev
                    WHERE prev.category_id = budget_months.category_id
                    AND prev.currency_id = budget_months.currency_id
                    AND prev.month < budget_months.month
                )
            """)
            conn.commit()
            print("✅ Backfill initial_overridden completado (seeds marcados como overridden)")

        if 'assigned_overridden' in budget_columns:
            print("✓ La columna 'assigned_overridden' ya existe en budget_months")
        else:
            print("🔧 Agregando columna 'assigned_overridden' a la tabla budget_months...")
            cursor.execute("ALTER TABLE budget_months ADD COLUMN assigned_overridden BOOLEAN DEFAULT 0")
            # Backfill: marcar como overridden solo los meses donde el assigned difiere del mes anterior
            # (o donde no hay mes anterior). Si el assigned coincide con el mes anterior, probablemente
            # fue heredado automaticamente y NO debe bloquear el cascade.
            cursor.execute("""
                UPDATE budget_months SET assigned_overridden = 1
                WHERE assigned != 0.0
                AND NOT EXISTS (
                    SELECT 1 FROM budget_months prev
                    WHERE prev.category_id = budget_months.category_id
                    AND prev.currency_id = budget_months.currency_id
                    AND prev.month = date(budget_months.month, '-1 month')
                    AND prev.assigned = budget_months.assigned
                )
            """)
            conn.commit()
            print("✅ Columna agregada y backfill completado")

        if 'initial_amount' in budget_columns:
            print("✓ La columna 'initial_amount' ya existe en budget_months")
        else:
            print("🔧 Agregando columna 'initial_amount' a la tabla budget_months...")
            cursor.execute("ALTER TABLE budget_months ADD COLUMN initial_amount FLOAT DEFAULT 0.0")
            conn.commit()
            print("✅ Columna agregada exitosamente en budget_months")

            # Backfill: for accumulate categories, set initial_amount from previous month's available
            print("🔧 Rellenando initial_amount en budget_months para categorías de ahorro...")
            cursor.execute("""
                UPDATE budget_months SET initial_amount = (
                    SELECT prev.available
                    FROM budget_months prev
                    JOIN categories c ON c.id = budget_months.category_id
                    WHERE c.rollover_type = 'accumulate'
                    AND prev.category_id = budget_months.category_id
                    AND prev.currency_id = budget_months.currency_id
                    AND prev.month = date(budget_months.month, '-1 month')
                )
                WHERE EXISTS (
                    SELECT 1 FROM categories c2
                    WHERE c2.id = budget_months.category_id AND c2.rollover_type = 'accumulate'
                )
                AND (
                    SELECT prev2.available FROM budget_months prev2
                    WHERE prev2.category_id = budget_months.category_id
                    AND prev2.currency_id = budget_months.currency_id
                    AND prev2.month = date(budget_months.month, '-1 month')
                ) IS NOT NULL
            """)
            conn.commit()

            # For accumulate categories with no previous month, use category.initial_amount
            cursor.execute("""
                UPDATE budget_months SET initial_amount = (
                    SELECT c.initial_amount FROM categories c
                    WHERE c.id = budget_months.category_id AND c.rollover_type = 'accumulate'
                )
                WHERE initial_amount = 0.0
                AND EXISTS (
                    SELECT 1 FROM categories c2
                    WHERE c2.id = budget_months.category_id AND c2.rollover_type = 'accumulate'
                    AND c2.initial_amount > 0
                )
                AND NOT EXISTS (
                    SELECT 1 FROM budget_months prev
                    WHERE prev.category_id = budget_months.category_id
                    AND prev.currency_id = budget_months.currency_id
                    AND prev.month < budget_months.month
                )
            """)
            conn.commit()
            print("✅ Backfill completado")

        conn.close()
        print("\n✓ Migración completada. Ahora puedes ejecutar 'python init_db.py'")

    except Exception as e:
        print(f"❌ Error al migrar la base de datos: {e}")
        sys.exit(1)

def migrate_all_databases():
    """Migrate all databases found in the data directory."""
    dbs = _find_all_databases()
    if not dbs:
        print(f"❌ No se encontraron bases de datos en {DATABASE_DIR}")
        sys.exit(1)
    print(f"Se encontraron {len(dbs)} base(s) de datos: {', '.join(p.name for p in dbs)}")
    for db_path in dbs:
        migrate_database(db_path)
    print("\n✓ Todas las migraciones completadas.")


if __name__ == "__main__":
    print("=" * 60)
    print("MIGRACIÓN DE BASE DE DATOS")
    print("=" * 60)
    print("\nEsta migración agregará columnas nuevas a categories, accounts y recurring_transactions")

    response = input("\n¿Continuar? (s/n): ")
    if response.lower() == 's':
        migrate_all_databases()
    else:
        print("❌ Migración cancelada")
