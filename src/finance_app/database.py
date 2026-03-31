from pathlib import Path
import re
import threading
import shutil

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from finance_app.config import (
    SQLALCHEMY_DATABASE_URI,
    DEMO_DATABASE_URL,
    DEFAULT_DB_MODE,
    BASE_DIR
)
from fastapi import Request

DEFAULT_DB_NAME = "demo"
PRIMARY_DB_ALIAS = "primary"
DEMO_DB_ALIAS = "demo"
DATABASE_DIRECTORY = BASE_DIR / "data"
_ENGINE_CACHE: dict[str, any] = {}
_SESSION_CACHE: dict[str, sessionmaker] = {}
_INITIALIZED_DATABASES: set[str] = set()
_INIT_LOCK = threading.Lock()


def normalize_db_name(name: str) -> str:
    return name.strip().lower()


def is_valid_db_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name))


def clear_database_cache(name: str) -> None:
    normalized = normalize_db_name(name)
    engine_to_clear = _ENGINE_CACHE.pop(normalized, None)
    if engine_to_clear is not None:
        engine_to_clear.dispose()
    _SESSION_CACHE.pop(normalized, None)
    _INITIALIZED_DATABASES.discard(normalized)


def delete_database(name: str) -> None:
    name = normalize_db_name(name)
    if name in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        raise ValueError("No se puede eliminar la base principal o demo.")
    db_path = database_path_for(name)
    if db_path is None:
        raise ValueError("Solo se pueden eliminar bases SQLite.")
    if not db_path.exists():
        raise FileNotFoundError("La base de datos no existe.")
    clear_database_cache(name)
    db_path.unlink()


def duplicate_database(source: str, target: str) -> None:
    source = normalize_db_name(source)
    target = normalize_db_name(target)
    if source == target:
        raise ValueError("El nombre de la base destino debe ser diferente.")
    source_path = database_path_for(source)
    target_path = database_path_for(target)
    if source_path is None or target_path is None:
        raise ValueError("Solo se pueden duplicar bases SQLite.")
    if not source_path.exists():
        raise FileNotFoundError("La base de origen no existe.")
    if target_path.exists():
        raise FileExistsError("La base destino ya existe.")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    clear_database_cache(target)


def rename_database(source: str, target: str) -> None:
    source = normalize_db_name(source)
    target = normalize_db_name(target)
    if source in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        raise ValueError("No se puede renombrar la base principal o demo.")
    if source == target:
        raise ValueError("El nombre nuevo debe ser diferente.")
    source_path = database_path_for(source)
    target_path = database_path_for(target)
    if source_path is None or target_path is None:
        raise ValueError("Solo se pueden renombrar bases SQLite.")
    if not source_path.exists():
        raise FileNotFoundError("La base de origen no existe.")
    if target_path.exists():
        raise FileExistsError("La base destino ya existe.")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    clear_database_cache(source)
    source_path.rename(target_path)


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
DATABASE_DIRECTORY.mkdir(parents=True, exist_ok=True)

# Create SQLAlchemy engines
engine = create_engine_for_url(SQLALCHEMY_DATABASE_URI)
engine_demo = create_engine_for_url(DEMO_DATABASE_URL)

# Create SessionLocal classes
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocalDemo = sessionmaker(autocommit=False, autoflush=False, bind=engine_demo)

# Create Base class for models
Base = declarative_base()


def resolve_db_name(request: Request) -> str:
    raw_name = request.cookies.get("db_name")
    if raw_name:
        return normalize_db_name(raw_name)
    legacy_mode = request.cookies.get("db_mode", DEFAULT_DB_MODE)
    if legacy_mode in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        return legacy_mode
    return DEFAULT_DB_NAME


