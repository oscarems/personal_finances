import logging
from pathlib import Path
import re
import threading
import shutil

logger = logging.getLogger(__name__)

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
    """Normalize a database name to lowercase trimmed form."""
    return name.strip().lower()


def is_valid_db_name(name: str) -> bool:
    """Validate that *name* is a safe database identifier (lowercase alphanumeric)."""
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name))


def clear_database_cache(name: str) -> None:
    """Dispose the engine and remove session/cache entries for a database."""
    normalized = normalize_db_name(name)
    engine_to_clear = _ENGINE_CACHE.pop(normalized, None)
    if engine_to_clear is not None:
        engine_to_clear.dispose()
    _SESSION_CACHE.pop(normalized, None)
    _INITIALIZED_DATABASES.discard(normalized)


def delete_database(name: str) -> None:
    """Delete a user-created SQLite database file (not primary or demo)."""
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
    """Copy a SQLite database file to create a new database with a different name.

    Raises:
        ValueError: If source equals target, or either is not SQLite.
        FileNotFoundError: If source database does not exist.
        FileExistsError: If target database already exists.
    """
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
    """Rename a user-created SQLite database file.

    Primary and demo databases cannot be renamed.

    Raises:
        ValueError: If source is primary/demo, source equals target, or not SQLite.
        FileNotFoundError: If source database does not exist.
        FileExistsError: If target database already exists.
    """
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
    """Create the parent directory for a SQLite database file if it does not exist."""
    if not database_url.startswith('sqlite:///'):
        return
    Path(database_url.replace('sqlite:///', '')).parent.mkdir(parents=True, exist_ok=True)


def create_engine_for_url(database_url: str):
    """Create a SQLAlchemy engine with appropriate connect_args for the URL scheme."""
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
    """Determine the database name from the request cookies.

    Checks ``db_name`` cookie first, then falls back to the legacy
    ``db_mode`` cookie, and finally to the default database name.
    """
    raw_name = request.cookies.get("db_name")
    if raw_name:
        return normalize_db_name(raw_name)
    legacy_mode = request.cookies.get("db_mode", DEFAULT_DB_MODE)
    if legacy_mode in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
        return legacy_mode
    return DEFAULT_DB_NAME


def database_path_for(name: str) -> Path | None:
    """Return the filesystem path for a named database, or None if not SQLite."""
    name = normalize_db_name(name)
    if name == PRIMARY_DB_ALIAS:
        return Path(SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")) if SQLALCHEMY_DATABASE_URI.startswith("sqlite:///") else None
    if name == DEMO_DB_ALIAS:
        return Path(DEMO_DATABASE_URL.replace("sqlite:///", "")) if DEMO_DATABASE_URL.startswith("sqlite:///") else None
    return DATABASE_DIRECTORY / f"{name}.db"


def database_url_for(name: str) -> str:
    """Return the SQLAlchemy database URL for a named database."""
    name = normalize_db_name(name)
    if name == PRIMARY_DB_ALIAS:
        return SQLALCHEMY_DATABASE_URI
    if name == DEMO_DB_ALIAS:
        return DEMO_DATABASE_URL
    return f"sqlite:///{DATABASE_DIRECTORY / f'{name}.db'}"


def database_exists(name: str) -> bool:
    """Return True if the named database file exists (non-SQLite always returns True)."""
    db_path = database_path_for(name)
    if db_path is None:
        return True
    return db_path.exists()


def list_databases() -> list[dict]:
    """List all available databases (primary, demo, and user-created)."""
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
    """Return the name of the default database to use on startup."""
    if database_exists(PRIMARY_DB_ALIAS):
        return PRIMARY_DB_ALIAS
    dbs = list_databases()
    for entry in dbs:
        if entry["name"] not in {PRIMARY_DB_ALIAS, DEMO_DB_ALIAS}:
            return entry["name"]
    return DEFAULT_DB_NAME


def get_engine_for_name(name: str):
    """Return a cached SQLAlchemy engine for the named database, creating one if needed."""
    name = normalize_db_name(name)
    if name in _ENGINE_CACHE:
        return _ENGINE_CACHE[name]
    url = database_url_for(name)
    ensure_sqlite_directory(url)
    engine_for_name = create_engine_for_url(url)
    _ENGINE_CACHE[name] = engine_for_name
    return engine_for_name


def get_session_factory(name: str) -> sessionmaker:
    """Return a cached sessionmaker for the named database, creating one if needed."""
    name = normalize_db_name(name)
    if name in _SESSION_CACHE:
        return _SESSION_CACHE[name]
    engine_for_name = get_engine_for_name(name)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine_for_name)
    _SESSION_CACHE[name] = factory
    return factory


def ensure_database_initialized(name: str) -> None:
    """Ensure tables exist and seed data is loaded for the named database.

    Thread-safe: uses a lock to prevent concurrent initialization of the
    same database. Subsequent calls for an already-initialized database are
    no-ops.
    """
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


