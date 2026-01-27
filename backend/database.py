from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from config import (
    SQLALCHEMY_DATABASE_URI,
    DEMO_DATABASE_URL,
    DEFAULT_DB_MODE
)
from fastapi import Request

def ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith('sqlite:///'):
        return
    Path(database_url.replace('sqlite:///', '')).parent.mkdir(parents=True, exist_ok=True)


def create_engine_for_url(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith('sqlite:///') else {}
    return create_engine(database_url, connect_args=connect_args)


# Ensure data directories exist
ensure_sqlite_directory(SQLALCHEMY_DATABASE_URI)
ensure_sqlite_directory(DEMO_DATABASE_URL)

# Create SQLAlchemy engines
engine = create_engine_for_url(SQLALCHEMY_DATABASE_URI)
engine_demo = create_engine_for_url(DEMO_DATABASE_URL)

# Create SessionLocal classes
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocalDemo = sessionmaker(autocommit=False, autoflush=False, bind=engine_demo)

# Create Base class for models
Base = declarative_base()


def resolve_db_mode(request: Request) -> str:
    return request.cookies.get("db_mode", DEFAULT_DB_MODE)


def get_db(request: Request):
    """
    Dependency for FastAPI to get database session
    Usage:
        @app.get("/")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    mode = resolve_db_mode(request)
    session_factory = SessionLocalDemo if mode == "demo" else SessionLocal
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def init_db(engine_override=None):
    """Initialize database - create all tables"""
    # Import all models here to ensure they're registered
    from backend.models import (
        Currency, Account, CategoryGroup, Category,
        Payee, Transaction, BudgetMonth, RecurringTransaction, ExchangeRate,
        Debt, DebtPayment, YnabCategoryMapping, AlertRule, ReconciliationSession, WealthAsset
    )

    active_engine = engine_override or engine
    Base.metadata.create_all(bind=active_engine)
    ensure_sqlite_column(
        table_name="recurring_transactions",
        column_name="transaction_type",
        column_definition="transaction_type VARCHAR(20) DEFAULT 'expense'",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="categories",
        column_name="is_essential",
        column_definition="is_essential BOOLEAN DEFAULT 0",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="categories",
        column_name="is_emergency_fund",
        column_definition="is_emergency_fund BOOLEAN DEFAULT 0",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="is_adjustment",
        column_definition="is_adjustment BOOLEAN DEFAULT 0",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="original_amount",
        column_definition="original_amount FLOAT DEFAULT 0",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="original_currency_id",
        column_definition="original_currency_id INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="fx_rate",
        column_definition="fx_rate FLOAT",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="base_amount",
        column_definition="base_amount FLOAT",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="base_currency_id",
        column_definition="base_currency_id INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="loan_years",
        column_definition="loan_years INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="wealth_assets",
        column_name="return_rate",
        column_definition="return_rate FLOAT",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="wealth_assets",
        column_name="return_amount",
        column_definition="return_amount FLOAT",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="wealth_assets",
        column_name="mortgage_debt_id",
        column_definition="mortgage_debt_id INTEGER",
        engine_override=active_engine
    )
    print("✓ Database tables created")


def ensure_sqlite_column(
    table_name: str,
    column_name: str,
    column_definition: str,
    engine_override=None
) -> None:
    active_engine = engine_override or engine
    if active_engine.url.drivername != "sqlite":
        return

    with active_engine.begin() as connection:
        columns = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        if not columns:
            return
        column_names = {row[1] for row in columns}
        if column_name in column_names:
            return
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"))
        # No need for explicit commit() - context manager handles it
