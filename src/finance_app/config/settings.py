from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LOGGER = logging.getLogger("finance_app.config.settings")

load_dotenv(override=False)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# BASE_DIR points to the project root (three levels up from this file)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DEMO_MODE = os.getenv('DEMO_MODE', '').lower() in {'1', 'true', 'yes', 'on'}
DEFAULT_DB_MODE = 'demo' if DEMO_MODE else 'primary'

PRIMARY_DATABASE_PATH = BASE_DIR / 'data' / 'finances.db'
DEMO_DATABASE_PATH = BASE_DIR / 'data' / 'finances_demo.db'

PRIMARY_DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{PRIMARY_DATABASE_PATH}')
DEMO_DATABASE_URL = os.getenv('DEMO_DATABASE_URL', f'sqlite:///{DEMO_DATABASE_PATH}')

SQLALCHEMY_DATABASE_URI = PRIMARY_DATABASE_URL
DATABASE_IS_SQLITE = SQLALCHEMY_DATABASE_URI.startswith('sqlite:///')
DEMO_DATABASE_IS_SQLITE = DEMO_DATABASE_URL.startswith('sqlite:///')
SQLALCHEMY_TRACK_MODIFICATIONS = False

# ---------------------------------------------------------------------------
# App config
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = True

# ---------------------------------------------------------------------------
# Currency settings
# ---------------------------------------------------------------------------
DEFAULT_CURRENCY = 'COP'
SUPPORTED_CURRENCIES = {
    'COP': {'symbol': '$', 'name': 'Peso Colombiano', 'decimals': 0},
    'USD': {'symbol': 'US$', 'name': 'Dólar Estadounidense', 'decimals': 2}
}

DEFAULT_EXCHANGE_RATES = {
    'COP': 1.0,
    'USD': 4000.0
}

# ---------------------------------------------------------------------------
# Budget alert settings
# ---------------------------------------------------------------------------
BUDGET_ALERT_DEFAULT_THRESHOLDS = {
    'warning': 60,
    'risk': 80,
    'critical': 100
}

BUDGET_ALERT_DEFAULT_PACING_MARGINS = {
    'warning': 10,
    'risk': 20,
    'critical': 30
}

BUDGET_ALERT_CATEGORY_OVERRIDES = {}

BUDGET_ALERT_COOLDOWN_DAYS = int(os.getenv('BUDGET_ALERT_COOLDOWN_DAYS', '3'))

# ---------------------------------------------------------------------------
# Default budget category groups
# ---------------------------------------------------------------------------
DEFAULT_CATEGORY_GROUPS = [
    {
        'name': 'Vivienda',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Arriendo / Hipoteca', 'rollover_type': 'reset'},
            {'name': 'Servicios Públicos', 'rollover_type': 'reset'},
            {'name': 'Internet y Celular', 'rollover_type': 'reset'},
            {'name': 'Mantenimiento', 'rollover_type': 'reset'},
            {'name': 'Seguros', 'rollover_type': 'reset'},
        ]
    },
    {
        'name': 'Necesidades',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Mercado', 'rollover_type': 'reset'},
            {'name': 'Transporte', 'rollover_type': 'reset'},
            {'name': 'Salud', 'rollover_type': 'reset'},
            {'name': 'Educación', 'rollover_type': 'reset'},
            {'name': 'Cuidado Personal', 'rollover_type': 'reset'},
        ]
    },
    {
        'name': 'Estilo de Vida',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Restaurantes', 'rollover_type': 'reset'},
            {'name': 'Entretenimiento', 'rollover_type': 'reset'},
            {'name': 'Suscripciones', 'rollover_type': 'reset'},
            {'name': 'Ropa', 'rollover_type': 'reset'},
            {'name': 'Hobbies', 'rollover_type': 'reset'},
        ]
    },
    {
        'name': 'Deudas',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Tarjeta de Crédito', 'rollover_type': 'reset'},
            {'name': 'Préstamos', 'rollover_type': 'reset'},
        ]
    },
    {
        'name': 'Ahorros',
        'rollover_type': 'accumulate',
        'categories': [
            {'name': 'Fondo de Emergencia', 'rollover_type': 'accumulate'},
            {'name': 'Vacaciones', 'rollover_type': 'accumulate'},
            {'name': 'Metas a Largo Plazo', 'rollover_type': 'accumulate'},
        ]
    },
]