def database_path_for(name: str) -> Path | None:
    name = normalize_db_name(name)
    if name == PRIMARY_DB_ALIAS:
        return Path(SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")) if SQLALCHEMY_DATABASE_URI.startswith("sqlite:///") else None
    if name == DEMO_DB_ALIAS:
        return Path(DEMO_DATABASE_URL.replace("sqlite:///", "")) if DEMO_DATABASE_URL.startswith("sqlite:///") else None
    return DATABASE_DIRECTORY / f"{name}.db"


def database_url_for(name: str) -> str:
    name = normalize_db_name(name)
    if name == PRIMARY_DB_ALIAS:
        return SQLALCHEMY_DATABASE_URI
    if name == DEMO_DB_ALIAS:
        return DEMO_DATABASE_URL
    return f"sqlite:///{DATABASE_DIRECTORY / f'{name}.db'}"


def database_exists(name: str) -> bool:
    db_path = database_path_for(name)
    if db_path is None:
        return True
    return db_path.exists()


def list_databases() -> list[dict]:
    entries: list[dict] = []
    existing = {path.stem for path in DATABASE_DIRECTORY.glob("*.db")}
    for alias, label in [(PRIMARY_DB_ALIAS, "Principal"), (DEMO_DB_ALIAS, "Demo")]:
        entries.append({
            "name": alias,
            "label": label,
            "exists": database_exists(alias)
        })
    for name in sorted(existing):
        if name in {"finances", "finances_demo"}:
            continue
        entries.append({
            "name": name,
            "label": name.capitalize(),
            "exists": True
        })
    return entries


def default_database_name() -> str:
    if database_exists(PRIMARY_DB_ALIAS):
        return PRIMARY_DB_ALIAS
    dbs = list_databases()
    for entry in dbs:
        if entry["name"] not in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
            return entry["name"]
    return DEFAULT_DB_NAME


def get_engine_for_name(name: str):
    name = normalize_db_name(name)
    if name in _ENGINE_CACHE:
        return _ENGINE_CACHE[name]
    url = database_url_for(name)
    ensure_sqlite_directory(url)
    engine_for_name = create_engine_for_url(url)
    _ENGINE_CACHE[name] = engine_for_name
    return engine_for_name


def get_session_factory(name: str) -> sessionmaker:
    name = normalize_db_name(name)
    if name in _SESSION_CACHE:
        return _SESSION_CACHE[name]
    engine_for_name = get_engine_for_name(name)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine_for_name)
    _SESSION_CACHE[name] = factory
    return factory


def ensure_database_initialized(name: str) -> None:
    name = normalize_db_name(name)
    if name in _INITIALIZED_DATABASES:
        return
    with _INIT_LOCK:
        if name in _INITIALIZED_DATABASES:
            return
        engine_for_name = get_engine_for_name(name)
        init_db(engine_override=engine_for_name)
        session_factory = get_session_factory(name)
        db = session_factory()
        try:
            from finance_app.models import Currency
            currencies = db.query(Currency).first()
            if not currencies:
                from finance_app.init_db import initialize_database
                initialize_database(
                    create_samples=True,
                    create_demo_data=(name == DEMO_DB_ALIAS),
                    session_factory=session_factory,
                    create_tables_func=lambda: init_db(engine_override=engine_for_name)
                )
            elif name == DEMO_DB_ALIAS:
                from finance_app.init_db import init_demo_data
                init_demo_data(db)
        finally:
            db.close()
        _INITIALIZED_DATABASES.add(name)


