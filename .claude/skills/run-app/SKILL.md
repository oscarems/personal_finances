---
description: Launch the personal finances FastAPI + vanilla JS app and test it in the browser
---

# Run personal-finances app

## How to launch

```bash
cd /home/oscar/Documents/Github/personal_finances
# Kill any existing server on port 8000
pkill -f "uvicorn" 2>/dev/null; sleep 1
# Start server in background
source venv/bin/activate && APP_PASSWORD=dev python run.py &
sleep 3
# Verify it's up
curl -s http://localhost:8000/health
```

## Environment

- **Port**: 8000
- **Entrypoint**: `python run.py` (starts uvicorn with auto-reload)
- **Auth**: `APP_PASSWORD=dev` for local dev (auth is disabled but the env var must be set)
- **Static files**: served at `/static/` from `src/finance_app/static/`
- **API**: all routes under `/api/`
- **SPA fallback**: non-API 404s serve `index.html`

## Browser testing (Playwright)

```bash
# Install playwright if needed
pip install playwright && playwright install chromium

# Basic smoke test
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('http://localhost:8000/')
    page.screenshot(path='/tmp/app-screenshot.png')
    print('Title:', page.title())
    browser.close()
"
```

## Common API tests

```bash
# Health check
curl -s http://localhost:8000/health

# Accounts
curl -s http://localhost:8000/api/accounts/ | python3 -m json.tool | head -20

# Budget for current month (format: year/month)
curl -s http://localhost:8000/api/budgets/month/$(date +%Y)/$(date +%-m) | python3 -m json.tool | head -20

# Transactions
curl -s "http://localhost:8000/api/transactions/?limit=5" | python3 -m json.tool | head -20
```

## Key field mappings (API ↔ Frontend)

| Model | API returns | Frontend uses |
|-------|-------------|---------------|
| Account | `type`, `currency` (object) | `a.type`, `a.currency?.code` |
| Transaction | `payee_name`, `memo`, `amount` (sign = income/expense) | positive=income, negative=expense |
| Debt | `currency_code` (string) | `d.currency_code` |
| Budget endpoint | `/budgets/month/{year}/{month}` | returns `groups[].categories[]` |
| Patrimonio | `/patrimonio/resumen`, `/patrimonio/activos` | Spanish fields: `nombre`, `tipo`, `valor_adquisicion` |

## Important: currency_id mapping

- COP = id 1
- USD = id 2

Forms that create transactions/accounts must send `currency_id: 1` or `2`, not `currency: "COP"`.
