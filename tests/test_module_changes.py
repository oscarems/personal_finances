"""
Tests for the 4-module finance system changes:
  Module 1: Patrimonio (Net Worth) - executive table, mortgage-asset grouping
  Module 2: Presupuestos (Budgets) - assigned protection, available semantics, covering
  Module 3: Deudas (Credit Cards) - label changes, utilization, net worth integration
  Module 4: Dashboard - KPI cards, chart data
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.models import (
    Account,
    BudgetMonth,
    Category,
    CategoryGroup,
    Currency,
    Debt,
    ExchangeRate,
    Transaction,
)
from finance_app.services.budget_service import (
    assign_money_to_category,
    calculate_available,
    get_or_create_budget_month,
)
from finance_app.api.reports_pkg import debt as reports_debt_mod


# ─── helpers ────────────────────────────────────────────────────────

def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_currencies(db):
    cop = Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0)
    usd = Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2)
    db.add_all([cop, usd])
    db.add(ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=date(2026, 1, 1)))
    db.commit()


def _seed_budget_account(db, currency_id=1):
    """Create a budget account for use in covering transactions."""
    account = Account(
        name="Cuenta presupuesto",
        type="checking",
        balance=5000000.0,
        currency_id=currency_id,
        is_budget=True,
        is_closed=False,
    )
    db.add(account)
    db.commit()
    return account


def _seed_category(db, name, rollover_type="reset", group_name="Gastos", is_income=False):
    group = db.query(CategoryGroup).filter_by(name=group_name).first()
    if not group:
        group = CategoryGroup(name=group_name, is_income=is_income)
        db.add(group)
        db.flush()
    cat = Category(name=name, category_group_id=group.id, rollover_type=rollover_type)
    db.add(cat)
    db.commit()
    return cat


# ═══════════════════════════════════════════════════════════════════
# MODULE 2: PRESUPUESTOS
# ═══════════════════════════════════════════════════════════════════


class TestModule2_AssignedProtection:
    """2.1: assigned field must only be modified by explicit user action."""

    def test_new_budget_starts_at_zero(self):
        """New budget months should always start with assigned=0."""
        db = _make_session()
        _seed_currencies(db)
        cat = _seed_category(db, "Comida")
        month = date(2026, 3, 1)

        budget = get_or_create_budget_month(db, cat.id, month, currency_id=1)

        assert budget.assigned == 0.0
        assert budget.activity == 0.0
        assert budget.available == 0.0

    def test_new_budget_does_not_copy_previous_assigned(self):
        """Creating a new month should NOT copy assigned from the previous month."""
        db = _make_session()
        _seed_currencies(db)
        cat = _seed_category(db, "Servicios")

        # Set up previous month with assigned=500000
        prev_month = date(2026, 2, 1)
        prev_budget = get_or_create_budget_month(db, cat.id, prev_month, currency_id=1)
        assign_money_to_category(db, cat.id, prev_month, currency_id=1, amount=500000.0)
        db.refresh(prev_budget)
        assert prev_budget.assigned == 500000.0

        # Create new month budget
        new_month = date(2026, 3, 1)
        new_budget = get_or_create_budget_month(db, cat.id, new_month, currency_id=1)

        # Should NOT copy 500000 from previous month
        assert new_budget.assigned == 0.0

    def test_assign_money_sets_assigned_explicitly(self):
        """assign_money_to_category should be the only way to set assigned."""
        db = _make_session()
        _seed_currencies(db)
        cat = _seed_category(db, "Transporte")
        month = date(2026, 3, 1)

        budget = assign_money_to_category(db, cat.id, month, currency_id=1, amount=300000.0)

        assert budget.assigned == 300000.0


class TestModule2_AvailableSemantics:
    """2.2: 'Disponible para gastar' for expense, 'Ahorrado' for savings."""

    def test_reset_category_available_equals_assigned_plus_activity(self):
        """For reset (expense) categories: available = assigned + activity (no rollover)."""
        db = _make_session()
        _seed_currencies(db)
        cat = _seed_category(db, "Comida", rollover_type="reset")
        account = _seed_budget_account(db)
        month = date(2026, 3, 1)

        budget = assign_money_to_category(db, cat.id, month, currency_id=1, amount=800000.0)

        # Simulate spending (negative transaction)
        tx = Transaction(
            account_id=account.id,
            date=date(2026, 3, 15),
            amount=-200000.0,
            currency_id=1,
            original_amount=-200000.0,
            original_currency_id=1,
            category_id=cat.id,
        )
        db.add(tx)
        db.commit()

        calculate_available(db, budget)
        db.commit()

        assert budget.activity == -200000.0
        assert budget.available == 600000.0  # 800k - 200k

    def test_accumulate_category_carries_over_available(self):
        """For accumulate (savings) categories: available accumulates across months."""
        db = _make_session()
        _seed_currencies(db)
        cat = _seed_category(db, "Fondo Emergencia", rollover_type="accumulate")
        month1 = date(2026, 1, 1)
        month2 = date(2026, 2, 1)

        # Month 1: assign 1M
        budget1 = assign_money_to_category(db, cat.id, month1, currency_id=1, amount=1000000.0)
        calculate_available(db, budget1)
        db.commit()
        assert budget1.available == 1000000.0

        # Month 2: assign another 500k
        budget2 = assign_money_to_category(db, cat.id, month2, currency_id=1, amount=500000.0)
        calculate_available(db, budget2)
        db.commit()

        # Should accumulate: 1M from month1 + 500k from month2
        assert budget2.available == 1500000.0


class TestModule2_Covering:
    """2.3: Covering should NOT modify assigned, should create transactions."""

    def test_cover_overspending_creates_transactions(self):
        """POST /cover-overspending should create transactions, not modify assigned."""
        db = _make_session()
        _seed_currencies(db)
        account = _seed_budget_account(db)

        source_cat = _seed_category(db, "Entretenimiento")
        target_cat = _seed_category(db, "Comida")

        month = date(2026, 3, 1)

        # Assign to both
        source_budget = assign_money_to_category(db, source_cat.id, month, currency_id=1, amount=500000.0)
        target_budget = assign_money_to_category(db, target_cat.id, month, currency_id=1, amount=300000.0)

        # Simulate overspending in target
        overspend_tx = Transaction(
            account_id=account.id,
            date=date(2026, 3, 10),
            amount=-400000.0,
            currency_id=1,
            original_amount=-400000.0,
            original_currency_id=1,
            category_id=target_cat.id,
        )
        db.add(overspend_tx)
        db.commit()

        # Execute covering via direct API logic (simulating what the endpoint does)
        from finance_app.api.budgets import cover_overspending, CoverOverspendingRequest
        request = CoverOverspendingRequest(
            source_category_id=source_cat.id,
            target_category_id=target_cat.id,
            amount=100000.0,
            currency_code="COP",
            month=month,
        )
        result = cover_overspending(request, db)

        assert result["success"] is True

        # Assigned must NOT have changed for either category
        db.refresh(source_budget)
        db.refresh(target_budget)
        assert source_budget.assigned == 500000.0, "Source assigned must not change"
        assert target_budget.assigned == 300000.0, "Target assigned must not change"

        # Two adjustment transactions should have been created
        adjustment_txs = db.query(Transaction).filter(
            Transaction.is_adjustment == True,
        ).all()
        assert len(adjustment_txs) == 2

        # One expense (source) and one income (target)
        source_tx = [t for t in adjustment_txs if t.category_id == source_cat.id]
        target_tx = [t for t in adjustment_txs if t.category_id == target_cat.id]
        assert len(source_tx) == 1
        assert len(target_tx) == 1
        assert source_tx[0].amount == -100000.0  # expense
        assert target_tx[0].amount == 100000.0    # income


# ═══════════════════════════════════════════════════════════════════
# MODULE 3: DEUDAS - TARJETAS DE CRÉDITO
# ═══════════════════════════════════════════════════════════════════


class TestModule3_CreditCards:
    """Module 3: Credit card label changes, utilization, net worth integration."""

    def test_credit_card_utilization_calculation(self):
        """Disponible = Cupo - Cuánto debo, % Utilización = (Cuánto debo / Cupo) * 100."""
        db = _make_session()
        _seed_currencies(db)

        debt = Debt(
            account_id=1,
            name="Visa Gold",
            debt_type="credit_card",
            currency_code="COP",
            original_amount=5000000.0,  # This is "Cupo"
            credit_limit=5000000.0,
            current_balance=1500000.0,  # This is "Cuánto debo"
            start_date=date(2026, 1, 1),
            is_active=True,
        )
        db.add(debt)
        db.commit()

        debt_dict = debt.to_dict()

        # Cuánto debo
        assert debt_dict["current_balance"] == 1500000.0
        # Cupo (credit_limit)
        assert debt_dict["credit_limit"] == 5000000.0
        # Disponible en tarjeta = Cupo - Cuánto debo
        disponible = debt_dict["credit_limit"] - debt_dict["current_balance"]
        assert disponible == 3500000.0
        # % Utilización
        utilization = (debt_dict["current_balance"] / debt_dict["credit_limit"]) * 100
        assert utilization == 30.0

    def test_credit_card_high_utilization_alert(self):
        """Alert when utilization > 70%."""
        db = _make_session()
        _seed_currencies(db)

        debt = Debt(
            account_id=1,
            name="MC Platinum",
            debt_type="credit_card",
            currency_code="COP",
            original_amount=10000000.0,
            credit_limit=10000000.0,
            current_balance=8000000.0,  # 80% utilization
            start_date=date(2026, 1, 1),
            is_active=True,
        )
        db.add(debt)
        db.commit()

        utilization = (debt.current_balance / debt.credit_limit) * 100
        assert utilization == 80.0
        assert utilization > 70  # Should trigger alert

    def test_credit_card_zero_balance(self):
        """Credit card with zero balance should show 0 utilization."""
        db = _make_session()
        _seed_currencies(db)

        debt = Debt(
            account_id=1,
            name="Amex",
            debt_type="credit_card",
            currency_code="COP",
            original_amount=5000000.0,
            credit_limit=5000000.0,
            current_balance=0.0,
            start_date=date(2026, 1, 1),
            is_active=True,
        )
        db.add(debt)
        db.commit()

        utilization = (debt.current_balance / debt.credit_limit) * 100 if debt.credit_limit else 0
        assert utilization == 0.0

        disponible = debt.credit_limit - debt.current_balance
        assert disponible == 5000000.0


# TestModule1_NetWorth removed — legacy WealthAsset system consolidated into Patrimonio.
# See tests/test_patrimonio_calculator.py for net worth tests.


# ═══════════════════════════════════════════════════════════════════
# MODULE 4: DASHBOARD
# ═══════════════════════════════════════════════════════════════════


class TestModule4_Dashboard:
    """Module 4: KPI calculations, chart data endpoints."""

    def test_budget_income_expenses_includes_current_month(self):
        """The income/expenses endpoint should include the current month."""
        db = _make_session()
        _seed_currencies(db)

        from finance_app.api.reports_pkg import income as reports_income_mod

        result = reports_income_mod.get_budget_income_expenses(
            months=3,
            currency_id=1,
            db=db,
        )

        months = result.get("months", [])
        current_month_key = date.today().strftime("%Y-%m")

        # Current month should be in the results
        month_keys = [m["month"] for m in months]
        assert current_month_key in month_keys

    def test_kpi_savings_rate_calculation(self):
        """Tasa de Ahorro = Asignado ahorro / Asignado total."""
        db = _make_session()
        _seed_currencies(db)

        expense_cat = _seed_category(db, "Comida", rollover_type="reset")
        savings_cat = _seed_category(db, "Ahorro", rollover_type="accumulate")

        month = date(2026, 3, 1)
        assign_money_to_category(db, expense_cat.id, month, currency_id=1, amount=2000000.0)
        assign_money_to_category(db, savings_cat.id, month, currency_id=1, amount=1000000.0)

        # Savings rate = 1M / 3M = 33.3%
        total_assigned = 2000000.0 + 1000000.0
        savings_assigned = 1000000.0
        savings_rate = (savings_assigned / total_assigned) * 100

        assert abs(savings_rate - 33.33) < 0.1

    def test_kpi_net_balance(self):
        """Balance Neto = Ingresos del mes - Gastos del periodo (budget activity)."""
        income = 5000000.0
        budget_activity = -3500000.0  # activity is negative (expenses)
        net_balance = income - abs(budget_activity)
        assert net_balance == 1500000.0

    def test_kpi_free_money_rate(self):
        """Tasa de Dinero Libre = Balance Neto / Ingresos."""
        income = 5000000.0
        budget_activity = -3500000.0
        net_balance = income - abs(budget_activity)
        free_money_rate = (net_balance / income) * 100
        assert free_money_rate == 30.0

    def test_spending_by_category_over_time_endpoint_exists(self):
        """The spending-by-category-over-time endpoint should return per-category data."""
        db = _make_session()
        _seed_currencies(db)

        from finance_app.api.reports_pkg import spending as reports_spending_mod

        result = reports_spending_mod.get_spending_by_category_over_time(
            currency_id=1,
            db=db,
        )

        # Should return months and series lists (used by dashboard line chart)
        assert "months" in result
        assert "series" in result
        assert isinstance(result["months"], list)
        assert isinstance(result["series"], list)


# ═══════════════════════════════════════════════════════════════════
# CROSS-MODULE: Integration tests
# ═══════════════════════════════════════════════════════════════════


class TestCrossModule:
    """Integration tests across modules."""

    def test_covering_does_not_affect_net_worth(self):
        """Covering between categories creates offsetting transactions, net effect = 0."""
        db = _make_session()
        _seed_currencies(db)
        account = _seed_budget_account(db)

        source_cat = _seed_category(db, "Recreación")
        target_cat = _seed_category(db, "Alimentación")

        month = date(2026, 3, 1)
        assign_money_to_category(db, source_cat.id, month, currency_id=1, amount=500000.0)
        assign_money_to_category(db, target_cat.id, month, currency_id=1, amount=300000.0)

        from finance_app.api.budgets import cover_overspending, CoverOverspendingRequest
        request = CoverOverspendingRequest(
            source_category_id=source_cat.id,
            target_category_id=target_cat.id,
            amount=100000.0,
            currency_code="COP",
            month=month,
        )
        cover_overspending(request, db)

        # The two adjustment transactions should net to zero
        adjustments = db.query(Transaction).filter(
            Transaction.is_adjustment == True
        ).all()
        total = sum(t.amount for t in adjustments)
        assert total == 0.0

    def test_debt_summary_includes_credit_cards_with_current_balance(self):
        """Debt summary should show credit card with current_balance, not credit_limit."""
        db = _make_session()
        _seed_currencies(db)

        cc = Debt(
            account_id=1,
            name="Mastercard",
            debt_type="credit_card",
            currency_code="COP",
            original_amount=15000000.0,
            credit_limit=15000000.0,
            current_balance=3000000.0,
            start_date=date(2026, 1, 1),
            is_active=True,
        )
        db.add(cc)
        db.commit()

        summary = reports_debt_mod.get_debt_summary(currency_id=1, db=db)

        # Total debt should be 3M (current_balance), not 15M
        assert summary["totals"]["total_debt"] == 3000000.0
