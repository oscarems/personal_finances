"""
FastAPI Main Application
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from backend.database import init_db
from backend.init_db import initialize_database
from backend.api import transactions, accounts, budgets, categories, import_routes, mortgage, reports, recurring

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
app.include_router(mortgage.router, prefix="/api/mortgage", tags=["mortgage"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(recurring.router, prefix="/api/recurring", tags=["recurring"])


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    print("✓ Database initialized")

    # Check if DB needs seeding
    from backend.database import SessionLocal
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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
