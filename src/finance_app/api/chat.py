"""
API router — Chat SQL con LangGraph + Ollama, y chat con Claude vía Anthropic API.
"""
import json
import logging
import os
from datetime import datetime, date

import anthropic
import requests as http_requests
from fastapi import APIRouter, Depends, Request
from finance_app.config import OLLAMA_BASE_URL
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List, Optional

from finance_app.database import get_db
from finance_app.services.chat_service import procesar_mensaje
from finance_app.services.budget_service import get_budget_overview, get_month_budget
from finance_app.services.transaction_service import get_transactions

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# ---------------------------------------------------------------------------
# Claude agent — herramientas: presupuesto y transacciones
# ---------------------------------------------------------------------------

CLAUDE_TOOLS = [
    {
        "name": "get_budget",
        "description": (
            "Obtiene el presupuesto mensual del usuario: categorías con asignado, gastado y disponible. "
            "Úsalo cuando el usuario pregunte por su presupuesto, categorías, cuánto ha gastado o cuánto le queda."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "Año del presupuesto, ej: 2026. Si no se especifica, usa el año actual."
                },
                "month": {
                    "type": "integer",
                    "description": "Mes del presupuesto (1-12). Si no se especifica, usa el mes actual."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_transactions",
        "description": (
            "Lista las transacciones del usuario con filtros opcionales por fechas o búsqueda de texto. "
            "Úsalo cuando el usuario pregunte por gastos específicos, compras recientes o movimientos de dinero."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Fecha inicio en formato YYYY-MM-DD, ej: 2026-06-01"
                },
                "end_date": {
                    "type": "string",
                    "description": "Fecha fin en formato YYYY-MM-DD, ej: 2026-06-30"
                },
                "search": {
                    "type": "string",
                    "description": "Texto libre para buscar en descripción o lugar de la transacción"
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de transacciones a retornar. Por defecto 30."
                }
            },
            "required": []
        }
    }
]


def _execute_tool(name: str, tool_input: dict, db: Session) -> str:
    today = date.today()
    try:
        if name == "get_budget":
            year = tool_input.get("year", today.year)
            month = tool_input.get("month", today.month)
            result = get_month_budget(db, date(year, month, 1))
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "get_transactions":
            start = tool_input.get("start_date")
            end = tool_input.get("end_date")
            txns = get_transactions(
                db,
                start_date=date.fromisoformat(start) if start else None,
                end_date=date.fromisoformat(end) if end else None,
                search=tool_input.get("search"),
                limit=tool_input.get("limit", 30),
            )
            return json.dumps([t.to_dict() for t in txns], ensure_ascii=False, default=str)

        return json.dumps({"error": f"Herramienta desconocida: {name}"})
    except Exception as e:
        logger.error("[claude-agent] tool %s error: %s", name, e)
        return json.dumps({"error": str(e)})


@router.get("/", response_class=HTMLResponse)
def chat_page(request: Request):
    return templates.TemplateResponse("chat_ui.html", context={"request": request})


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


# ---------------------------------------------------------------------------
# Claude agent endpoint
# ---------------------------------------------------------------------------

class ClaudeMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ClaudeRequest(BaseModel):
    message: str
    history: List[ClaudeMessage] = []


class ClaudeResponse(BaseModel):
    reply: str


@router.post("/claude", response_model=ClaudeResponse)
def claude_chat(body: ClaudeRequest, db: Session = Depends(get_db)):
    """Chat con Claude usando herramientas de presupuesto y transacciones."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ClaudeResponse(reply="Error: ANTHROPIC_API_KEY no configurada en el .env")

    client = anthropic.Anthropic(api_key=api_key)

    messages = [{"role": m.role, "content": m.content} for m in body.history]
    messages.append({"role": "user", "content": body.message})

    today = date.today().strftime("%d de %B de %Y")
    system = (
        f"Eres un asistente financiero personal. Hoy es {today}. "
        "Tienes acceso al presupuesto mensual y a las transacciones reales del usuario. "
        "Responde siempre en español, de forma clara y concisa. "
        "Cuando necesites datos para responder, usa las herramientas disponibles. "
        "No inventes cifras: si no tienes los datos, consúltalos primero."
    )

    while True:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=system,
            tools=CLAUDE_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            return ClaudeResponse(reply=text)

        # Claude quiere usar una herramienta
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_tool(block.name, block.input, db)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "user", "content": tool_results})
