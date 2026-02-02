#!/usr/bin/env python3
"""
Script de prueba para leer y visualizar CSV de YNAB
Úsalo para probar tu archivo CSV antes de importarlo
"""
import sys
import csv
from pathlib import Path


def print_table_row(cols, widths):
    """Helper to print a table row"""
    row = "| "
    for col, width in zip(cols, widths):
        row += str(col)[:width].ljust(width) + " | "
    print(row)


def print_separator(widths):
    """Helper to print table separator"""
    sep = "+"
    for width in widths:
        sep += "-" * (width + 2) + "+"
    print(sep)


def read_ynab_csv(csv_path):
    """Lee y muestra el contenido del CSV de YNAB"""

    if not Path(csv_path).exists():
        print(f"❌ Error: Archivo no encontrado: {csv_path}")
        sys.exit(1)

    print(f"\n📂 Leyendo archivo: {csv_path}\n")
    print("=" * 120)

    # Leer CSV
    rows = []
    headers = []
    widths = [20, 10, 25, 30, 20, 10, 10, 10]

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames

        print(f"✅ Columnas encontradas: {', '.join(headers)}\n")

        for idx, row in enumerate(reader, 1):
            rows.append(row)

            # Mostrar primeras 10 filas como ejemplo
            if idx <= 10:
                # Formatear para tabla
                display_row = [
                    row.get('Account', '')[:20],
                    row.get('Date', ''),
                    row.get('Payee', '')[:25],
                    row.get('Category', '')[:30],
                    row.get('Memo', '')[:20],
                    row.get('Outflow', ''),
                    row.get('Inflow', ''),
                    row.get('Cleared', '')
                ]

                if idx == 1:
                    # Imprimir encabezados
                    table_headers = ['Account', 'Date', 'Payee', 'Category', 'Memo', 'Outflow', 'Inflow', 'Cleared']
                    print_separator(widths)
                    print_table_row(table_headers, widths)
                    print_separator(widths)

                print_table_row(display_row, widths)

            elif idx == 11:
                # Cerrar la tabla
                print_separator(widths)

    print("\n" + "=" * 120)
    print(f"\n📊 Resumen:")
    print(f"   Total de filas: {len(rows)}")

    # Estadísticas
    accounts = set(row.get('Account', '') for row in rows if row.get('Account'))
    categories = set(row.get('Category', '') for row in rows if row.get('Category'))
    payees = set(row.get('Payee', '') for row in rows if row.get('Payee'))

    print(f"   Cuentas únicas: {len(accounts)}")
    print(f"   Categorías únicas: {len(categories)}")
    print(f"   Beneficiarios únicos: {len(payees)}")

    # Mostrar cuentas
    if accounts:
        print(f"\n📋 Cuentas encontradas:")
        for acc in sorted(accounts):
            if acc:
                count = sum(1 for row in rows if row.get('Account') == acc)
                print(f"   - {acc} ({count} transacciones)")

    # Mostrar categorías principales
    if categories:
        print(f"\n🏷️  Primeras 10 categorías:")
        category_counts = {}
        for row in rows:
            cat = row.get('Category', '')
            if cat:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for cat, count in sorted_cats:
            print(f"   - {cat} ({count} transacciones)")

    # Validaciones
    print(f"\n✔️  Validaciones:")
    invalid_dates = sum(1 for row in rows if not row.get('Date') or row.get('Date') == '########')
    zero_amounts = sum(1 for row in rows if not row.get('Outflow') and not row.get('Inflow'))

    if invalid_dates > 0:
        print(f"   ⚠️  {invalid_dates} filas con fechas inválidas (se omitirán)")
    else:
        print(f"   ✅ Todas las fechas son válidas")

    if zero_amounts > 0:
        print(f"   ⚠️  {zero_amounts} filas con monto cero (se omitirán)")
    else:
        print(f"   ✅ Todos los montos son válidos")

    print("\n" + "=" * 120)
    print("\n💡 Para importar este archivo:")
    print(f"   1. Ejecuta la aplicación: python run.py")
    print(f"   2. Ve a: http://localhost:8000/import")
    print(f"   3. Selecciona la moneda (COP o USD)")
    print(f"   4. Sube este archivo CSV")
    print()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: python test_csv_reader.py <ruta_al_archivo.csv>")
        print("\nEjemplo:")
        print("  python test_csv_reader.py mi_presupuesto.csv")
        sys.exit(1)

    csv_path = sys.argv[1]
    read_ynab_csv(csv_path)
