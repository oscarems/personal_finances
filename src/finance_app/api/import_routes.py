"""
Import YNAB CSV API endpoints
"""
import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.utils.ynab_importer import import_ynab_csv

router = APIRouter()


@router.post("/ynab")
async def import_ynab_csv_endpoint(
    file: UploadFile = File(...),
    currency_code: str = 'COP',
    db: Session = Depends(get_db)
):
    """
    Import YNAB CSV file

    Args:
        file: CSV file exported from YNAB
        currency_code: Currency for transactions (COP or USD)

    Returns:
        Import statistics
    """
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV file")

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as tmp_file:
        # Read and write uploaded file
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name

    try:
        # Import CSV using our importer
        stats = import_ynab_csv(db, tmp_file_path, currency_code)

        return {
            "success": True,
            "message": f"Successfully imported {stats['imported']} transactions",
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

    finally:
        # Clean up temporary file
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
