#!/usr/bin/env python3
"""
Script to reset the database.
Deletes all transactions, categories, budgets and resets account balances to 0.
"""

from finance_app.database import SessionLocal, engine, Base
from finance_app.models import (
    Transaction, Category, CategoryGroup, BudgetMonth,
    RecurringTransaction, Account, Payee, ExchangeRate,
    Debt, DebtPayment, DebtAmortizationMonthly
)
from sqlalchemy import text
import sys


def reset_database(keep_accounts=True, keep_categories=True):
    """
    Reset the database by deleting selected data.

    Args:
        keep_accounts: If True, keeps accounts but resets their balances to 0.
        keep_categories: If True, keeps categories and category groups.
    """
    db = SessionLocal()

    try:
        print("🔄 Iniciando reinicio de base de datos...")

        # 1. Eliminar todas las transacciones
        print("  → Eliminando transacciones...")
        deleted_transactions = db.query(Transaction).delete()
        db.commit()
        print(f"    ✓ {deleted_transactions} transacciones eliminadas")

        # 2. Eliminar todas las transacciones recurrentes
        print("  → Eliminando transacciones recurrentes...")
        deleted_recurring = db.query(RecurringTransaction).delete()
        db.commit()
        print(f"    ✓ {deleted_recurring} transacciones recurrentes eliminadas")

        # 3. Eliminar todos los presupuestos
        print("  → Eliminando presupuestos...")
        deleted_budgets = db.query(BudgetMonth).delete()
        db.commit()
        print(f"    ✓ {deleted_budgets} presupuestos eliminados")

        # 4. Eliminar payees
        print("  → Eliminando payees...")
        deleted_payees = db.query(Payee).delete()
        db.commit()
        print(f"    ✓ {deleted_payees} payees eliminados")

        # 5. Eliminar pagos de deudas y deudas
        print("  → Eliminando pagos de deudas...")
        deleted_debt_payments = db.query(DebtPayment).delete()
        db.commit()
        print(f"    ✓ {deleted_debt_payments} pagos de deudas eliminados")

        print("  → Eliminando amortizaciones de deudas...")
        deleted_debt_amortizations = db.query(DebtAmortizationMonthly).delete()
        db.commit()
        print(f"    ✓ {deleted_debt_amortizations} amortizaciones eliminadas")

        print("  → Eliminando deudas...")
        deleted_debts = db.query(Debt).delete()
        db.commit()
        print(f"    ✓ {deleted_debts} deudas eliminadas")

        # 6. Resetear balances de cuentas o eliminarlas
        if keep_accounts:
            print("  → Reseteando balances de cuentas a 0...")
            accounts = db.query(Account).all()
            for account in accounts:
                account.balance = 0
            db.commit()
            print(f"    ✓ {len(accounts)} cuentas reseteadas a balance 0")
        else:
            print("  → Eliminando todas las cuentas...")
            deleted_accounts = db.query(Account).delete()
            db.commit()
            print(f"    ✓ {deleted_accounts} cuentas eliminadas")

        # 7. Eliminar categorías y grupos si se solicita
        if not keep_categories:
            print("  → Eliminando categorías...")
            deleted_categories = db.query(Category).delete()
            db.commit()
            print(f"    ✓ {deleted_categories} categorías eliminadas")

            print("  → Eliminando grupos de categorías...")
            deleted_groups = db.query(CategoryGroup).delete()
            db.commit()
            print(f"    ✓ {deleted_groups} grupos de categorías eliminados")
        else:
            print("  → Manteniendo categorías y grupos de categorías")

        # 8. Opcional: Limpiar tasas de cambio antiguas (mantener solo las más recientes)
        print("  → Limpiando tasas de cambio antiguas...")
        # Mantener solo las tasas de cambio de los últimos 30 días
        db.execute(text("""
            DELETE FROM exchange_rates
            WHERE date < date('now', '-30 days')
        """))
        db.commit()
        print("    ✓ Tasas de cambio antiguas eliminadas")

        # 9. Resetear secuencias de IDs de SQLite
        print("  → Reseteando secuencias de IDs...")
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='transactions'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='recurring_transactions'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='budget_months'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='payees'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='debts'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='debt_payments'"))
        db.execute(text("DELETE FROM sqlite_sequence WHERE name='debt_amortization_monthly'"))
        if not keep_accounts:
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='accounts'"))
        if not keep_categories:
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='categories'"))
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='category_groups'"))
        db.commit()
        print("    ✓ Secuencias de IDs reseteadas")

        print("\n✅ Base de datos reiniciada exitosamente!")
        print("\n📊 Resumen:")
        print(f"  • Transacciones eliminadas: {deleted_transactions}")
        print(f"  • Transacciones recurrentes eliminadas: {deleted_recurring}")
        print(f"  • Presupuestos eliminados: {deleted_budgets}")
        print(f"  • Payees eliminados: {deleted_payees}")
        print(f"  • Deudas eliminadas: {deleted_debts}")
        print(f"  • Pagos de deudas eliminados: {deleted_debt_payments}")
        print(f"  • Amortizaciones de deudas eliminadas: {deleted_debt_amortizations}")
        if keep_accounts:
            print(f"  • Cuentas reseteadas: {len(accounts)}")
        else:
            print(f"  • Cuentas eliminadas: {deleted_accounts}")
        if not keep_categories:
            print(f"  • Categorías eliminadas: {deleted_categories}")
            print(f"  • Grupos eliminados: {deleted_groups}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error al reiniciar la base de datos: {e}")
        sys.exit(1)
    finally:
        db.close()


def full_reset():
    """
    Full reset: deletes EVERYTHING including accounts and categories.
    """
    print("\n⚠️  ATENCIÓN: Esto eliminará TODOS los datos de la base de datos")
    print("   Incluyendo: transacciones, cuentas, categorías, presupuestos, etc.")
    confirm = input("\n¿Estás seguro? Escribe 'SI ELIMINAR TODO' para confirmar: ")

    if confirm == "SI ELIMINAR TODO":
        reset_database(keep_accounts=False, keep_categories=False)
    else:
        print("❌ Operación cancelada")


def soft_reset():
    """
    Soft reset: keeps accounts and categories, only deletes transactions and budgets.
    """
    print("\n⚠️  Esto eliminará transacciones, presupuestos y reseteará balances a 0")
    print("   Se mantendrán: cuentas, categorías y grupos de categorías")
    confirm = input("\n¿Continuar? (s/n): ")

    if confirm.lower() == 's':
        reset_database(keep_accounts=True, keep_categories=True)
    else:
        print("❌ Operación cancelada")


if __name__ == "__main__":
    print("=" * 60)
    print("REINICIAR BASE DE DATOS - Sistema de Finanzas Personales")
    print("=" * 60)
    print("\nOpciones:")
    print("  1. Reinicio SUAVE (recomendado)")
    print("     → Elimina transacciones, presupuestos, payees")
    print("     → Resetea balances de cuentas a 0")
    print("     → MANTIENE: cuentas y categorías")
    print()
    print("  2. Reinicio COMPLETO")
    print("     → Elimina TODO (transacciones, cuentas, categorías, etc.)")
    print()

    choice = input("Selecciona una opción (1/2): ")

    if choice == "1":
        soft_reset()
    elif choice == "2":
        full_reset()
    else:
        print("❌ Opción inválida")
        sys.exit(1)
