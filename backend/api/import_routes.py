"""
Import YNAB CSV API endpoints
"""
from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.database import get_db

router = APIRouter()


@router.post("/ynab")
async def import_ynab_csv(
    file: UploadFile = File(...),
    currency_code: str = 'COP',
    db: Session = Depends(get_db)
):
    """Import YNAB CSV file"""
    # TODO: Implement YNAB import logic
    return {
        "success": True,
        "message": "Import functionality coming soon",
        "stats": {
            "transactions_imported": 0,
            "accounts_created": 0,
            "categories_created": 0
        }
    }
