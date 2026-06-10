from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.services.fire_service import get_fire_dashboard

router = APIRouter()


@router.get("/")
def fire_dashboard(db: Session = Depends(get_db)):
    try:
        return get_fire_dashboard(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
