from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from config import SQLALCHEMY_DATABASE_URI
from pathlib import Path

# Ensure data directory exists
Path(SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')).parent.mkdir(parents=True, exist_ok=True)

# Create SQLAlchemy engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URI,
    connect_args={"check_same_thread": False}  # Needed for SQLite
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI to get database session
    Usage:
        @app.get("/")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database - create all tables"""
    # Import all models here to ensure they're registered
    from backend.models import (
        Currency, Account, CategoryGroup, Category,
        Payee, Transaction, BudgetMonth, RecurringTransaction, ExchangeRate,
        Debt, DebtPayment, YnabCategoryMapping
    )

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_column(
        table_name="recurring_transactions",
        column_name="transaction_type",
        column_definition="transaction_type VARCHAR(20) DEFAULT 'expense'"
    )
    ensure_sqlite_column(
        table_name="categories",
        column_name="is_essential",
        column_definition="is_essential BOOLEAN DEFAULT 0"
    )
    ensure_sqlite_column(
        table_name="categories",
        column_name="is_emergency_fund",
        column_definition="is_emergency_fund BOOLEAN DEFAULT 0"
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="is_adjustment",
        column_definition="is_adjustment BOOLEAN DEFAULT 0"
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="original_amount",
        column_definition="original_amount FLOAT DEFAULT 0"
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="original_currency_id",
        column_definition="original_currency_id INTEGER"
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="fx_rate",
        column_definition="fx_rate FLOAT"
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="base_amount",
        column_definition="base_amount FLOAT"
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="base_currency_id",
        column_definition="base_currency_id INTEGER"
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="loan_years",
        column_definition="loan_years INTEGER"
    )
    print("✓ Database tables created")


def ensure_sqlite_column(table_name: str, column_name: str, column_definition: str) -> None:
    if engine.url.drivername != "sqlite":
        return

    with engine.connect() as connection:
        columns = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        if not columns:
            return
        column_names = {row[1] for row in columns}
        if column_name in column_names:
            return
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"))
        connection.commit()
