#!/usr/bin/env python3
"""
YNAB Import Script
==================
Standalone script to import YNAB CSV export into the database.

Usage:
    python import_ynab.py <path_to_ynab_csv> [currency_code]

Example:
    python import_ynab.py ~/Downloads/ynab_export.csv COP
    python import_ynab.py ./transactions.csv USD

CSV Format:
    Your YNAB CSV should have these columns:
    Account, Flag, Date, Payee, Category, Memo, Outflow, Inflow, Cleared

Notes:
    - This will automatically create missing accounts and categories
    - Duplicate transactions (same account, date, amount, payee) will be skipped
    - Transactions will be imported with the specified currency (default: COP)
    - Account balances will be updated based on imported transactions
"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.database import SessionLocal
from backend.utils.ynab_importer import import_ynab_csv


def main():
    # Parse arguments
    if len(sys.argv) < 2:
        print("❌ Error: CSV file path required")
        print("\nUsage:")
        print("  python import_ynab.py <path_to_csv> [currency_code]")
        print("\nExample:")
        print("  python import_ynab.py ~/Downloads/ynab_export.csv COP")
        sys.exit(1)

    csv_file_path = sys.argv[1]
    currency_code = sys.argv[2] if len(sys.argv) > 2 else 'COP'

    # Validate file exists
    if not os.path.exists(csv_file_path):
        print(f"❌ Error: File not found: {csv_file_path}")
        sys.exit(1)

    print("=" * 60)
    print("🔄 YNAB IMPORT")
    print("=" * 60)
    print(f"📁 File: {csv_file_path}")
    print(f"💰 Currency: {currency_code}")
    print("=" * 60)
    print()

    # Confirm before importing
    response = input("Continue with import? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print("Import cancelled.")
        sys.exit(0)

    print()

    # Create database session
    db = SessionLocal()

    try:
        # Import CSV
        stats = import_ynab_csv(db, csv_file_path, currency_code)

        print()
        print("=" * 60)
        print("📊 IMPORT SUMMARY")
        print("=" * 60)
        print(f"Total rows processed: {stats['total_rows']}")
        print(f"✅ Successfully imported: {stats['imported']}")
        print(f"⏭️  Skipped: {stats['skipped']}")

        if stats['errors']:
            print(f"\n⚠️  Errors encountered: {len(stats['errors'])}")
            print("\nFirst 10 errors:")
            for error in stats['errors'][:10]:
                print(f"  - {error}")

        print("=" * 60)
        print()

        if stats['imported'] > 0:
            print("✅ Import completed successfully!")
            print()
            print("Next steps:")
            print("  1. Review imported transactions: http://localhost:8000/transactions")
            print("  2. Review accounts: http://localhost:8000/accounts")
            print("  3. Assign categories to uncategorized transactions")
            print("  4. Set up your budget: http://localhost:8000/budget")
        else:
            print("⚠️  No transactions were imported.")
            if stats['errors']:
                print("   Please check the errors above.")

    except Exception as e:
        print(f"❌ Fatal error during import: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    main()
