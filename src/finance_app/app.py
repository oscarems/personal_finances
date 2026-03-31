"""
FastAPI Main Application
"""
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from sqlalchemy.orm import Session

from finance_app.database import (
    init_db,
    get_db,
    default_database_name,
    ensure_database_initialized,
    get_session_factory,
)
from finance_app.api import (
    transactions,
    accounts,
    budgets,
    categories,
    mortgage,
    recurring,
    exchange_rates,
    admin,
    debts,
    emergency_fund,
    gmail_import,
    alerts,
    reconciliation,
    investment_simulator,
    tags,
    goals,
    patrimonio,
)
from finance_app.api.reports_pkg import router as reports_router
from finance_app.services.recurring_service import generate_due_transactions

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Personal Finances",
    description="YNAB-style personal finance manager",
    version="1.0.1"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Jinja2 templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Include API routers
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(budgets.router, prefix="/api/budgets", tags=["budgets"])
app.include_router(categories.router, prefix="/api/categories", tags=["categories"])
app.include_router(gmail_import.router, prefix="/api/import/gmail", tags=["gmail-import"])
app.include_router(mortgage.router, prefix="/api/mortgage", tags=["mortgage"])
app.include_router(investment_simulator.router, prefix="/api/investment-simulator", tags=["investment-simulator"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
app.include_router(recurring.router, prefix="/api/recurring", tags=["recurring"])
app.include_router(exchange_rates.router, prefix="/api/exchange-rates", tags=["exchange-rates"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(debts.router, prefix="/api/debts", tags=["debts"])
app.include_router(emergency_fund.router, prefix="/api/emergency-fund", tags=["emergency-fund"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(reconciliation.router, prefix="/api/reconciliation", tags=["reconciliation"])
app.include_router(tags.router, prefix="/api/tags", tags=["tags"])
app.include_router(goals.router, prefix="/api/goals", tags=["goals"])
app.include_router(patrimonio.router, prefix="/api/patrimonio", tags=["patrimonio"])


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    default_name = default_database_name()
    ensure_database_initialized(default_name)
    session_factory = get_session_factory(default_name)
    db = session_factory()
    try:
        generate_due_transactions(db)
    finally:
        db.close()
    try:
        from finance_app.sync.email_scrape_sync import sync_email_transactions
        sync_email_transactions()
    except (ImportError, RuntimeError) as exc:
        logger.warning("Email sync skipped during startup: %s", exc)
    print("✓ Database initialized")


@app.get("/")
async def home(request: Request):
    """Home page - Dashboard"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/budget")
async def budget_page(request: Request):
    """Budget page"""
    return templates.TemplateResponse("budget.html", {"request": request})


@app.get("/transactions")
async def transactions_page(request: Request):
    """Transactions page"""
    return templates.TemplateResponse("transactions.html", {"request": request})


@app.get("/accounts")
async def accounts_page(request: Request):
    """Accounts page"""
    return templates.TemplateResponse("accounts.html", {"request": request})


@app.get("/advanced/gmail")
async def advanced_gmail_page(request: Request):
    """Gmail import preview page"""
    return templates.TemplateResponse("gmail_import.html", {"request": request})

@app.get("/mortgage")
async def mortgage_page(request: Request):
    """Mortgage simulator page"""
    return templates.TemplateResponse("mortgage.html", {"request": request})


@app.get("/investment-simulator")
async def investment_simulator_page(request: Request):
    """Investment simulator page"""
    return templates.TemplateResponse("investment_simulator.html", {"request": request})


@app.get("/reports")
async def reports_page(request: Request):
    """Reports and analytics page"""
    return templates.TemplateResponse("reports/index.html", {"request": request})

@app.get("/patrimonio")
async def patrimonio_page(request: Request):
    """Patrimonio dashboard page"""
    return templates.TemplateResponse("patrimonio/patrimonio.html", {"request": request})



@app.get("/recurring")
async def recurring_page(request: Request):
    """Recurring/automatic transactions page"""
    return templates.TemplateResponse("recurring.html", {"request": request})


@app.get("/debts")
async def debts_page(request: Request):
    """Debts management page"""
    return templates.TemplateResponse("debts.html", {"request": request})


@app.get("/emergency-fund")
async def emergency_fund_page(request: Request):
    """Emergency fund page"""
    return templates.TemplateResponse("emergency_fund.html", {"request": request})


@app.get("/financial-health")
async def financial_health_page(request: Request):
    """Financial health dashboard"""
    return templates.TemplateResponse("financial_health.html", {"request": request})


@app.get("/goals")
async def goals_page(request: Request):
    """Goals page"""
    return templates.TemplateResponse("goals.html", {"request": request})


@app.get("/api/currencies")
async def get_currencies(db: Session = Depends(get_db)):
    """Get all available currencies"""
    from finance_app.models import Currency
    currencies = db.query(Currency).all()
    return [c.to_dict() for c in currencies]


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
