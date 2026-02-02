-- Migration: add mortgage payment allocations and mortgage balance fields

CREATE TABLE IF NOT EXISTS mortgage_payment_allocations (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    loan_id INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    payment_date DATE NOT NULL,
    period VARCHAR(20),
    notes TEXT,
    interest_paid NUMERIC(18, 6) NOT NULL,
    principal_paid NUMERIC(18, 6) NOT NULL,
    fees_paid NUMERIC(18, 6) NOT NULL DEFAULT 0,
    escrow_paid NUMERIC(18, 6) NOT NULL DEFAULT 0,
    extra_principal_paid NUMERIC(18, 6) NOT NULL DEFAULT 0,
    currency_code VARCHAR(3) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mortgage_payment_allocation_tx_loan UNIQUE (transaction_id, loan_id)
);

ALTER TABLE debts ADD COLUMN principal_balance NUMERIC(18, 6);
ALTER TABLE debts ADD COLUMN interest_balance NUMERIC(18, 6);
ALTER TABLE debts ADD COLUMN annual_interest_rate NUMERIC(10, 6);
ALTER TABLE debts ADD COLUMN term_months INTEGER;
ALTER TABLE debts ADD COLUMN next_due_date DATE;
ALTER TABLE debts ADD COLUMN last_accrual_date DATE;
