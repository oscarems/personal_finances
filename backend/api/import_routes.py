"""
Import API endpoints
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
import shutil

from backend.database import get_db
from backend.utils.ynab_importer import import_ynab_csv

router = APIRouter()


@router.post("/ynab")
async def import_ynab(
    file: UploadFile = File(...),
    currency_code: str = "COP",
    db: Session = Depends(get_db)
):
    """
    Import YNAB CSV file
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Save uploaded file temporarily
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Import the file
        stats = import_ynab_csv(db, str(file_path), currency_code)

        # Clean up
        file_path.unlink()

        return {
            "message": "Import completed",
            "stats": stats
        }

    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))
