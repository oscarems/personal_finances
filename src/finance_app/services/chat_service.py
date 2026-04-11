"""
Chat service — LangGraph + Ollama para consultas SQL en lenguaje natural.

En producción (sin LangChain instalado) el módulo carga igual pero
`procesar_mensaje` devuelve un mensaje de "no disponible".
"""
import json
import re
from typing import Any, TypedDict, Annotated

from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from langchain_ollama import OllamaLLM
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    from langgraph.checkpoint.memory import MemorySaver
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False

from finance_app.config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT

MAX_ROWS = 200

TABLAS = [
    "transactions", "categories", "category_groups", "accounts",
    "budget_months", "debts", "debt_payments", "wealth_assets",
    "patrimonio_asset", "patrimonio_debt", "goals",
]


# ── Helpers (no dependen de LangChain) ───────────────────────────────────

def get_db_schema(db: Session) -> str:
    """Devuelve el schema de las tablas relevantes en formato compacto."""
    lineas = []
    for tabla in TABLAS:
        try:
            rows = db.execute(text(f"PRAGMA table_info({tabla})")).fetchall()
            if rows:
                cols = ", ".join(r[1] for r in rows)
                lineas.append(f"{tabla}: {cols}")
        except Exception:
            continue

    lineas.append("")
    lineas.append("ADVERTENCIAS:")
    lineas.append("- Solo SELECT. Nunca INSERT, UPDATE ni DELETE.")
    lineas.append("- budget_months.assigned es de solo lectura.")
    return "\n".join(lineas)


def _format_historial(messages: list, limit: int = 4) -> str:
    recientes = messages[-limit:] if len(messages) > limit else messages
    lineas = []
    for m in recientes:
        role = "Usuario" if getattr(m, "type", None) == "human" else "Asistente"
        lineas.append(f"{role}: {m.content if hasattr(m, 'content') else str(m)}")
    return "\n".join(lineas)


# ── Sección LangChain (solo si está disponible) ───────────────────────────

