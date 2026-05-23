"""
Onboarding / first-run setup API.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from finance_app.database import get_db
from finance_app.models import Account, Currency
from finance_app.config import SUPPORTED_CURRENCIES, DEFAULT_EXCHANGE_RATES_TO_USD

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CurrencySetup(BaseModel):
    base_code: str        # moneda principal (ej. "COP")
    secondary_code: Optional[str] = None  # moneda secundaria opcional (ej. "USD")


class FirstAccountSetup(BaseModel):
    name: str
    type: str             # checking, savings, cash, etc.
    currency_code: str
    balance: float = 0.0
    country: Optional[str] = None


class SetupCompletePayload(BaseModel):
    currencies: CurrencySetup
    account: FirstAccountSetup
    gmail_email: Optional[str] = None
    gmail_app_password: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rate_to_base(code: str, base_code: str) -> float:
    """Calculate exchange rate from `code` to `base_code` using USD as pivot."""
    rates = DEFAULT_EXCHANGE_RATES_TO_USD
    base_in_usd = rates.get(base_code, 1.0)
    code_in_usd = rates.get(code, 1.0)
    if base_code == code:
        return 1.0
    # base per 1 unit of code
    return base_in_usd / code_in_usd


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
def setup_status(db: Session = Depends(get_db)):
    """Return whether initial setup has been completed (has at least one account)."""
    has_accounts = db.query(Account).filter_by(is_closed=False).count() > 0
    has_currencies = db.query(Currency).count() > 0
    return {
        "setup_complete": has_accounts,
        "has_currencies": has_currencies,
    }


@router.get("/currencies")
def list_available_currencies():
    """Return all currencies available for selection."""
    return [
        {
            "code": code,
            "name": info["name"],
            "symbol": info["symbol"],
            "decimals": info["decimals"],
        }
        for code, info in SUPPORTED_CURRENCIES.items()
    ]


@router.post("/currencies")
def configure_currencies(payload: CurrencySetup, db: Session = Depends(get_db)):
    """
    Set up base and secondary currencies.
    Clears existing currencies and creates the chosen ones.
    Only allowed before any accounts exist (pre-setup).
    """
    if db.query(Account).count() > 0:
        raise HTTPException(400, "No se pueden cambiar las monedas después de crear cuentas.")

    base = payload.base_code.upper()
    secondary = payload.secondary_code.upper() if payload.secondary_code else None

    codes_to_create = [base]
    if secondary and secondary != base:
        codes_to_create.append(secondary)

    for code in codes_to_create:
        if code not in SUPPORTED_CURRENCIES:
            raise HTTPException(400, f"Moneda no soportada: {code}")

    # Remove existing currencies (safe before any accounts exist)
    db.query(Currency).delete()
    db.commit()

    for code in codes_to_create:
        info = SUPPORTED_CURRENCIES[code]
        rate = _rate_to_base(code, base)
        db.add(Currency(
            code=code,
            symbol=info["symbol"],
            name=info["name"],
            exchange_rate_to_base=rate,
            is_base=(code == base),
            decimals=info["decimals"],
        ))

    db.commit()
    return {"ok": True, "currencies": codes_to_create}


@router.post("/complete")
def complete_setup(payload: SetupCompletePayload, db: Session = Depends(get_db)):
    """
    Finish the onboarding wizard:
    1. Configure currencies
    2. Create first account
    3. (Optional) Save Gmail config to .env
    """
    # Step 1: currencies
    configure_currencies(payload.currencies, db)

    # Step 2: first account
    acc = payload.account
    currency = db.query(Currency).filter_by(code=acc.currency_code.upper()).first()
    if not currency:
        raise HTTPException(400, f"Moneda '{acc.currency_code}' no encontrada. Configura las monedas primero.")

    account = Account(
        name=acc.name,
        type=acc.type,
        currency_id=currency.id,
        balance=acc.balance,
        country=acc.country,
        is_budget=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    # Step 3: Gmail config (write to .env file if provided)
    if payload.gmail_email and payload.gmail_app_password:
        _save_gmail_env(payload.gmail_email, payload.gmail_app_password)

    return {
        "ok": True,
        "account_id": account.id,
        "message": "Configuración completada exitosamente",
    }


def _save_gmail_env(email: str, app_password: str):
    """Append Gmail credentials to the .env file (create if not exists)."""
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"

    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    lines = existing.splitlines()
    updated = {}
    kept = []
    for line in lines:
        if line.startswith("GMAIL_EMAIL="):
            updated["GMAIL_EMAIL"] = True
            kept.append(f"GMAIL_EMAIL={email}")
        elif line.startswith("GMAIL_APP_PASSWORD="):
            updated["GMAIL_APP_PASSWORD"] = True
            kept.append(f"GMAIL_APP_PASSWORD={app_password}")
        else:
            kept.append(line)

    if "GMAIL_EMAIL" not in updated:
        kept.append(f"GMAIL_EMAIL={email}")
    if "GMAIL_APP_PASSWORD" not in updated:
        kept.append(f"GMAIL_APP_PASSWORD={app_password}")

    env_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
