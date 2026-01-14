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
# rollover_type: 'reset' = dinero sobrante vuelve a Ready to Assign cada mes
#                'accumulate' = dinero sobrante pasa al siguiente mes
DEFAULT_CATEGORY_GROUPS = [
    {
        'name': 'Gastos Esenciales',
        'rollover_type': 'reset',  # Se resetean mensualmente
        'categories': [
            {'name': 'Vivienda', 'rollover_type': 'reset'},
            {'name': 'Servicios Públicos', 'rollover_type': 'reset'},
            {'name': 'Alimentación', 'rollover_type': 'reset'},
            {'name': 'Transporte', 'rollover_type': 'reset'},
            {'name': 'Salud', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Obligaciones Financieras',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Hipoteca', 'rollover_type': 'reset'},
            {'name': 'Tarjetas de Crédito', 'rollover_type': 'reset'},
            {'name': 'Préstamos', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Gastos Discrecionales',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Entretenimiento', 'rollover_type': 'reset'},
            {'name': 'Restaurantes', 'rollover_type': 'reset'},
            {'name': 'Compras', 'rollover_type': 'reset'},
            {'name': 'Suscripciones', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Ahorros',
        'rollover_type': 'accumulate',  # Acumulan mes a mes
        'categories': [
            {'name': 'Fondo de Emergencia', 'rollover_type': 'accumulate'},
            {'name': 'Vacaciones', 'rollover_type': 'accumulate'},
            {'name': 'Inversiones', 'rollover_type': 'accumulate'},
            {'name': 'Compra Grande', 'rollover_type': 'accumulate'}
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
