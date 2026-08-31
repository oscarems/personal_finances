"""Mobile snapshot API — read-only payload for WiFi sync."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.services.mobile_snapshot_service import build_mobile_snapshot

router = APIRouter()


@router.get("/snapshot")
def mobile_snapshot(currency_code: str = 'COP', db: Session = Depends(get_db)):
    """
    Compact budget snapshot for mobile clients.

    Intended for same-LAN pull; clients may cache locally and show stale data
    when the desktop app is offline.
    """
    return build_mobile_snapshot(db, currency_code=currency_code)
