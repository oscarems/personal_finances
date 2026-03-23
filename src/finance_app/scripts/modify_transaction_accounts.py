"""
Script para modificar la cuenta (account_id) de transacciones en bulk.

Uso:
    python -m finance_app.scripts.modify_transaction_accounts

El script:
  1. Muestra las cuentas disponibles
  2. Permite filtrar transacciones por cuenta origen, rango de fechas, payee o memo
  3. Muestra las transacciones que coinciden para revisión
  4. Pide la cuenta destino
  5. Actualiza account_id y recalcula balances de ambas cuentas
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime
from sqlalchemy import and_
from finance_app.database import get_engine_for_name, get_session_factory, ensure_database_initialized
from finance_app.models import Transaction, Account, Payee


def get_db_name():
    print("\n=== Bases de datos disponibles ===")
    from finance_app.database import list_databases
    dbs = list_databases()
    for i, db in enumerate(dbs, 1):
        status = "✓" if db["exists"] else "✗"
        print(f"  {i}. [{status}] {db['name']} ({db['label']})")
    choice = input("\nNombre de la base de datos (default: primary): ").strip() or "primary"
    return choice


def show_accounts(session):
    accounts = session.query(Account).order_by(Account.name).all()
    print("\n=== Cuentas disponibles ===")
    for acc in accounts:
        currency_code = acc.currency.code if acc.currency else "?"
        print(f"  ID {acc.id:3d} | {acc.name:<30s} | {acc.type:<15s} | Balance: {acc.balance:>15,.2f} {currency_code}")
    return {acc.id: acc for acc in accounts}


def filter_transactions(session, accounts_map):
    print("\n=== Filtrar transacciones ===")

    # Cuenta origen
    source_input = input("ID de cuenta origen (Enter = todas): ").strip()
    source_account_id = int(source_input) if source_input else None
    if source_account_id and source_account_id not in accounts_map:
        print(f"Error: cuenta {source_account_id} no existe.")
        return []

    # Rango de fechas
    date_from_str = input("Fecha desde (YYYY-MM-DD, Enter = sin límite): ").strip()
    date_to_str = input("Fecha hasta (YYYY-MM-DD, Enter = sin límite): ").strip()
    date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date() if date_from_str else None
    date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date() if date_to_str else None

    # Payee
    payee_filter = input("Filtrar por payee (texto parcial, Enter = sin filtro): ").strip()

    # Memo
    memo_filter = input("Filtrar por memo (texto parcial, Enter = sin filtro): ").strip()

    # Build query
    query = session.query(Transaction)
    if source_account_id:
        query = query.filter(Transaction.account_id == source_account_id)
    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)
    if payee_filter:
        query = query.join(Payee, Transaction.payee_id == Payee.id).filter(
            Payee.name.ilike(f"%{payee_filter}%")
        )
    if memo_filter:
        query = query.filter(Transaction.memo.ilike(f"%{memo_filter}%"))

    transactions = query.order_by(Transaction.date.desc()).all()
    return transactions


def display_transactions(transactions, accounts_map):
    if not transactions:
        print("\nNo se encontraron transacciones con esos filtros.")
        return

    print(f"\n=== {len(transactions)} transacciones encontradas ===")
    print(f"  {'#':>4s} | {'ID':>6s} | {'Fecha':<12s} | {'Cuenta':<25s} | {'Payee':<25s} | {'Monto':>15s} | {'Memo'}")
    print("  " + "-" * 120)
    for i, t in enumerate(transactions, 1):
        acc_name = accounts_map.get(t.account_id, None)
        acc_name = acc_name.name if acc_name else f"ID:{t.account_id}"
        payee_name = t.payee.name if t.payee else ""
        memo = (t.memo or "")[:40]
        print(f"  {i:4d} | {t.id:6d} | {t.date} | {acc_name:<25s} | {payee_name:<25s} | {t.amount:>15,.2f} | {memo}")


def select_transactions(transactions):
    print("\n¿Cuáles transacciones quieres modificar?")
    print("  - 'todas' para seleccionar todas")
    print("  - Números separados por coma (ej: 1,3,5-10)")
    print("  - 'cancelar' para salir")

    choice = input("\nSelección: ").strip().lower()
    if choice == "cancelar":
        return []
    if choice == "todas":
        return list(transactions)

    selected = []
    for part in choice.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            for idx in range(int(start), int(end) + 1):
                if 1 <= idx <= len(transactions):
                    selected.append(transactions[idx - 1])
        else:
            idx = int(part)
            if 1 <= idx <= len(transactions):
                selected.append(transactions[idx - 1])
    return selected


def update_account(session, selected_transactions, accounts_map):
    target_input = input("\nID de la cuenta destino: ").strip()
    if not target_input:
        print("Cancelado.")
        return False

    target_account_id = int(target_input)
    if target_account_id not in accounts_map:
        print(f"Error: cuenta {target_account_id} no existe.")
        return False

    target_account = accounts_map[target_account_id]
    print(f"\nSe moverán {len(selected_transactions)} transacciones a: {target_account.name}")
    confirm = input("¿Confirmar? (s/n): ").strip().lower()
    if confirm != "s":
        print("Cancelado.")
        return False

    # Track balance changes per account
    balance_changes = {}  # account_id -> delta

    for t in selected_transactions:
        old_account_id = t.account_id
        if old_account_id == target_account_id:
            continue

        # Subtract from old account, add to new
        balance_changes[old_account_id] = balance_changes.get(old_account_id, 0) - t.amount
        balance_changes[target_account_id] = balance_changes.get(target_account_id, 0) + t.amount

        t.account_id = target_account_id

    # Apply balance changes
    for acc_id, delta in balance_changes.items():
        acc = accounts_map[acc_id]
        old_balance = acc.balance
        acc.balance = (acc.balance or 0) + delta
        print(f"  Cuenta '{acc.name}': {old_balance:,.2f} -> {acc.balance:,.2f}")

    session.commit()
    print(f"\n✓ {len(selected_transactions)} transacciones actualizadas correctamente.")
    return True


def main():
    db_name = get_db_name()
    ensure_database_initialized(db_name)
    session_factory = get_session_factory(db_name)
    session = session_factory()

    try:
        accounts_map = show_accounts(session)
        transactions = filter_transactions(session, accounts_map)
        display_transactions(transactions, accounts_map)

        if not transactions:
            return

        selected = select_transactions(transactions)
        if not selected:
            print("No se seleccionaron transacciones.")
            return

        print(f"\n{len(selected)} transacciones seleccionadas.")
        update_account(session, selected, accounts_map)

    except KeyboardInterrupt:
        print("\n\nCancelado por el usuario.")
    except Exception as e:
        session.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
