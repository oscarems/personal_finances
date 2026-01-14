"""
Database initialization script with seed data
"""
from datetime import datetime, date
from backend.database import SessionLocal, init_db as create_tables
from backend.models import (
    Currency, Account, CategoryGroup, Category,
    Payee, Transaction, BudgetMonth, ExchangeRate
)
from config import (
    DEFAULT_EXCHANGE_RATES,
    SUPPORTED_CURRENCIES,
    DEFAULT_CATEGORY_GROUPS
)


def init_currencies(db_session):
    """Initialize default currencies (COP & USD)"""
    print("Creating currencies...")

    for code, rate in DEFAULT_EXCHANGE_RATES.items():
        currency_config = SUPPORTED_CURRENCIES[code]

        currency = db_session.query(Currency).filter_by(code=code).first()
        if not currency:
            currency = Currency(
                code=code,
                symbol=currency_config['symbol'],
                name=currency_config['name'],
                exchange_rate_to_base=rate,
                is_base=(code == 'COP'),
                decimals=currency_config['decimals']
            )
            db_session.add(currency)
            print(f"  ✓ Created currency: {code}")

    db_session.commit()


def init_categories(db_session):
    """Initialize default category groups and categories (YNAB style)"""
    print("Creating categories...")

    for idx, group_data in enumerate(DEFAULT_CATEGORY_GROUPS):
        group = db_session.query(CategoryGroup).filter_by(name=group_data['name']).first()
        if not group:
            group = CategoryGroup(
                name=group_data['name'],
                sort_order=idx,
                is_income=False
            )
            db_session.add(group)
            db_session.commit()
            print(f"  ✓ Created group: {group_data['name']}")

        # Create categories in group
        for cat_idx, cat_data in enumerate(group_data['categories']):
            # Handle both old format (string) and new format (dict)
            if isinstance(cat_data, str):
                cat_name = cat_data
                rollover_type = group_data.get('rollover_type', 'reset')
            else:
                cat_name = cat_data['name']
                rollover_type = cat_data.get('rollover_type', 'reset')

            category = db_session.query(Category).filter_by(
                name=cat_name,
                category_group_id=group.id
            ).first()

            if not category:
                category = Category(
                    category_group_id=group.id,
                    name=cat_name,
                    sort_order=cat_idx,
                    rollover_type=rollover_type
                )
                db_session.add(category)
                rollover_indicator = "🔄" if rollover_type == 'accumulate' else "🔁"
                print(f"    ✓ Created category: {cat_name} {rollover_indicator}")

    # Create Income category group
    income_group = db_session.query(CategoryGroup).filter_by(name='Ingresos').first()
    if not income_group:
        income_group = CategoryGroup(
            name='Ingresos',
            sort_order=999,
            is_income=True
        )
        db_session.add(income_group)
        db_session.commit()
        print(f"  ✓ Created group: Ingresos")

        # Income categories
        income_categories = ['Salario', 'Freelance', 'Inversiones', 'Otros']
        for cat_idx, cat_name in enumerate(income_categories):
            category = Category(
                category_group_id=income_group.id,
                name=cat_name,
                sort_order=cat_idx
            )
            db_session.add(category)
            print(f"    ✓ Created category: {cat_name}")

    db_session.commit()


def init_sample_accounts(db_session):
    """Initialize sample accounts (optional, for testing)"""
    print("Creating sample accounts...")

    cop_currency = db_session.query(Currency).filter_by(code='COP').first()
    usd_currency = db_session.query(Currency).filter_by(code='USD').first()

    sample_accounts = [
        {
            'name': 'Cuenta Corriente COP',
            'type': 'checking',
            'currency': cop_currency,
            'balance': 0.0
        },
        {
            'name': 'Ahorros USD',
            'type': 'savings',
            'currency': usd_currency,
            'balance': 0.0
        }
    ]

    for acc_data in sample_accounts:
        account = db_session.query(Account).filter_by(name=acc_data['name']).first()
        if not account:
            account = Account(
                name=acc_data['name'],
                type=acc_data['type'],
                currency_id=acc_data['currency'].id,
                balance=acc_data['balance'],
                is_budget=True
            )
            db_session.add(account)
            print(f"  ✓ Created account: {acc_data['name']}")

    db_session.commit()


def initialize_database(create_samples=True):
    """
    Main initialization function
    Args:
        create_samples: If True, creates sample accounts for testing
    """
    print("\n🔧 Initializing database...")
    print("=" * 50)

    # Create all tables
    create_tables()
    print("✓ Database tables created")

    # Get database session
    db_session = SessionLocal()

    try:
        # Initialize data
        init_currencies(db_session)
        init_categories(db_session)

        if create_samples:
            init_sample_accounts(db_session)

        print("=" * 50)
        print("✅ Database initialization complete!\n")

    finally:
        db_session.close()


if __name__ == '__main__':
    initialize_database(create_samples=True)