# ---------------------------------------------------------------------------
# Account types
# ---------------------------------------------------------------------------
ACCOUNT_TYPES = {
    'checking': {
        'name': 'Cuenta Corriente',
        'icon': '💳',
        'description': 'Cuenta bancaria para uso diario',
        'can_overdraft': True,
        'tracks_interest': False,
        'requires_payment': False,
        'is_debt': False
    },
    'savings': {
        'name': 'Cuenta de Ahorros',
        'icon': '🏦',
        'description': 'Cuenta de ahorro con intereses',
        'can_overdraft': False,
        'tracks_interest': True,
        'requires_payment': False,
        'is_debt': False,
        'interest_rate_field': True
    },
    'credit_card': {
        'name': 'Tarjeta de Crédito',
        'icon': '💳',
        'description': 'Tarjeta de crédito con cupo',
        'can_overdraft': False,
        'tracks_interest': True,
        'requires_payment': True,
        'is_debt': True,
        'credit_limit_field': True,
        'payment_due_field': True
    },
    'credit_loan': {
        'name': 'Crédito Libre Inversión',
        'icon': '💰',
        'description': 'Préstamo personal / crédito de consumo',
        'can_overdraft': False,
        'tracks_interest': True,
        'requires_payment': True,
        'is_debt': True,
        'interest_rate_field': True,
        'monthly_payment_field': True,
        'payment_due_field': True
    },
    'mortgage': {
        'name': 'Hipoteca',
        'icon': '🏠',
        'description': 'Préstamo hipotecario',
        'can_overdraft': False,
        'tracks_interest': True,
        'requires_payment': True,
        'is_debt': True,
        'interest_rate_field': True,
        'monthly_payment_field': True,
        'payment_due_field': True,
        'original_amount_field': True
    },
    'cdt': {
        'name': 'CDT (Certificado Depósito)',
        'icon': '📜',
        'description': 'Certificado de Depósito a Término',
        'can_overdraft': False,
        'tracks_interest': True,
        'requires_payment': False,
        'is_debt': False,
        'interest_rate_field': True,
        'maturity_date_field': True,
        'original_amount_field': True
    },
    'investment': {
        'name': 'Inversión',
        'icon': '📈',
        'description': 'Cuenta de inversión (acciones, fondos, etc.)',
        'can_overdraft': False,
        'tracks_interest': False,
        'requires_payment': False,
        'is_debt': False
    },
    'cash': {
        'name': 'Efectivo',
        'icon': '💵',
        'description': 'Dinero en efectivo',
        'can_overdraft': False,
        'tracks_interest': False,
        'requires_payment': False,
        'is_debt': False
    }
}

# ---------------------------------------------------------------------------
# Ollama (LLM chat)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# Exchange Rate API
# ---------------------------------------------------------------------------
EXCHANGE_RATE_API = {
    'primary': 'https://api.exchangerate-api.com/v4/latest/USD',
    'fallback': 'https://api.exchangerate.host/latest?base=USD',
    'timeout': 5,
    'retries': 2,
    'fallback_average_days': 5,
    'default_rate': 3800
}


# ---------------------------------------------------------------------------
# Pydantic Settings (env-based)
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    email_panama_account: str | None = Field(default=None, validation_alias="EMAIL_PANAMA_ACCOUNT")
    email_colombia_account: str | None = Field(default=None, validation_alias="EMAIL_COLOMBIA_ACCOUNT")
    email_mastercard_black_account: str | None = Field(
        default=None,
        validation_alias="EMAIL_MASTERCARD_BLACK_ACCOUNT",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
