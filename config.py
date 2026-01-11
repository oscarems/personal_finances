import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent

# Database
DATABASE_PATH = BASE_DIR / 'data' / 'finances.db'
SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
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

# Budget categories (YNAB style)
DEFAULT_CATEGORY_GROUPS = [
    {
        'name': 'Gastos Esenciales',
        'categories': [
            'Vivienda',
            'Servicios Públicos',
            'Alimentación',
            'Transporte',
            'Salud'
        ]
    },
    {
        'name': 'Obligaciones Financieras',
        'categories': [
            'Hipoteca',
            'Tarjetas de Crédito',
            'Préstamos'
        ]
    },
    {
        'name': 'Gastos Discrecionales',
        'categories': [
            'Entretenimiento',
            'Restaurantes',
            'Compras',
            'Suscripciones'
        ]
    },
    {
        'name': 'Ahorros',
        'categories': [
            'Fondo de Emergencia',
            'Vacaciones',
            'Inversiones'
        ]
    }
]

# Account types
ACCOUNT_TYPES = [
    'checking',      # Cuenta corriente
    'savings',       # Cuenta de ahorros
    'credit_card',   # Tarjeta de crédito
    'cash'           # Efectivo
]
