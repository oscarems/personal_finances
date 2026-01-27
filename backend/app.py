"""
FastAPI Main Application
"""
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from sqlalchemy.orm import Session

from backend.database import init_db, get_db, SessionLocal, SessionLocalDemo, engine_demo
from backend.init_db import initialize_database
from backend.api import transactions, accounts, budgets, categories, import_routes, mortgage, reports, recurring, exchange_rates, admin, debts, emergency_fund, ynab_mappings, outlook_import, alerts, reconciliation, wealth_assets

# Create FastAPI app
app = FastAPI(
    title="Personal Finances",
    description="YNAB-style personal finance manager",
    version="1.0.0"
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
static_path = Path(__file__).parent.parent / "frontend" / "static"
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Jinja2 templates
templates_path = Path(__file__).parent.parent / "frontend" / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Include API routers
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(budgets.router, prefix="/api/budgets", tags=["budgets"])
app.include_router(categories.router, prefix="/api/categories", tags=["categories"])
app.include_router(import_routes.router, prefix="/api/import", tags=["import"])
app.include_router(outlook_import.router, prefix="/api/import/outlook", tags=["outlook-import"])
app.include_router(mortgage.router, prefix="/api/mortgage", tags=["mortgage"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(recurring.router, prefix="/api/recurring", tags=["recurring"])
app.include_router(exchange_rates.router, prefix="/api/exchange-rates", tags=["exchange-rates"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(debts.router, prefix="/api/debts", tags=["debts"])
app.include_router(emergency_fund.router, prefix="/api/emergency-fund", tags=["emergency-fund"])
app.include_router(ynab_mappings.router, prefix="/api/ynab-mappings", tags=["ynab-mappings"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(reconciliation.router, prefix="/api/reconciliation", tags=["reconciliation"])
app.include_router(wealth_assets.router, prefix="/api/wealth-assets", tags=["wealth-assets"])


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    print("✓ Database initialized")

    # Check if primary DB needs seeding
    from backend.models import Currency

    db = SessionLocal()
    try:
        currencies = db.query(Currency).first()
        if not currencies:
            print("🌱 Seeding database with initial data...")
            db.close()
            initialize_database(create_samples=True)
    finally:
        db.close()

    init_db(engine_override=engine_demo)
    if DEMO_DATABASE_IS_SQLITE:
        demo_db_missing = not DEMO_DATABASE_PATH.exists()
    else:
        demo_db_missing = False

    demo_db = SessionLocalDemo()
    try:
        demo_currencies = demo_db.query(Currency).first()
        if demo_db_missing or not demo_currencies:
            print("🌱 Seeding demo database with initial data...")
            demo_db.close()
            initialize_database(
                create_samples=True,
                session_factory=SessionLocalDemo,
                create_tables_func=lambda: init_db(engine_override=engine_demo)
            )
    finally:
        demo_db.close()


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


@app.get("/import")
async def import_page(request: Request):
    """Import page"""
    return templates.TemplateResponse("import.html", {"request": request})


@app.get("/mortgage")
async def mortgage_page(request: Request):
    """Mortgage simulator page"""
    return templates.TemplateResponse("mortgage.html", {"request": request})


@app.get("/reports")
async def reports_page(request: Request):
    """Reports and analytics page"""
    return templates.TemplateResponse("reports.html", {"request": request})

@app.get("/patrimonio")
async def patrimonio_page(request: Request):
    """Wealth overview page"""
    return templates.TemplateResponse("wealth.html", {"request": request})


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


@app.get("/api/currencies")
async def get_currencies(db: Session = Depends(get_db)):
    """Get all available currencies"""
    from backend.models import Currency
    currencies = db.query(Currency).all()
    return [c.to_dict() for c in currencies]


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
