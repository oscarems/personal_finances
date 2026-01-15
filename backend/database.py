from sqlalchemy import create_engine
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
        Payee, Transaction, BudgetMonth, RecurringTransaction, ExchangeRate
    )

    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created")
