"""Tests for the patrimonio calculator module."""
import pytest
from datetime import date
from types import SimpleNamespace

from finance_app.services.patrimonio.calculator import (
    aplicar_depreciacion,
    calcular_valor_activo_en_mes,
    saldo_deuda_en_mes,
    calcular_patrimonio_en_mes,
    timeline_patrimonio,
)


# ── Test data factories ──────────────────────────────────────────────


def make_asset(**overrides):
    defaults = dict(
        valor_adquisicion=100_000_000,
        fecha_adquisicion=date(2021, 1, 1),
        tasa_anual=0.05,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_debt(**overrides):
    """Create a Debt-like object (matches Debt model field names)."""
    defaults = dict(
        original_amount=10_000_000,
        interest_rate=12.0,  # percentage, like Debt model
        annual_interest_rate=None,
        term_months=60,
        loan_years=None,
        start_date=date(2021, 1, 1),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ── Asset valuation tests ────────────────────────────────────────────


class TestAssetValuation:
    def test_apartment_jan_2025(self):
        """Apartment: 300M, acquired 2021-06-15, rate 8%."""
        apt = make_asset(
            valor_adquisicion=300_000_000,
            fecha_adquisicion=date(2021, 6, 15),
            tasa_anual=0.08,
        )
        # year 2025, exponent = max(0, 2025 - 2021 - 1) = 3
        value = calcular_valor_activo_en_mes(apt, 2025, 1)
        expected = 300_000_000 * (1.08 ** 3)
        assert abs(value - expected) < 1  # 377_913_600

    def test_toyota_jan_2025(self):
        """Toyota: 80M, acquired 2020-03-10, rate -12% (depreciation)."""
        car = make_asset(
            valor_adquisicion=80_000_000,
            fecha_adquisicion=date(2020, 3, 10),
            tasa_anual=-0.12,
        )
        # year 2025, exponent = max(0, 2025 - 2020 - 1) = 4
        value = calcular_valor_activo_en_mes(car, 2025, 1)
        expected = 80_000_000 * (0.88 ** 4)
        assert abs(value - expected) < 100

    def test_acquisition_year_returns_original(self):
        apt = make_asset(
            valor_adquisicion=300_000_000,
            fecha_adquisicion=date(2021, 6, 15),
            tasa_anual=0.08,
        )
        value = calcular_valor_activo_en_mes(apt, 2021, 12)
        assert value == 300_000_000

    def test_asset_with_linea_recta_depreciation(self):
        """Vehicle: 80M, acquired 2020, 10-year straight-line, salvage 10M."""
        car = make_asset(
            valor_adquisicion=80_000_000,
            fecha_adquisicion=date(2020, 1, 1),
            tasa_anual=0.0,
            depreciation_method="linea_recta",
            depreciation_rate=None,
            depreciation_years=10,
            depreciation_salvage_value=10_000_000,
            depreciation_start_date=date(2020, 1, 1),
        )
        value = calcular_valor_activo_en_mes(car, 2025, 1)
        assert abs(value - 45_000_000) < 500_000

    def test_asset_with_saldo_decreciente(self):
        """Vehicle: 80M, rate 20%/year, declining balance."""
        car = make_asset(
            valor_adquisicion=80_000_000,
            fecha_adquisicion=date(2020, 1, 1),
            tasa_anual=0.0,
            depreciation_method="saldo_decreciente",
            depreciation_rate=20.0,
            depreciation_years=None,
            depreciation_salvage_value=0,
            depreciation_start_date=date(2020, 1, 1),
        )
        value = calcular_valor_activo_en_mes(car, 2025, 1)
        expected = 80_000_000 * (0.8 ** 5)
        assert abs(value - expected) < 500_000

    def test_asset_with_doble_saldo_decreciente(self):
        """Vehicle: 80M, 10-year life, double declining."""
        car = make_asset(
            valor_adquisicion=80_000_000,
            fecha_adquisicion=date(2020, 1, 1),
            tasa_anual=0.0,
            depreciation_method="doble_saldo_decreciente",
            depreciation_rate=None,
            depreciation_years=10,
            depreciation_salvage_value=0,
            depreciation_start_date=date(2020, 1, 1),
        )
        value = calcular_valor_activo_en_mes(car, 2025, 1)
        expected = 80_000_000 * (0.8 ** 5)
        assert abs(value - expected) < 500_000

    def test_asset_appreciation_plus_depreciation(self):
        """Asset with both appreciation and depreciation applied."""
        asset = make_asset(
            valor_adquisicion=100_000_000,
            fecha_adquisicion=date(2020, 1, 1),
            tasa_anual=0.05,
            depreciation_method="linea_recta",
            depreciation_years=20,
            depreciation_salvage_value=0,
            depreciation_start_date=date(2020, 1, 1),
        )
        value = calcular_valor_activo_en_mes(asset, 2025, 1)
        assert value > 0
        assert value < 100_000_000

    def test_no_depreciation_method_returns_appreciated(self):
        """sin_depreciacion should not reduce value."""
        asset = make_asset(
            valor_adquisicion=100_000_000,
            fecha_adquisicion=date(2020, 1, 1),
            tasa_anual=0.10,
            depreciation_method="sin_depreciacion",
        )
        value = calcular_valor_activo_en_mes(asset, 2025, 1)
        expected = 100_000_000 * (1.10 ** 4)
        assert abs(value - expected) < 1

    def test_before_acquisition_returns_zero(self):
        apt = make_asset(
            valor_adquisicion=300_000_000,
            fecha_adquisicion=date(2021, 6, 15),
            tasa_anual=0.08,
        )
        assert calcular_valor_activo_en_mes(apt, 2021, 5) == 0.0
        assert calcular_valor_activo_en_mes(apt, 2020, 1) == 0.0

    def test_year_after_acquisition_exponent_zero(self):
        apt = make_asset(
            valor_adquisicion=100_000_000,
            fecha_adquisicion=date(2021, 1, 1),
            tasa_anual=0.10,
        )
        value = calcular_valor_activo_en_mes(apt, 2022, 6)
        assert value == 100_000_000


# ── Debt balance tests (using Debt model field names) ─────────────────


class TestDebtBalance:
    def test_mortgage_jan_2025(self):
        """Mortgage: 240M, 12% annual, 180 months, start 2021-06."""
        mortgage = make_debt(
            original_amount=240_000_000,
            interest_rate=12.0,
            term_months=180,
            start_date=date(2021, 6, 1),
        )
        balance = saldo_deuda_en_mes(mortgage, 2025, 1)
        assert abs(balance - 214_347_528) < 500_000

    def test_consumer_loan_jan_2025(self):
        """Consumer: 15M, 18% annual, 36 months, start 2023-01."""
        loan = make_debt(
            original_amount=15_000_000,
            interest_rate=18.0,
            term_months=36,
            start_date=date(2023, 1, 1),
        )
        balance = saldo_deuda_en_mes(loan, 2025, 1)
        assert abs(balance - 5_914_987) < 500_000

    def test_balance_at_start(self):
        debt = make_debt(original_amount=10_000_000, start_date=date(2024, 1, 1))
        assert saldo_deuda_en_mes(debt, 2024, 1) == 10_000_000

    def test_balance_before_start(self):
        debt = make_debt(original_amount=10_000_000, start_date=date(2024, 1, 1))
        assert saldo_deuda_en_mes(debt, 2023, 6) == 10_000_000

    def test_balance_after_full_term(self):
        debt = make_debt(
            original_amount=10_000_000,
            interest_rate=12.0,
            term_months=12,
            start_date=date(2024, 1, 1),
        )
        assert saldo_deuda_en_mes(debt, 2025, 6) == 0.0

    def test_zero_rate_balance(self):
        debt = make_debt(
            original_amount=12_000_000,
            interest_rate=0.0,
            term_months=12,
            start_date=date(2024, 1, 1),
        )
        balance = saldo_deuda_en_mes(debt, 2024, 7)
        assert abs(balance - 6_000_000) < 1

    def test_loan_years_fallback(self):
        """term_months=None but loan_years=15 should work."""
        debt = make_debt(
            original_amount=100_000_000,
            interest_rate=10.0,
            term_months=None,
            loan_years=15,
            start_date=date(2020, 1, 1),
        )
        balance = saldo_deuda_en_mes(debt, 2025, 1)
        assert 0 < balance < 100_000_000


# ── Net worth / patrimonio tests ─────────────────────────────────────


class TestPatrimonio:
    def _make_test_portfolio(self):
        apt = make_asset(
            valor_adquisicion=300_000_000,
            fecha_adquisicion=date(2021, 6, 15),
            tasa_anual=0.08,
        )
        car = make_asset(
            valor_adquisicion=80_000_000,
            fecha_adquisicion=date(2020, 3, 10),
            tasa_anual=-0.12,
        )
        mortgage = make_debt(
            original_amount=240_000_000,
            interest_rate=12.0,
            term_months=180,
            start_date=date(2021, 6, 1),
        )
        loan = make_debt(
            original_amount=15_000_000,
            interest_rate=18.0,
            term_months=36,
            start_date=date(2023, 1, 1),
        )
        return [apt, car], [mortgage, loan]

    def test_net_worth_jan_2025(self):
        activos, deudas = self._make_test_portfolio()
        result = calcular_patrimonio_en_mes(activos, deudas, 2025, 1)

        assert abs(result["total_activos"] - 425_889_229) < 1_000_000
        assert abs(result["total_deudas"] - 220_262_515) < 1_000_000
        assert abs(result["patrimonio_neto"] - 205_626_714) < 1_000_000

    def test_empty_arrays(self):
        result = calcular_patrimonio_en_mes([], [], 2025, 1)
        assert result["total_activos"] == 0
        assert result["total_deudas"] == 0
        assert result["patrimonio_neto"] == 0


# ── Timeline tests ───────────────────────────────────────────────────


class TestTimeline:
    def test_timeline_length(self):
        asset = make_asset()
        debt = make_debt()
        tl = timeline_patrimonio([asset], [debt], 2024, 1, 2024, 12)
        assert len(tl) == 12

    def test_timeline_ordering(self):
        asset = make_asset()
        debt = make_debt()
        tl = timeline_patrimonio([asset], [debt], 2024, 6, 2025, 6)
        assert len(tl) == 13
        assert tl[0]["año"] == 2024 and tl[0]["mes"] == 6
        assert tl[-1]["año"] == 2025 and tl[-1]["mes"] == 6

    def test_timeline_single_month(self):
        tl = timeline_patrimonio([], [], 2025, 3, 2025, 3)
        assert len(tl) == 1


# ── Depreciation function tests ──────────────────────────────────────


class TestDepreciacion:
    def test_linea_recta(self):
        result = aplicar_depreciacion(
            valor=100_000,
            method="linea_recta",
            rate=None,
            years=10,
            salvage_value=10_000,
            start_date=date(2020, 1, 1),
            reference_date=date(2025, 1, 1),
        )
        assert abs(result - 55_000) < 500

    def test_saldo_decreciente(self):
        result = aplicar_depreciacion(
            valor=100_000,
            method="saldo_decreciente",
            rate=20.0,
            years=None,
            salvage_value=0,
            start_date=date(2020, 1, 1),
            reference_date=date(2025, 1, 1),
        )
        expected = 100_000 * (0.8 ** 5)
        assert abs(result - expected) < 500

    def test_doble_saldo_decreciente(self):
        result = aplicar_depreciacion(
            valor=100_000,
            method="doble_saldo_decreciente",
            rate=None,
            years=10,
            salvage_value=0,
            start_date=date(2020, 1, 1),
            reference_date=date(2025, 1, 1),
        )
        expected = 100_000 * (0.8 ** 5)
        assert abs(result - expected) < 500

    def test_sin_depreciacion(self):
        result = aplicar_depreciacion(
            valor=100_000,
            method="sin_depreciacion",
            rate=None,
            years=None,
            salvage_value=None,
            start_date=date(2020, 1, 1),
            reference_date=date(2025, 1, 1),
        )
        assert result == 100_000

    def test_before_start_date(self):
        result = aplicar_depreciacion(
            valor=100_000,
            method="linea_recta",
            rate=None,
            years=10,
            salvage_value=0,
            start_date=date(2025, 1, 1),
            reference_date=date(2020, 1, 1),
        )
        assert result == 100_000

    def test_salvage_value_floor(self):
        result = aplicar_depreciacion(
            valor=100_000,
            method="linea_recta",
            rate=None,
            years=5,
            salvage_value=30_000,
            start_date=date(2015, 1, 1),
            reference_date=date(2025, 1, 1),
        )
        assert abs(result - 30_000) < 500