def get_db(request: Request):
    """
    Dependency for FastAPI to get database session
    Usage:
        @app.get("/")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    selected_name = resolve_db_name(request)
    if not database_exists(selected_name):
        selected_name = default_database_name()
    ensure_database_initialized(selected_name)
    session_factory = get_session_factory(selected_name)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def init_db(engine_override=None):
    """Initialize database - create all tables"""
    # Import all models here to ensure they're registered
    from finance_app.models import (
        Currency, Account, CategoryGroup, Category,
        Payee, Transaction, BudgetMonth, RecurringTransaction, ExchangeRate,
        Debt, DebtPayment, DebtCategoryAllocation, DebtAmortizationMonthly,
        DebtSnapshotMonthly, DebtSnapshotProjectedMonthly,
        YnabCategoryMapping, AlertRule, BudgetAlertState, ReconciliationSession,
        EmailScrapeTransaction, PatrimonioAsset
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
        table_name="categories",
        column_name="alerts_enabled",
        column_definition="alerts_enabled BOOLEAN DEFAULT 1",
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
        table_name="transactions",
        column_name="investment_asset_id",
        column_definition="investment_asset_id INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="debt_id",
        column_definition="debt_id INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="source",
        column_definition="source VARCHAR(50)",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="transactions",
        column_name="source_id",
        column_definition="source_id VARCHAR(120)",
        engine_override=active_engine
    )
    ensure_sqlite_index(
        index_name="uq_transactions_source_source_id",
        index_definition="CREATE UNIQUE INDEX IF NOT EXISTS "
                         "uq_transactions_source_source_id ON transactions (source, source_id)",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="loan_years",
        column_definition="loan_years INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="category_id",
        column_definition="category_id INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="has_insurance",
        column_definition="has_insurance BOOLEAN DEFAULT 0",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="principal_balance",
        column_definition="principal_balance NUMERIC(18, 6)",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="interest_balance",
        column_definition="interest_balance NUMERIC(18, 6)",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="annual_interest_rate",
        column_definition="annual_interest_rate NUMERIC(10, 6)",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="term_months",
        column_definition="term_months INTEGER",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="next_due_date",
        column_definition="next_due_date DATE",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="debts",
        column_name="last_accrual_date",
        column_definition="last_accrual_date DATE",
        engine_override=active_engine
    )
    ensure_sqlite_column(
        table_name="accounts",
        column_name="country",
        column_definition="country VARCHAR(50)",
        engine_override=active_engine
    )
    # Patrimonio asset new columns
    for col, defn in [
        ("depreciation_method", "depreciation_method VARCHAR(40) DEFAULT 'sin_depreciacion'"),
        ("depreciation_rate", "depreciation_rate FLOAT"),
        ("depreciation_years", "depreciation_years INTEGER"),
        ("depreciation_salvage_value", "depreciation_salvage_value NUMERIC(18,2)"),
        ("depreciation_start_date", "depreciation_start_date DATE"),
        ("return_rate", "return_rate FLOAT"),
        ("return_amount", "return_amount NUMERIC(18,2)"),
    ]:
        ensure_sqlite_column(table_name="patrimonio_asset", column_name=col, column_definition=defn, engine_override=active_engine)
    ensure_sqlite_column(
        table_name="goals",
        column_name="category_id",
        column_definition="category_id INTEGER REFERENCES categories(id)",
        engine_override=active_engine
    )
    _backfill_account_country(active_engine)
    print("✓ Database tables created")


ACCOUNT_COUNTRY_MAP: dict[str, str] = {
    "cuenta corriente cop": "Colombia",
    "ahorros usd": "Panama",
}


def _backfill_account_country(engine_override=None):
    """Set country for accounts based on name: Cuenta Corriente COP → Colombia, Ahorros USD → Panama."""
    active_engine = engine_override or engine
    with active_engine.begin() as connection:
        for account_name, country in ACCOUNT_COUNTRY_MAP.items():
            connection.execute(
                text("UPDATE accounts SET country = :country WHERE lower(name) = :name AND (country IS NULL OR country = '')"),
                {"country": country, "name": account_name},
            )


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


def ensure_sqlite_index(
    index_name: str,
    index_definition: str,
    engine_override=None
) -> None:
    active_engine = engine_override or engine
    if active_engine.url.drivername != "sqlite":
        return

    with active_engine.begin() as connection:
        indexes = connection.execute(text("PRAGMA index_list(transactions)")).fetchall()
        existing_names = {row[1] for row in indexes}
        if index_name in existing_names:
            return
        connection.execute(text(index_definition))
