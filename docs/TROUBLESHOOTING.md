# Known Issues and Solutions

## Status Summary

| Issue | Status | Action Required |
|-------|--------|-----------------|
| DB missing column `initial_amount` | Resolved | `python src/finance_app/scripts/migrate_db.py` |
| Add/delete budget groups | Resolved | "New Group" button in Budget |
| Category selector unavailable | Resolved | Banner + button in Transactions |
| Mortgage extra payment not recalculating charts | Pending | — |
| Mortgage end date / total not displayed | Pending | — |
| Edit initial savings amount | Resolved | Field in budget assignment modal |
| Multi-currency reports | Resolved | Automatic conversion implemented |
| Categories in recurring transactions | Resolved | Same fix as category selector |

---

## 1. Error: `no such column: categories.initial_amount`

**Solution:**
```bash
python src/finance_app/scripts/migrate_db.py
```

This script adds the missing column without losing data.

**Alternative (start fresh — WARNING: deletes all data):**
```bash
# Windows
Remove-Item src\finance_app\data\finances.db
# Linux/Mac
rm src/finance_app/data/finances.db

python src/finance_app/scripts/init_db.py
```

---

## 2. Add/Delete Budget Groups

**How to create a group:**
1. Go to Budget
2. Click **"+ New Group"** (top right corner)
3. Enter a group name
4. Select type: Expenses or Income
5. Click "Create Group"

**How to delete a group:**
1. Click the trash icon next to the group name
2. Confirm deletion
3. **WARNING:** This also deletes all categories in the group

**Code locations:**
- Frontend: `src/finance_app/templates/budget.html`
- Backend: `src/finance_app/api/categories.py`
  - `POST /api/categories/groups`
  - `DELETE /api/categories/groups/{id}`

---

## 3. No Categories Available in Transaction/Recurring Forms

**Option 1 — From the UI (recommended):**
1. Go to **Transactions**
2. If no categories exist, a yellow warning banner appears
3. Click **"Create Default Categories"**

**Option 2 — From terminal:**
```bash
python src/finance_app/scripts/seed_categories.py
# or
python src/finance_app/scripts/init_db.py
```

**Option 3 — Create manually:**
Go to Budget → click **"+ New Group"** → add categories

---

## 4. Mortgage Extra Payment Not Recalculating Charts

**Status: Pending fix**

The extra payment input does not trigger an automatic recalculation of the amortization chart and end date.

**Workaround:** After modifying the extra payment amount, click "Calculate" again manually.

---

## 5. Mortgage End Date and Total Not Displayed

**Status: Pending fix**

The data is returned in the API response but is not rendered in the HTML template.

---

## 6. Cannot Edit Initial Savings Amount

**Status: Resolved**

A **"Money I Have Today (Initial)"** field was added to the budget assignment modal.

**How to use:**
1. Go to Budget
2. Click on an "accumulate" category (savings/goal type)
3. The "Initial amount I already have" field will appear
4. Enter the amount you already have saved for that category
5. Click "Save Budget"

---

## 7. Reports: USD Transactions Not Appearing in COP Reports

**Status: Resolved**

All reports now **include all currencies** with automatic conversion.

**What changed:**
- All reports now show COP and USD transactions combined
- The current exchange rate is used to convert to the selected display currency
- Applies to all report endpoints in `api/reports_pkg/`

**Example:**
- Select "View in COP" → see COP expenses + USD expenses converted to COP
- Select "View in USD" → see USD expenses + COP expenses converted to USD

---

## Recommended Quick Start After Fresh Install

```bash
# Step 1: Run database migrations
python src/finance_app/scripts/migrate_db.py

# Step 2: Verify categories exist
curl http://localhost:8000/api/categories/groups
# If returns [] (empty array), run step 3

# Step 3: Seed initial data
python src/finance_app/scripts/init_db.py

# Step 4: Start the server
python run.py
```
