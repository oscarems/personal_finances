"""
Budget CSV Importer
Handles the budget CSV export format with columns:
Account, Flag, Date, Payee, Category, Memo, Outflow, Inflow, Cleared
"""
import pandas as pd
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session

from finance_app.models import Account, Category, CategoryGroup, Payee, Transaction, Currency
from finance_app.services.transaction_service import build_transaction_audit_fields


def parse_ynab_date(date_str):
    """
    Parse CSV date string (handle various formats and ######).
    Priority order: DD/MM/YYYY (most common CSV export format).
    """
    if not date_str or date_str == '########' or pd.isna(date_str):
        return None

    try:
        # Convert to string and strip whitespace
        date_str = str(date_str).strip()

        # Remove 'nan' strings
        if date_str.lower() == 'nan':
            return None

        # Try common date formats - DD/MM/YYYY FIRST (CSV export format)
        formats = [
            '%d/%m/%Y',      # 15/01/2024 (default CSV format)
            '%d-%m-%Y',      # 15-01-2024
            '%d.%m.%Y',      # 15.01.2024
            '%d/%m/%y',      # 15/01/24
            '%m/%d/%Y',      # 01/15/2024 (US format)
            '%Y-%m-%d',      # 2024-01-15 (ISO format)
            '%Y/%m/%d',      # 2024/01/15
            '%m-%d-%Y',      # 01-15-2024
            '%m/%d/%y',      # 01/15/24
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        # If all formats fail, log the problematic date for debugging
        print(f"⚠️  Could not parse date: '{date_str}'")
        return None
    except Exception as e:
        print(f"⚠️  Error parsing date '{date_str}': {str(e)}")
        return None


def parse_amount(amount_str):
    """Parse amount string (handle $, commas, etc.)"""
    if not amount_str or pd.isna(amount_str):
        return 0.0

    # Remove currency symbols and commas
    amount_str = str(amount_str).replace('$', '').replace(',', '').strip()

    try:
        return float(amount_str)
    except ValueError:
        return 0.0


def parse_category(category_str):
    """
    Parse CSV category format: "Group: Category".
    Returns tuple (group_name, category_name).
    """
    if not category_str or pd.isna(category_str):
        return None, None

    category_str = str(category_str).strip()

    # Check if it's a transfer
    if category_str.startswith('Transfer:'):
        # This is a transfer, not a regular category
        return 'Transfer', category_str.replace('Transfer:', '').strip()

    # Split by colon
    if ':' in category_str:
        parts = category_str.split(':', 1)
        group_name = parts[0].strip()
        category_name = parts[1].strip()
        return group_name, category_name

    # No group specified, use category as is
    return None, category_str


def get_or_create_category(db: Session, group_name: str, category_name: str, is_transfer: bool = False):
    """
    Get or create a category from a CSV import.
    Returns category_id or None.
    """
    if is_transfer:
        # Skip transfers for now, or handle specially
        return None

    if not category_name:
        return None

    # Try to find exact match first
    category = db.query(Category).join(CategoryGroup).filter(
        Category.name.ilike(f"%{category_name}%")
    ).first()

    if category:
        return category.id

    # If not found, try to map to existing categories
    # Create mapping for common CSV categories -> our categories
    category_mapping = {
        'gym': 'Entretenimiento',
        'administracion': 'Vivienda',
        'hipoteca': 'Hipoteca',
        'deuda': 'Préstamos',
        'prepagada': 'Servicios Públicos',
        'pension': 'Ahorros',
        'eps': 'Salud',
        'caja compensacion': 'Salud',
    }

    # Try mapping
    category_lower = category_name.lower()
    for key, mapped_name in category_mapping.items():
        if key in category_lower:
            category = db.query(Category).filter_by(name=mapped_name).first()
            if category:
                return category.id

    # If still not found, create new category in appropriate group
    # Determine group based on category name or provided group_name
    if group_name:
        group = db.query(CategoryGroup).filter_by(name=group_name).first()
        if not group:
            # Create new group
            group = CategoryGroup(
                name=group_name,
                sort_order=100,
                is_income=False
            )
            db.add(group)
            db.flush()
    else:
        # Use default group "Gastos Discrecionales"
        group = db.query(CategoryGroup).filter(
            CategoryGroup.name.like('%Discrecional%')
        ).first()

        if not group:
            group = db.query(CategoryGroup).first()  # Fallback to first group

    # Create new category
    new_category = Category(
        category_group_id=group.id,
        name=category_name,
        sort_order=999
    )
    db.add(new_category)
    db.flush()

    return new_category.id


def get_or_create_account(db: Session, account_name: str, default_currency_id: int):
    """Get or create an account from a CSV import."""
    if not account_name or pd.isna(account_name):
        return None

    account = db.query(Account).filter(
        Account.name.ilike(f"%{account_name}%")
    ).first()

    if account:
        return account.id

    # Create new account
    new_account = Account(
        name=account_name,
        type='checking',  # Default type
        currency_id=default_currency_id,
        balance=0.0,
        is_budget=True
    )
    db.add(new_account)
    db.flush()

    return new_account.id


def import_ynab_csv(db: Session, csv_file_path: str, default_currency_code: str = 'COP'):
    """
    Import a budget CSV file.
    Returns a dict with import statistics.
    """
    stats = {
        'total_rows': 0,
        'imported': 0,
        'skipped': 0,
        'errors': []
    }

    # Get default currency
    currency = db.query(Currency).filter_by(code=default_currency_code).first()
    if not currency:
        stats['errors'].append(f"Currency {default_currency_code} not found")
        return stats

    try:
        # Read CSV - IMPORTANT: Don't let pandas parse dates automatically
        df = pd.read_csv(csv_file_path, dtype={'Date': str})
        stats['total_rows'] = len(df)

        print(f"📂 Importing {stats['total_rows']} transactions from CSV...")
        print(f"   CSV columns: {list(df.columns)}")

        # Show first date as example
        if len(df) > 0:
            first_date = df.iloc[0].get('Date')
            print(f"   Example date format: '{first_date}'")

        for idx, row in df.iterrows():
            try:
                # Parse date
                transaction_date = parse_ynab_date(row.get('Date'))
                if not transaction_date:
                    stats['skipped'] += 1
                    stats['errors'].append(f"Row {idx + 2}: Invalid date")
                    continue

                # Parse amounts (Outflow is negative, Inflow is positive)
                outflow = parse_amount(row.get('Outflow', 0))
                inflow = parse_amount(row.get('Inflow', 0))

                # Net amount: inflow is positive, outflow is negative
                amount = inflow - outflow

                if amount == 0:
                    stats['skipped'] += 1
                    continue

                # Get or create account
                account_name = row.get('Account')
                account_id = get_or_create_account(db, account_name, currency.id)

                if not account_id:
                    stats['skipped'] += 1
                    stats['errors'].append(f"Row {idx + 2}: No account specified")
                    continue

                # Get or create payee
                payee_name = row.get('Payee')
                payee_id = None
                if payee_name and not pd.isna(payee_name):
                    payee = db.query(Payee).filter_by(name=payee_name).first()
                    if not payee:
                        payee = Payee(name=payee_name)
                        db.add(payee)
                        db.flush()
                    payee_id = payee.id

                # Parse category
                category_str = row.get('Category')
                group_name, category_name = parse_category(category_str)
                is_transfer = (group_name == 'Transfer')

                category_id = get_or_create_category(
                    db,
                    group_name,
                    category_name,
                    is_transfer
                )

                # Get memo
                memo = row.get('Memo', '')
                if pd.isna(memo):
                    memo = ''

                # Parse cleared status
                cleared_str = row.get('Cleared', 'Uncleared')
                cleared = (str(cleared_str).lower() == 'cleared')

                # Create import_id to avoid duplicates
                import_id = f"csv_{account_name}_{transaction_date}_{amount}_{payee_name}"

                # Check if already imported
                existing = db.query(Transaction).filter_by(import_id=import_id).first()
                if existing:
                    stats['skipped'] += 1
                    continue

                base_amount, base_currency_id = build_transaction_audit_fields(
                    db,
                    amount,
                    currency.id,
                    transaction_date
                )
                # Create transaction
                transaction = Transaction(
                    account_id=account_id,
                    date=transaction_date,
                    payee_id=payee_id,
                    category_id=category_id,
                    memo=memo,
                    amount=amount,
                    currency_id=currency.id,
                    original_amount=amount,
                    original_currency_id=currency.id,
                    fx_rate=None,
                    base_amount=base_amount,
                    base_currency_id=base_currency_id,
                    cleared=cleared,
                    import_id=import_id
                )

                db.add(transaction)

                # Update account balance
                account = db.query(Account).get(account_id)
                if account:
                    account.balance += amount

                stats['imported'] += 1

                # Commit in batches
                if stats['imported'] % 50 == 0:
                    db.commit()
                    print(f"  ✓ Imported {stats['imported']} transactions...")

            except Exception as e:
                stats['errors'].append(f"Row {idx + 2}: {str(e)}")
                stats['skipped'] += 1
                continue

        # Final commit
        db.commit()

        print(f"\n✅ Import complete!")
        print(f"   Total rows: {stats['total_rows']}")
        print(f"   Imported: {stats['imported']}")
        print(f"   Skipped: {stats['skipped']}")

        if stats['errors']:
            print(f"\n⚠️  Errors: {len(stats['errors'])}")
            for error in stats['errors'][:10]:  # Show first 10 errors
                print(f"   - {error}")

    except Exception as e:
        stats['errors'].append(f"File read error: {str(e)}")
        print(f"❌ Error reading CSV: {str(e)}")

    return stats
