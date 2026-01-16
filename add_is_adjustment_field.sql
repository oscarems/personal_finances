-- Migration: Add is_adjustment field to transactions table
-- Date: 2026-01-16
-- Description: Adds a boolean field to identify balance adjustment transactions

-- Add the is_adjustment column with default value False
ALTER TABLE transactions ADD COLUMN is_adjustment BOOLEAN DEFAULT FALSE;

-- Update the column to be NOT NULL after setting defaults
ALTER TABLE transactions ALTER COLUMN is_adjustment SET NOT NULL;

-- Optional: Create an index if you need to filter by adjustment type frequently
-- CREATE INDEX idx_transactions_is_adjustment ON transactions(is_adjustment);
