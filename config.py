import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Database
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

# App config
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = True

# Currency settings
DEFAULT_CURRENCY = 'COP'
SUPPORTED_CURRENCIES = {
    'COP': {'symbol': '$', 'name': 'Peso Colombiano', 'decimals': 0},
    'USD': {'symbol': 'US$', 'name': 'Dólar Estadounidense', 'decimals': 2}
}

# Default exchange rates (manually updatable)
DEFAULT_EXCHANGE_RATES = {
    'COP': 1.0,      # Base currency
    'USD': 4000.0    # 1 USD = 4000 COP (actualizar manualmente)
}

# Budget alert settings
# Thresholds are percentage of budget consumed (0-100 scale).
BUDGET_ALERT_DEFAULT_THRESHOLDS = {
    'warning': 60,
    'risk': 80,
    'critical': 100
}

# Pacing margins are percentage points above expected spend for the period.
BUDGET_ALERT_DEFAULT_PACING_MARGINS = {
    'warning': 10,
    'risk': 20,
    'critical': 30
}

# Optional per-category overrides. Keys can be category IDs or names.
# Example:
# BUDGET_ALERT_CATEGORY_OVERRIDES = {
#     12: {"thresholds": {"warning": 55, "risk": 75, "critical": 100}},
#     "Transporte": {"pacing_margins": {"warning": 8, "risk": 18, "critical": 28}}
# }
BUDGET_ALERT_CATEGORY_OVERRIDES = {}

# Cooldown in days to repeat the same alert state if it persists.
BUDGET_ALERT_COOLDOWN_DAYS = int(os.getenv('BUDGET_ALERT_COOLDOWN_DAYS', '3'))

# Budget categories (YNAB style)
# rollover_type: 'reset' = dinero sobrante vuelve a Ready to Assign cada mes
#                'accumulate' = dinero sobrante pasa al siguiente mes
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

# Account types con configuraciones detalladas
ACCOUNT_TYPES = {
    'checking': {
        'name': 'Cuenta Corriente',
        'icon': '💳',
        'description': 'Cuenta bancaria para uso diario',
        'can_overdraft': True,  # Puede tener sobregiro
        'tracks_interest': False,
        'requires_payment': False,
        'is_debt': False
    },
    'savings': {
        'name': 'Cuenta de Ahorros',
        'icon': '🏦',
        'description': 'Cuenta de ahorro con intereses',
        'can_overdraft': False,
        'tracks_interest': True,  # Genera intereses
        'requires_payment': False,
        'is_debt': False,
        'interest_rate_field': True  # Tiene campo de tasa de interés
    },
    'credit_card': {
        'name': 'Tarjeta de Crédito',
        'icon': '💳',
        'description': 'Tarjeta de crédito con cupo',
        'can_overdraft': False,
        'tracks_interest': True,
        'requires_payment': True,  # Requiere pago mensual
        'is_debt': True,  # Es una deuda
        'credit_limit_field': True,  # Tiene campo de cupo
        'payment_due_field': True  # Fecha de pago
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
        'monthly_payment_field': True,  # Cuota mensual
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
        'original_amount_field': True  # Monto original del préstamo
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
        'maturity_date_field': True,  # Fecha de vencimiento
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

# Exchange Rate API Configuration
EXCHANGE_RATE_API = {
    'primary': 'https://api.exchangerate-api.com/v4/latest/USD',  # API primaria
    'fallback': 'https://api.exchangerate.host/latest?base=USD',   # API de respaldo
    'timeout': 5,  # segundos
    'retries': 2,  # intentos por API
    'fallback_average_days': 5,  # Promedio de últimos 5 días
    'default_rate': 3800  # Tasa por defecto si todo falla
}
