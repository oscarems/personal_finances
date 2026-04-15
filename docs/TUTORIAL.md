# User Guide - Personal Finances

**A multi-currency personal finance system**

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Key Concepts](#key-concepts)
4. [Accounts](#accounts)
5. [Budget](#budget)
6. [Transactions](#transactions)
7. [Transfers](#transfers)
8. [Net Worth (Patrimonio)](#net-worth-patrimonio)
9. [Debts](#debts)
10. [Reports](#reports)
11. [Importing from CSV](#importing-from-csv)
12. [Recurring Transactions](#recurring-transactions)
13. [Multi-Currency](#multi-currency)
14. [Tips and Best Practices](#tips-and-best-practices)
15. [Troubleshooting](#troubleshooting)

---

## Introduction

The budgeting philosophy is simple:

**"Give every peso a purpose"**

Instead of looking back asking "Where did my money go?", you look forward: "What do I need this money to do before I get paid again?"

---

## Getting Started

### 1. Start the System

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python src/finance_app/scripts/init_db.py

# Start server
python run.py
```

The server will be available at `http://localhost:8000`

### 2. First Access

The app opens directly (no authentication required). You will see:
- A dashboard with a summary
- A sidebar with navigation links

---

## Key Concepts

### 1. **Ready to Assign**
Money you have in your accounts that has **no assigned purpose** yet.

**Formula:**
```
Ready to Assign = Total in Accounts - Total Assigned in Budget
```

**Goal:** Bring this to $0 by assigning every peso to a category.

### 2. **Categories with Rollover**
Two types:

**Reset:**
- Unspent money returns to "Ready to Assign" next month
- Use for regular monthly expenses (groceries, utilities)

**Accumulate:**
- Unspent money stays in the category
- Use for savings and goals (vacation, emergency fund)

### 3. **Four Rules**

1. **Give Every Dollar a Job**: Assign every peso to a category
2. **Embrace Your True Expenses**: Plan for irregular expenses
3. **Roll With The Punches**: Adjust your budget when things change
4. **Age Your Money**: Try to live on last month's money

---

## Accounts

### Supported Account Types

| Type | Description | Special Fields |
|------|-------------|----------------|
| Checking | Daily bank account | — |
| Savings | Savings account | Interest rate |
| Credit Card | Credit card | Credit limit, payment due day |
| Personal Loan | Personal loan | Rate, monthly payment, original amount |
| Mortgage | Home loan | Rate, monthly payment, original amount |
| CDT | Certificate of deposit | Rate, maturity date, original amount |
| Investment | Investment account | — |
| Cash | Physical cash | — |

### Creating an Account

1. Go to **"Accounts"**
2. Click **"+ New Account"**
3. Fill in:
   - **Name**: e.g., "Davivienda Checking"
   - **Type**: Select from the list
   - **Currency**: COP or USD
   - **Initial Balance**: Current balance of the account
   - **Optional fields**: Depending on account type
4. Click **"Save"**

**Important:**
- Each account has **one official currency**
- Conversion to the other currency is shown automatically
- Check "Include in budget" for regular accounts
- Uncheck for tracking accounts (investments, mortgages)

---

## Budget

### Structure

**Category Groups** → **Categories**

Example:
```
Needs (Group)
   ├─ Gym (Category)
   ├─ Personal care
   └─ Transportation

Home (Group)
   ├─ Rent
   ├─ Groceries
   └─ Utilities
```

### Assigning Money

1. Go to **"Budget"**
2. Check your **"Ready to Assign"** (at the top)
3. Click on a category
4. Enter the amount to assign
5. Click **"Assign"**

### Budget Columns

| Column | Meaning |
|--------|---------|
| **Assigned** | Money you planned to spend |
| **Spent** | Money actually spent |
| **Available** | What remains (Assigned - Spent) |

**Progress bar:**
- Green: < 80% spent
- Yellow: 80–100% spent
- Red: > 100% spent (overspent!)

### Currency Selector

In the top right you can toggle between COP and USD:
- Does **NOT** separate the budgets
- Only changes how amounts are **displayed**
- Sums assignments from both currencies after conversion

**Example:**
If you assign:
- $100 USD to "Groceries"
- $400,000 COP to "Groceries"

Viewing in COP you see: **~$800,000 COP** (sum after conversion at current rate)

---

## Transactions

### Creating a Transaction

1. Go to **"Transactions"**
2. Click **"+ New Transaction"**
3. Fill in:
   - **Date**: Transaction date
   - **Account**: Which account it comes from/goes to
   - **Payee**: e.g., "Éxito", "My Employer"
   - **Category**: Which category it belongs to
   - **Amount**:
     - Positive = Income
     - Negative = Expense
   - **Currency**: COP or USD
   - **Memo**: Optional notes
4. Check **"Reconciled"** if you have confirmed it with your bank
5. Click **"Save"**

### Transaction Types

**Income (positive amount):**
```
Account: Davivienda Checking
Payee: My Employer
Category: Salary (income category)
Amount: +5,000,000 COP
```

**Expense (negative amount):**
```
Account: Davivienda Checking
Payee: Éxito
Category: Groceries
Amount: -150,000 COP
```

---

## Transfers

### When to Use Transfers

When moving money **between your own accounts**:
- Savings → Checking
- USD → COP
- Cash → Bank

**Do NOT use transfers for:**
- Payments to third parties
- Purchases
- Income

### Creating a Transfer

1. Go to **"Transactions"**
2. Click **"New Transfer"**
3. Fill in:
   - **Date**: Transfer date
   - **From**: Source account
   - **Source currency**: COP or USD
   - **To**: Destination account
   - **Destination currency**: COP or USD
   - **Amount**: Amount to transfer (in source currency)
   - **Memo**: Optional
4. Click **"Create Transfer"**

**Auto-magic:**
- Creates 2 linked transactions:
  - Outflow (-) from source account
  - Inflow (+) at destination account
- If currencies differ, **automatically converts**
- Deleting one deletes both

**Example:**
```
From: USD Savings ($100 USD)
To: COP Checking
Result:
  - USD Savings: -$100 USD
  - COP Checking: +$400,000 COP (at rate 4000)
```

---

## Net Worth (Patrimonio)

The unified net worth system. Tracks both assets and long-term debts.

### Assets

**Asset types:**
- `inmueble`: Real estate (apartment, house, land)
- `vehiculo`: Vehicles (car, motorcycle)
- `otro`: Other assets (equipment, art, etc.)

**Valuation:**
- Valued annually from the acquisition date
- Formula: `value = acquisition_value * (1 + annual_rate) ^ max(0, year - acquisition_year - 1)`
- Acquisition year returns the original value

**Depreciation methods:**
- Straight-line (`linea_recta`)
- Declining balance (`saldo_decreciente`)
- Double declining balance (`doble_saldo_decreciente`)

### Debts in Net Worth

- Patrimonio reads debts directly from the `/debts` module (no duplication)
- Includes: mortgages and personal loans
- Excludes: credit cards (managed separately in `/debts`)
- Uses the hybrid amortization engine (real payments + projections)

### Net Worth Timeline

- Dashboard shows 24 months past + 24 months future
- Charts assets, debts, and net worth over time

---

## Debts

### Debt Types

| Type | Description |
|------|-------------|
| `mortgage` | Home mortgage |
| `credit_loan` | Personal/consumer loan |
| `credit_card` | Credit card |

### Amortization Engine

The hybrid engine calculates balances using:
1. **Real payments**: Recorded `DebtPayment` entries
2. **Projected payments**: Future payments based on the amortization schedule

This gives accurate current balances even without entering every payment.

### Interest Rate Conventions

- **Colombia (EA)**: Effective annual rate → `monthly = (1 + annual)^(1/12) - 1`
- **US (APR)**: Nominal rate → `monthly = annual / 12`
- Document the convention used in `debt.notes`

---

## Reports

### Report Types

1. **Spending by Category** — Pie chart of your expenses; filter by date and category
2. **Spending by Group** — Expenses grouped by category group
3. **Spending Trends** — How spending changes over time
4. **Income vs Expenses** — Monthly comparison; filter by date range
5. **Budget vs Actual** — Planned vs real for each category
6. **Savings Rate** — What percentage of income you saved
7. **Balance Trend** — Account balance evolution
8. **Debt Summary** — Debt balances and payoff projections

All reports support multi-currency: you can view everything in COP or USD, with automatic conversion applied.

---

## Importing from CSV

### Prepare Your CSV

Export your transactions from your previous app or bank, or use the format described below. The importer expects a CSV with columns: `Account`, `Date`, `Payee`, `Category`, `Memo`, `Outflow`, `Inflow`.

### Import

1. In this app, go to **"Import"** (or `/import`)
2. Click **"Select file"**
3. Choose the budget CSV file
4. Click **"Import"**

**The system will:**
- Create payees automatically
- Match categories by name
- Match accounts by name
- Parse dates in DD/MM/YYYY format
- Show a success/error summary

---

## Recurring Transactions

### Creating a Recurring Entry

1. Go to `/recurring`
2. Click **"+ New Recurring"**
3. Fill in:
   - Account, payee, category
   - Amount and currency
   - **Frequency**: Daily, Weekly, Monthly, Yearly
   - **Start date**: When it begins
   - **End date**: Optional, when it stops

### How Transactions Are Generated

- The system checks daily and creates transactions up to today
- You can trigger generation manually from `/recurring`

**Example:**
```
Monthly rent:
- Amount: -1,500,000 COP
- Frequency: Monthly
- Start: 01/01/2024
- Day: 1 (every 1st of the month)
```

---

## Multi-Currency

### How It Works

- Each account has **one official currency**
- Conversion to the other currency is shown everywhere
- Budget is unified (sums both currencies)
- Transfers support automatic conversion
- Exchange rates come from an external API with multiple fallbacks

### Exchange Rate Fallback Order

1. Today's rate stored in DB
2. Primary exchange rate API
3. Fallback exchange rate API
4. 5-day average from DB
5. Default: 4,000 COP/USD

### Multi-Currency Budget Example

You have:
- $500 USD in bank
- $2,000,000 COP in bank

Budget in COP shows:
- Ready to Assign: ~$4,000,000 COP
  (= $2,000,000 + $500 × 4,000)

---

## Tips and Best Practices

### 1. Start Simple

You don't need every category on day one:
```
Start with:
  - Groceries
  - Transportation
  - Utilities
  - Other

Avoid:
  - 50 hyper-specific categories
```

### 2. Budget Before You Get Paid

When you know how much you'll earn:
1. Record the income (positive)
2. Assign that money to categories
3. Bring "Ready to Assign" to $0

### 3. Use Memos

Memos are useful for:
- Remembering what a transaction was
- Details (e.g., "Office chair purchase")
- Invoice numbers

### 4. Reconcile Regularly

Every week:
1. Compare your transactions with your bank statement
2. Mark them as reconciled
3. Correct any differences

### 5. Use Accumulate for Goals

Use **"accumulate"** for:
- Emergency fund
- Vacation
- Holiday gifts
- Annual insurance

Money builds up month after month.

### 6. Don't Be Afraid to Move Money

If you overspent on "Groceries":
1. Move money from another category
2. Adjust the budget
3. Don't feel bad — this is normal!

**Golden rule:** Never spend without covering it in the budget.

---

## Troubleshooting

### "no such column" error

**Problem:** Outdated database schema

**Solution:**
```bash
python src/finance_app/scripts/migrate_db.py
```

If that doesn't work, reinitialize (WARNING: deletes all data):
```bash
# Windows
del data\finances.db
# Linux/Mac
rm data/finances.db

python src/finance_app/scripts/init_db.py
```

### Charts not loading

**Problem:** Chart.js did not load

**Solution:**
- Check your internet connection (Tailwind and Chart.js load from CDN)
- Open the browser console (F12) and check for errors

### Incorrect exchange rate

**Problem:** External API not responding

**Solution:** The system uses automatic fallbacks — if the API is down, it uses the last stored rate or defaults to 4,000 COP/USD. Restart the server to trigger a fresh fetch.

### Duplicate transactions after import

**Problem:** Imported twice

**Solution:**
- Delete duplicates manually
- Or reset the database and re-import

### No categories available in transaction form

**Solution:**
```bash
python src/finance_app/scripts/seed_categories.py
```

Or from the UI: go to Transactions, look for the yellow warning banner, and click "Create Default Categories".
