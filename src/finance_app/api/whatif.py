"""What-if combined simulator API."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.services.whatif_service import simulate_what_if

router = APIRouter()


@router.get("/")
def what_if(
    extra_monthly: float = Query(0, ge=0),
    strategy: str = Query("avalanche", pattern="^(avalanche|snowball)$"),
    db: Session = Depends(get_db),
):
    """Project impact of an extra monthly amount on debt, emergency fund and FIRE."""
    return simulate_what_if(db, extra_monthly=extra_monthly, strategy=strategy)