def init_db(engine_override=None) -> None:
    """Create all tables and apply pending SQLite schema migrations."""
    # Import all models to register them with Base.metadata
    from finance_app.models import (  # noqa: F401
        Currency, Account, CategoryGroup, Category,
        Payee, Transaction, BudgetMonth, RecurringTransaction, ExchangeRate,
        Debt, DebtPayment, DebtCategoryAllocation, DebtAmortizationMonthly,
        DebtSnapshotMonthly, DebtSnapshotProjectedMonthly,
        AlertRule, BudgetAlertState, ReconciliationSession,
        EmailScrapeTransaction, PatrimonioAsset
    )

    active_engine = engine_override or engine
    Base.metadata.create_all(bind=active_engine)
    _apply_sqlite_migrations(active_engine)
    _backfill_account_country(active_engine)
    logger.info("Database tables created")


# ---------------------------------------------------------------------------
# Schema migration registry — each entry is (table, column, DDL definition)
# ---------------------------------------------------------------------------

_MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("recurring_transactions", "transaction_type", "transaction_type VARCHAR(20) DEFAULT 'expense'"),
    ("categories", "is_essential", "is_essential BOOLEAN DEFAULT 0"),
    ("categories", "is_emergency_fund", "is_emergency_fund BOOLEAN DEFAULT 0"),
    ("categories", "alerts_enabled", "alerts_enabled BOOLEAN DEFAULT 1"),
    ("transactions", "is_adjustment", "is_adjustment BOOLEAN DEFAULT 0"),
    ("transactions", "original_amount", "original_amount FLOAT DEFAULT 0"),
    ("transactions", "original_currency_id", "original_currency_id INTEGER"),
    ("transactions", "fx_rate", "fx_rate FLOAT"),
    ("transactions", "base_amount", "base_amount FLOAT"),
    ("transactions", "base_currency_id", "base_currency_id INTEGER"),
    ("transactions", "investment_asset_id", "investment_asset_id INTEGER"),
    ("transactions", "debt_id", "debt_id INTEGER"),
    ("transactions", "source", "source VARCHAR(50)"),
    ("transactions", "source_id", "source_id VARCHAR(120)"),
    ("debts", "loan_years", "loan_years INTEGER"),
    ("debts", "category_id", "category_id INTEGER"),
    ("debts", "has_insurance", "has_insurance BOOLEAN DEFAULT 0"),
    ("debts", "principal_balance", "principal_balance NUMERIC(18, 6)"),
    ("debts", "interest_balance", "interest_balance NUMERIC(18, 6)"),
    ("debts", "annual_interest_rate", "annual_interest_rate NUMERIC(10, 6)"),
    ("debts", "term_months", "term_months INTEGER"),
    ("debts", "next_due_date", "next_due_date DATE"),
    ("debts", "last_accrual_date", "last_accrual_date DATE"),
    ("accounts", "country", "country VARCHAR(50)"),
    ("patrimonio_asset", "depreciation_method", "depreciation_method VARCHAR(40) DEFAULT 'sin_depreciacion'"),
    ("patrimonio_asset", "depreciation_rate", "depreciation_rate FLOAT"),
    ("patrimonio_asset", "depreciation_years", "depreciation_years INTEGER"),
    ("patrimonio_asset", "depreciation_salvage_value", "depreciation_salvage_value NUMERIC(18,2)"),
    ("patrimonio_asset", "depreciation_start_date", "depreciation_start_date DATE"),
    ("patrimonio_asset", "return_rate", "return_rate FLOAT"),
    ("patrimonio_asset", "return_amount", "return_amount NUMERIC(18,2)"),
    ("goals", "category_id", "category_id INTEGER REFERENCES categories(id)"),
]

_MIGRATION_INDEXES: list[tuple[str, str]] = [
    (
        "uq_transactions_source_source_id",
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_transactions_source_source_id ON transactions (source, source_id)",
    ),
]


def _apply_sqlite_migrations(active_engine) -> None:
    """Ensure all migration columns and indexes exist."""
    for table, column, definition in _MIGRATION_COLUMNS:
        ensure_sqlite_column(
            table_name=table,
            column_name=column,
            column_definition=definition,
            engine_override=active_engine,
        )
    for index_name, index_ddl in _MIGRATION_INDEXES:
        ensure_sqlite_index(
            index_name=index_name,
            index_definition=index_ddl,
            engine_override=active_engine,
        )


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
    """Add a column to a SQLite table if it does not already exist."""
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
    """Create a SQLite index if it does not already exist."""
    active_engine = engine_override or engine
    if active_engine.url.drivername != "sqlite":
        return

    with active_engine.begin() as connection:
        indexes = connection.execute(text("PRAGMA index_list(transactions)")).fetchall()
        existing_names = {row[1] for row in indexes}
        if index_name in existing_names:
            return
        connection.execute(text(index_definition))
