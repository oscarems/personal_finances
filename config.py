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

# Budget categories (YNAB style - basado en tu exportación de YNAB)
# rollover_type: 'reset' = dinero sobrante vuelve a Ready to Assign cada mes
#                'accumulate' = dinero sobrante pasa al siguiente mes
DEFAULT_CATEGORY_GROUPS = [
    {
        'name': 'Needs',  # Necesidades (basado en tu YNAB)
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Gym', 'rollover_type': 'reset'},
            {'name': 'Cosmeticos', 'rollover_type': 'reset'},
            {'name': 'Bonos Prepagados', 'rollover_type': 'reset'},
            {'name': 'Kuro', 'rollover_type': 'reset'},
            {'name': 'Pension', 'rollover_type': 'reset'},
            {'name': 'EPS', 'rollover_type': 'reset'},
            {'name': 'Mercado', 'rollover_type': 'reset'},
            {'name': 'Prepagada', 'rollover_type': 'reset'},
            {'name': 'Pelo', 'rollover_type': 'reset'},
            {'name': 'Caja compensacion', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Hogar',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Hipoteca', 'rollover_type': 'reset'},
            {'name': 'Mantenimiento', 'rollover_type': 'reset'},
            {'name': 'Amoblar', 'rollover_type': 'reset'},
            {'name': 'Impuestos', 'rollover_type': 'reset'},
            {'name': 'Administracion', 'rollover_type': 'reset'},
            {'name': 'Empleada', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Deudas',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Nu', 'rollover_type': 'reset'},
            {'name': 'Deuda Mama', 'rollover_type': 'reset'},
            {'name': 'Gastos de su casa', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Servicios',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Gas', 'rollover_type': 'reset'},
            {'name': 'Celular', 'rollover_type': 'reset'},
            {'name': 'Internet', 'rollover_type': 'reset'},
            {'name': 'Luz', 'rollover_type': 'reset'},
            {'name': 'Agua', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Streaming',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Ynab', 'rollover_type': 'reset'},
            {'name': 'Youtube', 'rollover_type': 'reset'},
            {'name': 'Netflix', 'rollover_type': 'reset'},
            {'name': 'HBO', 'rollover_type': 'reset'},
            {'name': 'Spotify', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Pleasures',  # Placeres
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Coffes', 'rollover_type': 'reset'},
            {'name': 'Salidas', 'rollover_type': 'reset'},
            {'name': 'Restaurantes', 'rollover_type': 'reset'},
            {'name': 'Bar', 'rollover_type': 'reset'},
            {'name': 'Personal', 'rollover_type': 'reset'},
            {'name': 'Juegos', 'rollover_type': 'reset'},
            {'name': 'Ropa', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Trabajo',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Office Upgrades', 'rollover_type': 'reset'},
            {'name': 'Viajes', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Salud',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Medicamentos', 'rollover_type': 'reset'},
            {'name': 'Terapia', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Credit Card',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Black MC', 'rollover_type': 'reset'},
            {'name': 'Gold Visa', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Otros',
        'rollover_type': 'reset',
        'categories': [
            {'name': 'Otros', 'rollover_type': 'reset'},
            {'name': 'Ropa', 'rollover_type': 'reset'},
            {'name': 'Crunchy', 'rollover_type': 'reset'},
            {'name': 'Claude', 'rollover_type': 'reset'}
        ]
    },
    {
        'name': 'Big Plans',  # Grandes Planes - acumulan
        'rollover_type': 'accumulate',
        'categories': [
            {'name': 'Concierto', 'rollover_type': 'accumulate'},
            {'name': 'Juegos', 'rollover_type': 'accumulate'},
            {'name': 'Big Plans', 'rollover_type': 'accumulate'},
            {'name': 'cafe', 'rollover_type': 'accumulate'}
        ]
    },
    {
        'name': 'Savings',  # Ahorros - acumulan
        'rollover_type': 'accumulate',
        'categories': [
            {'name': 'Cirugia Nariz', 'rollover_type': 'accumulate'},
            {'name': 'Short Term', 'rollover_type': 'accumulate'},
            {'name': 'Salud', 'rollover_type': 'accumulate'},
            {'name': 'Emergencia', 'rollover_type': 'accumulate'},
            {'name': 'Kuro', 'rollover_type': 'accumulate'},
            {'name': 'Tecnologia', 'rollover_type': 'accumulate'},
            {'name': 'Viajes', 'rollover_type': 'accumulate'},
            {'name': 'Regalos', 'rollover_type': 'accumulate'}
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
