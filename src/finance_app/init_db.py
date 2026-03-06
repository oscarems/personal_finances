"""
Database initialization script with seed data
"""
from datetime import date, timedelta
from finance_app.database import SessionLocal, init_db as create_tables
from finance_app.models import (
    Currency, Account, CategoryGroup, Category,
    Payee, Transaction, BudgetMonth, RecurringTransaction, WealthAsset
)
from finance_app.services.transaction_service import build_transaction_audit_fields
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


def init_demo_data(db_session):
    """Initialize demo data with non-zero values for key entities."""
    print("Creating demo data...")

    cop_currency = db_session.query(Currency).filter_by(code='COP').first()
    usd_currency = db_session.query(Currency).filter_by(code='USD').first()

    account_cop = db_session.query(Account).filter_by(name='Cuenta Corriente COP').first()
    account_usd = db_session.query(Account).filter_by(name='Ahorros USD').first()
    if not account_cop or not account_usd:
        init_sample_accounts(db_session)
        account_cop = db_session.query(Account).filter_by(name='Cuenta Corriente COP').first()
        account_usd = db_session.query(Account).filter_by(name='Ahorros USD').first()

    if account_cop:
        account_cop.balance = 3250000.0
    if account_usd:
        account_usd.balance = 850.0
    db_session.commit()

    payee_names = ['Empresa ABC', 'Supermercado', 'Netflix', 'PayPal', 'Arrendador']
    for name in payee_names:
        if not db_session.query(Payee).filter_by(name=name).first():
            db_session.add(Payee(name=name))
    db_session.commit()

    if db_session.query(BudgetMonth).count() == 0:
        month_start = date.today().replace(day=1)
        budget_targets = [
            ('Mercado', 600000.0, -250000.0),
            ('Arriendo / Hipoteca', 1400000.0, -1400000.0),
            ('Suscripciones', 45000.0, -45000.0),
        ]
        for category_name, assigned, activity in budget_targets:
            category = db_session.query(Category).filter_by(name=category_name).first()
            if not category or not cop_currency:
                continue
            available = assigned + activity
            db_session.add(BudgetMonth(
                month=month_start,
                category_id=category.id,
                currency_id=cop_currency.id,
                assigned=assigned,
                activity=activity,
                available=available,
                notes="Presupuesto demo"
            ))
        db_session.commit()

    if db_session.query(Transaction).count() == 0:
        payee_empresa = db_session.query(Payee).filter_by(name='Empresa ABC').first()
        payee_super = db_session.query(Payee).filter_by(name='Supermercado').first()
        payee_netflix = db_session.query(Payee).filter_by(name='Netflix').first()
        payee_paypal = db_session.query(Payee).filter_by(name='PayPal').first()

        category_salary = db_session.query(Category).filter_by(name='Salario').first()
        category_market = db_session.query(Category).filter_by(name='Mercado').first()
        category_netflix = db_session.query(Category).filter_by(name='Suscripciones').first()

        today = date.today()
        transactions = []

        if account_cop and cop_currency:
            transactions.extend([
                {
                    'account': account_cop,
                    'date': today - timedelta(days=20),
                    'payee': payee_empresa,
                    'category': category_salary,
                    'amount': 5200000.0,
                    'currency': cop_currency,
                    'memo': 'Salario mensual'
                },
                {
                    'account': account_cop,
                    'date': today - timedelta(days=8),
                    'payee': payee_super,
                    'category': category_market,
                    'amount': -320000.0,
                    'currency': cop_currency,
                    'memo': 'Mercado semanal'
                },
                {
                    'account': account_cop,
                    'date': today - timedelta(days=4),
                    'payee': payee_netflix,
                    'category': category_netflix,
                    'amount': -45000.0,
                    'currency': cop_currency,
                    'memo': 'Suscripción Netflix'
                }
            ])

        if account_usd and usd_currency:
            transactions.extend([
                {
                    'account': account_usd,
                    'date': today - timedelta(days=12),
                    'payee': payee_paypal,
                    'category': None,
                    'amount': 200.0,
                    'currency': usd_currency,
                    'memo': 'Ingreso PayPal'
                },
                {
                    'account': account_usd,
                    'date': today - timedelta(days=2),
                    'payee': payee_netflix,
                    'category': category_netflix,
                    'amount': -35.0,
                    'currency': usd_currency,
                    'memo': 'Netflix USD'
                }
            ])

        for entry in transactions:
            base_amount, base_currency_id = build_transaction_audit_fields(
                db_session,
                entry['amount'],
                entry['currency'].id,
                entry['date']
            )
            db_session.add(Transaction(
                account_id=entry['account'].id,
                date=entry['date'],
                payee_id=entry['payee'].id if entry['payee'] else None,
                category_id=entry['category'].id if entry['category'] else None,
                memo=entry['memo'],
                amount=entry['amount'],
                currency_id=entry['currency'].id,
                original_amount=entry['amount'],
                original_currency_id=entry['currency'].id,
                fx_rate=None,
                base_amount=base_amount,
                base_currency_id=base_currency_id,
                cleared=False,
                approved=True
            ))
        db_session.commit()

    if db_session.query(RecurringTransaction).count() == 0:
        category_rent = db_session.query(Category).filter_by(name='Arriendo / Hipoteca').first()
        payee_landlord = db_session.query(Payee).filter_by(name='Arrendador').first()
        if account_cop and cop_currency:
            db_session.add(RecurringTransaction(
                account_id=account_cop.id,
                payee_id=payee_landlord.id if payee_landlord else None,
                category_id=category_rent.id if category_rent else None,
                description='Pago arriendo',
                amount=1500000.0,
                currency_id=cop_currency.id,
                transaction_type='expense',
                frequency='monthly',
                interval=1,
                start_date=date.today().replace(day=1),
                day_of_month=5,
                is_active=True
            ))
        db_session.commit()

    if db_session.query(WealthAsset).count() == 0:
        if cop_currency:
            db_session.add(WealthAsset(
                name='Apartamento Demo',
                asset_class='inmueble',
                investment_type='Residencial',
                value=450000000.0,
                return_rate=6.0,
                return_amount=27000000.0,
                expected_appreciation_rate=4.0,
                currency_id=cop_currency.id,
                as_of_date=date.today(),
                notes='Activo inmobiliario de demostración'
            ))
        db_session.commit()


def initialize_database(
    create_samples=True,
    create_demo_data=False,
    session_factory=SessionLocal,
    create_tables_func=create_tables
):
    """
    Main initialization function
    Args:
        create_samples: If True, creates sample accounts for testing
    """
    print("\n🔧 Initializing database...")
    print("=" * 50)

    # Create all tables
    create_tables_func()
    print("✓ Database tables created")

    # Get database session
    db_session = session_factory()

    try:
        db_session.query(BudgetMonth).delete()
        db_session.commit()
        # Initialize data
        init_currencies(db_session)
        init_categories(db_session)

        if create_samples:
            init_sample_accounts(db_session)
        if create_demo_data:
            init_demo_data(db_session)

        print("=" * 50)
        print("✅ Database initialization complete!\n")

    finally:
        db_session.close()


if __name__ == '__main__':
    initialize_database(create_samples=True, create_demo_data=False)
