import sqlite3

conn = sqlite3.connect(r"D:/Github/personal_finances/data/finances.db")
cursor = conn.cursor()

tablas = [
    'transactions', 'categories', 'category_groups', 
    'accounts', 'budget_months', 'debts', 'debt_payments',
    'wealth_assets', 'patrimonio_asset', 'patrimonio_debt', 'goals'
]

for tabla in tablas:
    cursor.execute(f"PRAGMA table_info({tabla})")
    cols = cursor.fetchall()
    print(f"\n--- {tabla} ---")
    for col in cols:
        print(f"  {col[1]} ({col[2]})")

conn.close()