from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

import web_scrapping_email

router = APIRouter()


@router.get("/messages")
def list_gmail_messages(
    since_date: str | None = Query(default=None, description="Fecha mínima YYYY-MM-DD"),
    max_emails: int = Query(default=50, ge=1, le=300),
):
    parsed_since_date = None
    if since_date:
        try:
            parsed_since_date = datetime.strptime(since_date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="since_date debe estar en formato YYYY-MM-DD") from exc

    try:
        rows = web_scrapping_email.fetch_transactions(
            since_date=parsed_since_date,
            max_emails=max_emails,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando Gmail: {exc}") from exc

    return {
        "total": len(rows),
        "messages": rows,
    }
