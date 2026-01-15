#!/usr/bin/env python3
"""
Recurring Transactions Generator
=================================
Standalone script to generate due recurring transactions.

This script should be run daily (e.g., via cron) to automatically
create transactions from recurring rules.

Usage:
    python generate_recurring.py [--date YYYY-MM-DD]

Examples:
    python generate_recurring.py
    python generate_recurring.py --date 2024-12-31

Cron setup (run daily at 1 AM):
    0 1 * * * cd /path/to/personal_finances && python generate_recurring.py
"""

import sys
import argparse
from pathlib import Path
from datetime import date

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.database import SessionLocal
from backend.services.recurring_service import generate_due_transactions


def main():
    parser = argparse.ArgumentParser(
        description='Generate due recurring transactions'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Generate transactions up to this date (YYYY-MM-DD). Default: today'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be generated without creating transactions'
    )

    args = parser.parse_args()

    # Parse target date
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"❌ Invalid date format: {args.date}")
            print("   Use YYYY-MM-DD format")
            sys.exit(1)
    else:
        target_date = date.today()

    print("=" * 60)
    print("🔄 RECURRING TRANSACTIONS GENERATOR")
    print("=" * 60)
    print(f"📅 Target date: {target_date.isoformat()}")
    if args.dry_run:
        print("⚠️  DRY RUN MODE - No transactions will be created")
    print("=" * 60)
    print()

    # Create database session
    db = SessionLocal()

    try:
        if args.dry_run:
            # TODO: Implement dry-run preview
            print("Dry-run preview not yet implemented")
            print("Run without --dry-run to generate transactions")
        else:
            # Generate transactions
            stats = generate_due_transactions(db, target_date)

            print()
            print("=" * 60)
            print("📊 GENERATION SUMMARY")
            print("=" * 60)
            print(f"Recurring rules checked: {stats['checked']}")
            print(f"✅ Transactions generated: {stats['generated']}")
            print(f"⏭️  Skipped: {stats['skipped']}")

            if stats['errors']:
                print(f"\n⚠️  Errors encountered: {len(stats['errors'])}")
                for error in stats['errors']:
                    print(f"  - {error}")

            print("=" * 60)
            print()

            if stats['generated'] > 0:
                print("✅ Generation completed successfully!")
                print(f"   Created {stats['generated']} new transactions")
            elif stats['checked'] == 0:
                print("ℹ️  No active recurring transactions found")
            else:
                print("ℹ️  No transactions were due for generation")

    except Exception as e:
        print(f"❌ Fatal error during generation: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    main()