if _LANGCHAIN_AVAILABLE:
    class ChatState(TypedDict):
        messages: Annotated[list, add_messages]
        pregunta: str
        intencion: str
        sql_generado: str
        resultado_sql: list[dict]
        respuesta_final: str
        error: str | None
        modelo: str
        db: Any

    def _make_llm(modelo: str, **kwargs) -> "OllamaLLM":
        return OllamaLLM(
            model=modelo,
            base_url=OLLAMA_BASE_URL,
            timeout=OLLAMA_TIMEOUT,
            num_ctx=2048,
            temperature=kwargs.get("temperature", 0),
            num_predict=kwargs.get("num_predict", -1),
        )

    def clasificar_intencion(state: ChatState) -> dict:
        llm = _make_llm(state["modelo"], num_predict=200)
        prompt = (
            "Clasifica la intencion del usuario. Responde UNICAMENTE con una de estas palabras: sql, conversacional\n\n"
            "- sql: el usuario quiere consultar datos financieros (gastos, ingresos, deudas, saldo, transacciones, metas, presupuesto)\n"
            "- conversacional: saludos, preguntas generales, consultas sobre el asistente\n\n"
            f"Mensaje: {state['pregunta']}\n\n"
            "Intencion:"
        )
        resp = llm.invoke(prompt).strip().lower()
        if resp not in ("sql", "conversacional"):
            resp = "sql"
        return {"intencion": resp}

    def generar_sql(state: ChatState) -> dict:
        llm = _make_llm(state["modelo"], num_predict=200)
        schema = get_db_schema(state["db"])
        prompt = (
            "Eres un experto en SQLite. Convierte la pregunta en un query SQL valido.\n"
            "Responde UNICAMENTE con el SQL. Sin explicaciones, sin markdown, sin backticks.\n"
            "Solo SELECT. Nunca INSERT, UPDATE ni DELETE.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"PREGUNTA: {state['pregunta']}\n\n"
            "SQL:"
        )
        sql = llm.invoke(prompt).strip()
        sql = re.sub(r"^```(?:sql)?\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.strip()
        if not sql.upper().startswith("SELECT"):
            return {"sql_generado": "", "error": f"El modelo no genero un SELECT valido: {sql}"}
        return {"sql_generado": sql, "error": None}

    def ejecutar_sql(state: ChatState) -> dict:
        try:
            q = state["sql_generado"].strip().rstrip(";")
            if "LIMIT" not in q.upper():
                q += f" LIMIT {MAX_ROWS}"
            rows = state["db"].execute(text(q)).fetchall()
            return {"resultado_sql": [dict(row._mapping) for row in rows], "error": None}
        except Exception as e:
            return {"resultado_sql": [], "error": f"Error al ejecutar el query: {e}"}

    def narrar_resultado(state: ChatState) -> dict:
        llm = _make_llm(state["modelo"], temperature=0.3, num_predict=300)
        historial = _format_historial(state.get("messages", []))
        datos = (
            "No se encontraron registros."
            if not state["resultado_sql"]
            else json.dumps(state["resultado_sql"][:50], default=str, ensure_ascii=False)
        )
        prompt = (
            "Eres un asistente financiero personal. Nunca respondas con SQL ni codigo.\n"
            "Solo responde en espanol conversacional y conciso.\n\n"
            f"Historial reciente:\n{historial}\n\n"
            f"El usuario pregunto: {state['pregunta']}\n\n"
            f"Resultado:\n{datos}\n\n"
            "Respuesta:"
        )
        respuesta = llm.invoke(prompt).strip()
        return {
            "respuesta_final": respuesta,
            "messages": [
                {"role": "human", "content": state["pregunta"]},
                {"role": "ai", "content": respuesta},
            ],
        }

    def responder_conversacional(state: ChatState) -> dict:
        llm = _make_llm(state["modelo"], temperature=0.3, num_predict=300)
        historial = _format_historial(state.get("messages", []))
        prompt = (
            "Eres un asistente financiero personal llamado Fincas.\n"
            "Responde en espanol de forma amigable y concisa.\n"
            "No menciones que puedes consultar bases de datos a menos que sea relevante.\n\n"
            f"Historial reciente:\n{historial}\n\n"
            f"Usuario: {state['pregunta']}\n"
            "Fincas:"
        )
        respuesta = llm.invoke(prompt).strip()
        return {
            "respuesta_final": respuesta,
            "messages": [
                {"role": "human", "content": state["pregunta"]},
                {"role": "ai", "content": respuesta},
            ],
        }

    def manejar_error(state: ChatState) -> dict:
        respuesta = (
            f"Lo siento, no pude procesar tu consulta. {state.get('error', '')}\n"
            "Intenta reformular tu pregunta."
        )
        return {
            "respuesta_final": respuesta,
            "messages": [
                {"role": "human", "content": state["pregunta"]},
                {"role": "ai", "content": respuesta},
            ],
        }

    def router_intencion(state: ChatState) -> str:
        return "generar_sql" if state["intencion"] == "sql" else "responder_conversacional"

    def router_post_sql_gen(state: ChatState) -> str:
        return "manejar_error" if state.get("error") else "ejecutar_sql"

    def router_post_sql_exec(state: ChatState) -> str:
        return "manejar_error" if state.get("error") else "narrar_resultado"

    _builder = StateGraph(ChatState)
    _builder.add_node("clasificar_intencion", clasificar_intencion)
    _builder.add_node("generar_sql", generar_sql)
    _builder.add_node("ejecutar_sql", ejecutar_sql)
    _builder.add_node("narrar_resultado", narrar_resultado)
    _builder.add_node("responder_conversacional", responder_conversacional)
    _builder.add_node("manejar_error", manejar_error)
    _builder.add_edge(START, "clasificar_intencion")
    _builder.add_conditional_edges("clasificar_intencion", router_intencion)
    _builder.add_conditional_edges("generar_sql", router_post_sql_gen)
    _builder.add_conditional_edges("ejecutar_sql", router_post_sql_exec)
    _builder.add_edge("narrar_resultado", END)
    _builder.add_edge("responder_conversacional", END)
    _builder.add_edge("manejar_error", END)

    _memory = MemorySaver()
    graph = _builder.compile(checkpointer=_memory)


# ── API pública ───────────────────────────────────────────────────────────

def procesar_mensaje(
    pregunta: str,
    modelo: str,
    db: Session,
    thread_id: str = "default",
) -> dict:
    """
    Punto de entrada principal. Retorna:
    {
        "respuesta": str,
        "sql_generado": str,
        "filas": int,
        "intencion": str,
    }
    """
    if not _LANGCHAIN_AVAILABLE:
        return {
            "respuesta": "El chat SQL no está disponible en este entorno (requiere Ollama local).",
            "sql_generado": "",
            "filas": 0,
            "intencion": "",
        }

    initial_state = {
        "pregunta": pregunta,
        "modelo": modelo,
        "db": db,
        "intencion": "",
        "sql_generado": "",
        "resultado_sql": [],
        "respuesta_final": "",
        "error": None,
    }

    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial_state, config)

    return {
        "respuesta": result.get("respuesta_final", ""),
        "sql_generado": result.get("sql_generado", ""),
        "filas": len(result.get("resultado_sql", [])),
        "intencion": result.get("intencion", ""),
    }
