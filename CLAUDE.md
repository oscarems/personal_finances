# CLAUDE.md — Personal Finances

## Stack & Commands

```bash
# Run
python run.py

# Test (full suite)
pytest tests/ -v

# Test (financial calculators only — run before ANY calculator change)
pytest tests/test_amortization*.py tests/test_patrimonio*.py tests/test_calculators*.py -v

# Lint
ruff check . && ruff format --check .

# DB migration (NO Alembic — manual scripts only)
python scripts/migrate_db.py
```

**Stack:** Python · FastAPI · SQLite · Jinja2 · Tailwind · vanilla JS · no frontend build pipeline.

---

## Architecture

```
models → services/calculators → api routers → templates
```

- Monolithic, server-rendered, desktop-first. No SPA, no microservices.
- Business logic lives in services/calculators, never in routers or templates.
- COP = base currency. USD = secondary. All conversions via exchange rate services only.

---

## Financial Precision Rules

- DB money columns: `Numeric(18, 2)` — NEVER `Float`.
- Python calcs: currently `float` (known tech debt). Do NOT introduce more float-based financial logic. New critical calculators → use `Decimal`.
- Debt balances in patrimonio always from: `AmortizationEngine.balance_as_of(..., mode="hybrid")`

---

## Source of Truth

```
Transactions → Calculated Balances → Reports / Patrimonio / Cash Flow
```

Manual reconciliations are authoritative checkpoints. Recalculation MUST NOT override balances after a reconciliation date. Never silently mutate historical balances.

---

## Always / Never

**Always:**
- Ask questions before implementing if requirements are ambiguous.
- Inspect existing templates before creating UI — reuse existing patterns.
- Use CSS variables and semantic classes (`design-system.css`).
- Use `SimpleNamespace`/dataclasses for mocks in calculator tests (no DB deps).
- Include currency metadata in all reports.

**Never:**
- Use `Float` for money in DB schema.
- Use inline styles or hardcoded colors in templates.
- Introduce React, Vue, or any frontend build system.
- Modify `amortization_engine.py` without running its full test suite first.
- Use Alembic — schema changes use `scripts/migrate_db.py` only (SQLite simplicity is intentional, not an oversight).
- Create new UI components if an equivalent pattern exists in the design system.

---

## Protected Files — High Risk

```
services/debt/amortization_engine.py   ← affects debt, patrimonio, cash flow, projections
services/patrimonio/calculator.py
database.py
models/
scripts/migrate_db.py
static/styles/design-system.css
.env
```

Changes to protected files require explicit user approval.

---

## Approval Required Before

Schema changes · file renames/moves · public API signature changes · new dependencies · deleting tests · `.env` edits · large refactors · rewriting financial formulas.

When in doubt: **STOP and ask.**

---

## Verification Checklist (before marking a task done)

1. Run relevant test suite (see Commands above).
2. If touching a financial calculator → run full calculator tests + spot-check with hardcoded expected values.
3. If touching UI → confirm no inline styles, no hardcoded colors, existing design-system classes used.
4. If touching DB schema → confirm `migrate_db.py` updated and backward compatibility preserved.
5. If touching patrimonio or cash flow → confirm `amortization_engine.py` was NOT modified without tests passing.

---

## Why These Decisions Exist

| Decision | Why |
|---|---|
| SQLite, no Alembic | Single-user system; simplicity over tooling overhead; manual scripts give full control |
| No soft-delete | Reduces complexity; hard delete is sufficient for a personal system |
| Float tech debt | Introduced before Decimal discipline was enforced; don't expand it, migrate incrementally |
| No formal month-close | Reports recalculate dynamically; reconciliation checkpoints serve the same purpose |
| Jinja2 server-render | Desktop-only personal tool; SSR is simpler and sufficient |

---

## Debt System Scope

Supported: `mortgage` · `credit_loan` · `credit_card`

Out of scope (do not implement without discussion): UVR / inflation-indexed loans · late-interest calc · daily accrual · revolving credit simulation · installment credit-card engine.

→ Full debt semantics: `@docs/debt-system.md`
→ Frontend conventions: `@docs/frontend-conventions.md`
→ Current sprint / active work: `@MEMORY.md`

---

## Anti-patterns (errores recurrentes — llenar según experiencia)

<!-- Agrega aquí los errores que Claude repite. Ejemplo:
- NEVER suggest using Alembic — already decided against it.
- NEVER put query logic inside Jinja2 templates.
- NEVER create a new CSS component when card/button/table pattern already exists.
-->