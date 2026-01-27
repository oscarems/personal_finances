import csv
from pathlib import Path

import pytest

from test_csv_reader import read_ynab_csv


def _write_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Account",
                "Date",
                "Payee",
                "Category",
                "Memo",
                "Outflow",
                "Inflow",
                "Cleared",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_read_ynab_csv_outputs_summary(tmp_path, capsys):
    csv_path = tmp_path / "sample.csv"
    _write_csv(
        csv_path,
        [
            {
                "Account": "Checking",
                "Date": "2024-01-01",
                "Payee": "Store",
                "Category": "Groceries",
                "Memo": "Weekly",
                "Outflow": "100.00",
                "Inflow": "",
                "Cleared": "Cleared",
            },
            {
                "Account": "Savings",
                "Date": "2024-01-02",
                "Payee": "Employer",
                "Category": "Income",
                "Memo": "",
                "Outflow": "",
                "Inflow": "500.00",
                "Cleared": "Cleared",
            },
        ],
    )

    read_ynab_csv(str(csv_path))
    captured = capsys.readouterr().out

    assert "Total de filas: 2" in captured
    assert "Cuentas únicas: 2" in captured
    assert "Categorías únicas: 2" in captured
    assert "Beneficiarios únicos: 2" in captured
    assert "✅ Todas las fechas son válidas" in captured


def test_read_ynab_csv_missing_file_exits(capsys):
    with pytest.raises(SystemExit) as excinfo:
        read_ynab_csv("missing.csv")

    captured = capsys.readouterr().out
    assert "Archivo no encontrado" in captured
    assert excinfo.value.code == 1
