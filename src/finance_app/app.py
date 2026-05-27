"""
FastAPI Main Application — SPA mode.

Serves all API routes and falls back to index.html for any non-API path,
enabling client-side routing via History API.
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
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
    cash_flow,
    setup,
)
from finance_app.api import email_sender_rules
from finance_app.api import merchant_rules as merchant_rules_module
from finance_app.api import chat as chat_module
from finance_app.api.reports_pkg import router as reports_router
from finance_app.services.recurring_service import generate_due_transactions
from finance_app.auth import router as auth_router, register_auth_exception_handler, APP_PASSWORD

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if not APP_PASSWORD:
        raise RuntimeError(
            "APP_PASSWORD environment variable is not set. "
            "Set it before starting the app (e.g. APP_PASSWORD=mysecret)."
        )
    init_db()
    default_name = default_database_name()
    ensure_database_initialized(default_name)
    session_factory = get_session_factory(default_name)
    db = session_factory()
    try:
        generate_due_transactions(db)
        from finance_app.services.exchange_rate_service import sync_all_currency_rates
        try:
            sync_all_currency_rates(db)
        except Exception as exc:
            logger.warning("Exchange rate sync skipped: %s", exc)
    finally:
        db.close()
    logger.info("Database initialized")
    yield


app = FastAPI(
    title="Personal Finances",
    description="Personal finance manager",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API routers
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
app.include_router(email_sender_rules.router, prefix="/api/email-sender-rules", tags=["email-sender-rules"])
app.include_router(merchant_rules_module.router, prefix="/api/merchant-rules", tags=["merchant-rules"])
app.include_router(chat_module.router, prefix="/api/chat", tags=["chat"])
app.include_router(cash_flow.router, prefix="/api/cash-flow", tags=["cash-flow"])
app.include_router(setup.router, prefix="/api/setup", tags=["setup"])
app.include_router(auth_router)
register_auth_exception_handler(app)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/currencies")
async def get_currencies(db: Session = Depends(get_db)):
    from finance_app.models import Currency
    currencies = db.query(Currency).all()
    return [c.to_dict() for c in currencies]


@app.exception_handler(StarletteHTTPException)
async def spa_fallback(request: Request, exc: StarletteHTTPException):
    """Serve index.html for 404s on non-API paths (client-side routing)."""
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        return FileResponse(str(INDEX_HTML))
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
