# Features Comparison

**Comparison of standard budgeting app features and their implementation status in this app**

---

## Implemented Features

| Feature | Reference App | This App | Status |
|---------|------|----------|--------|
| Multiple accounts | Yes | Yes | Complete |
| Budget by categories | Yes | Yes | Complete |
| Rollover (accumulate vs reset) | Yes | Yes | Complete |
| Ready to Assign | Yes | Yes | Complete + Multi-currency |
| Transactions | Yes | Yes | Complete |
| Categories organized in groups | Yes | Yes | Complete |
| Basic reconciliation | Yes | Partial | Field exists, no guided workflow |
| Import budget CSV | Yes | Yes | Complete |
| Recurring transactions | Yes | Yes | Complete |
| Multi-currency | No | Yes | **Not in most apps** |
| Basic reports | Yes | Yes | Complete |
| Advanced account types | Partial | Yes | **8 types vs 2 in most apps** |
| Inter-account transfers | Yes | Yes | Complete + Multi-currency |
| Net worth tracking | Yes | Yes | Complete — unified Patrimonio module |
| Debt amortization | No | Yes | **Not in most apps** — hybrid engine |

---

## Partial or Missing Features

### 1. Advanced Goals

| Feature | Reference App | This App |
|---------|------|----------|
| Target Category Balance | Yes | No |
| Target Balance by Date | Yes | No |
| Monthly Savings Builder | Yes | No |
| Needed for Spending | Yes | No |
| Basic `target_amount` field | Yes | Exists but no logic |

**Status: ~50% implemented**
- `target_amount` field exists in categories
- No goal types or progress tracking

---

### 2. Age of Money

**Status: Not implemented**

What it is: The average number of days money stays in your account before being spent. A high Age of Money means you are living on older income (financially healthy). A low Age of Money means you are spending money as soon as it arrives.

---

### 3. Split Transactions

**Status: Not implemented**

Allows splitting a single transaction across multiple categories.

**Example:**
```
Grocery store purchase: -$200,000 COP
├─ $120,000 → Groceries
├─ $50,000 → Cleaning supplies
└─ $30,000 → Personal care
```

---

### 4. Credit Card Payment Tracking

**Status: ~20% implemented**
- Credit cards exist as an account type
- No special budget logic for card payments (traditional budgeting apps move money from spending categories to a payment category when charging to a credit card)

---

### 5. Full Reconciliation Workflow

**Status: ~30% implemented**
- `cleared` field exists on transactions
- Checkbox in transaction form
- No guided reconciliation process
- No lock for reconciled transactions

---

### 6. Scheduled Transaction Approval

**Status: ~60% implemented**
- Recurring transactions auto-generate
- No upcoming transactions preview
- No approval/skip/snooze workflow

---

### 7. Advanced Reports

**Status: ~70% implemented**

| Report | Reference App | This App |
|--------|------|----------|
| Income vs Expenses | Yes | Yes |
| Spending by Category | Yes | Yes |
| Spending by Payee | Yes | No |
| Net Worth Over Time | Yes | Yes (Patrimonio timeline) |
| Age of Money | Yes | No |
| Month-to-Month Comparison | Yes | No |
| Spending Trends | Yes | Basic |
| Debt Payoff Projection | No | Yes |
| Principal Timeline | No | Yes |

---

### 8. Mobile App / PWA

**Status: Not implemented**

---

### 9. Direct Bank Import

**Status: ~25% implemented**
- Imports budget CSV
- Gmail scraping for supported Colombian banks (Bancolombia, BAC, Mastercard Black)
- No OFX/QFX import
- No direct bank API connection (Plaid not available for Colombia)

---

### 10. Undo/Redo and Change History

**Status: Not implemented**

---

## Our Advantages

This app has several advantages over standard budgeting apps:

1. **Native multi-currency** — Standard apps do not support multiple currencies. This app has COP/USD fully integrated with per-transaction FX tracking.

2. **Advanced account types** — Most apps only have checking/savings. This app has 8 account types with specialized fields (CDT maturity date, mortgage rate, etc.).

3. **Debt amortization engine** — Most apps have no debt tracking. This app has a hybrid amortization engine with real payments + projections, and a principal balance timeline.

4. **Net worth module** — Unified Patrimonio system with asset valuation (depreciation/appreciation), long-term debt tracking, and a 48-month timeline (24 past + 24 future).

5. **Multi-currency transfers** — Most apps do not support cross-currency transfers. This app converts automatically using the current exchange rate.

6. **No subscription** — Subscription apps cost ~$14.99/month. This app is free and open source.

---

## Priority Backlog

**High priority (core functionality):**
- Split transactions
- Reconciliation workflow
- Advanced goals

**Medium priority (improved experience):**
- Advanced reports (month-to-month comparison)
- Scheduled transaction approval workflow
- Credit card payment tracking
- Age of Money display

**Low priority (nice to have):**
- PWA / mobile app
- OFX/QFX import
- Undo/Redo
- Multi-user authentication

---

## Overall Status

**~75% of standard budgeting functionality implemented**

**Strengths:**
- Complete core budgeting
- Multi-currency (beyond what most apps offer)
- Advanced account types
- Smart transfers
- Full debt amortization engine
- Unified net worth tracking

**Gaps:**
- Split transactions
- Advanced goals
- Reconciliation workflow
- Age of Money
