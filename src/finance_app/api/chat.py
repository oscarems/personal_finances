"""
API router — Chat SQL con LangGraph + Ollama.
"""
import logging
from datetime import datetime

import requests as http_requests
from fastapi import APIRouter, Depends, Request
from finance_app.config import OLLAMA_BASE_URL
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pathlib import Path

from finance_app.database import get_db
from finance_app.services.chat_service import procesar_mensaje

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def chat_page(request: Request):
    return templates.TemplateResponse("chat_ui.html", {"request": request})


@router.get("/modelos")
def listar_modelos():
    try:
        resp = http_requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [
            {"nombre": m["name"], "tamaño_gb": round(m["size"] / 1e9, 1)}
            for m in data.get("models", [])
        ]
    except Exception:
        return []


class ChatQuery(BaseModel):
    pregunta: str
    modelo: str
    thread_id: str = "default"


class ChatResponse(BaseModel):
    respuesta: str
    sql_generado: str
    filas: int


@router.post("/query", response_model=ChatResponse)
def query_chat(body: ChatQuery, db: Session = Depends(get_db)):
    resultado = procesar_mensaje(
        pregunta=body.pregunta,
        modelo=body.modelo,
        db=db,
        thread_id=body.thread_id,
    )

    logger.info(
        "[chat] %s | thread=%s | modelo=%s | intencion=%s | filas=%d | sql=%s",
        datetime.now().isoformat(),
        body.thread_id,
        body.modelo,
        resultado["intencion"],
        resultado["filas"],
        resultado["sql_generado"] or "-",
    )

    return ChatResponse(
        respuesta=resultado["respuesta"],
        sql_generado=resultado["sql_generado"],
        filas=resultado["filas"],
    )
