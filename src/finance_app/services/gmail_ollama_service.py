import email as email_lib
import imaplib
import json
import logging
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)
# FUERA de la función, al inicio del archivo (se crea una sola vez)
_http_client = httpx.Client(timeout=90.0)

IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = os.getenv("GMAIL_EMAIL")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
SCRAPE_MIN_DATE = datetime(2026, 2, 3)


def _extract_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp.lower():
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/html" and "attachment" not in disp.lower():
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")
                return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def fetch_and_store_emails(
    db, since_date: datetime | None = None, max_emails: int = 50
) -> list:
    """Connect to Gmail via IMAP, store new emails in DB, return all fetched records."""
    from finance_app.models.gmail_message import GmailProcessedMessage

    if not EMAIL_ACCOUNT or not APP_PASSWORD:
        raise RuntimeError(
            "Faltan variables de entorno GMAIL_EMAIL / GMAIL_APP_PASSWORD"
        )

    effective_since = since_date
    if not effective_since or effective_since < SCRAPE_MIN_DATE:
        effective_since = SCRAPE_MIN_DATE

    imap = imaplib.IMAP4_SSL(IMAP_SERVER)
    imap.login(EMAIL_ACCOUNT, APP_PASSWORD)
    imap.select("INBOX")

    date_str = effective_since.strftime("%d-%b-%Y")
    status, data = imap.search(None, "SINCE", date_str)
    if status != "OK":
        imap.logout()
        raise RuntimeError("Error buscando correos en Gmail")

    ids = data[0].split()
    ids = ids[-max_emails:] if len(ids) > max_emails else ids

    fetched = []
    for mail_id in reversed(ids):
        status, msg_data = imap.fetch(mail_id, "(RFC822)")
        if status != "OK":
            continue

        msg = email_lib.message_from_bytes(msg_data[0][1])
        message_id = msg.get("Message-ID") or mail_id.decode(errors="ignore")
        subject = msg.get("Subject") or ""
        sender = msg.get("From") or ""

        received_at = None
        hdr = msg.get("Date")
        if hdr:
            try:
                received_at = parsedate_to_datetime(hdr).replace(tzinfo=None)
            except Exception:
                pass

        existing = (
            db.query(GmailProcessedMessage).filter_by(message_id=message_id).first()
        )
        if existing:
            fetched.append(existing)
            continue

        body = _extract_body(msg)
        record = GmailProcessedMessage(
            message_id=message_id,
            subject=subject,
            sender=sender,
            received_at=received_at,
            body_text=body,
        )
        db.add(record)
        fetched.append(record)

    db.commit()
    imap.logout()
    return fetched


def list_ollama_models() -> list[str]:
    """Return names of models available in the local Ollama instance."""
    try:
        response = _http_client.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
        response.raise_for_status()
        models = response.json().get("models", [])
        return [m["name"] for m in models if "name" in m]
    except Exception as exc:
        raise RuntimeError(f"No se pudo conectar a Ollama: {exc}")


def call_ollama(
    body_text: str,
    accounts: list[dict],
    categories: list[dict],
    merchant_rules: list[dict] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Send email body to Ollama and return extracted transaction fields."""

    # Formateo limpio de catálogos para que el LLM entienda la relación ID -> Concepto
    accounts_str = "\n".join(
        f"- id={a['id']}: {a['name']} ({(a.get('currency') or {}).get('code', '')})"
        for a in accounts
    )
    categories_str = "\n".join(f"- id={c['id']}: {c['name']}" for c in categories)

    merchant_rules_str = ""
    if merchant_rules:
        lines = "\n".join(
            f"- {r['merchant_name']} → categoria_id={r['category_id']} ({r.get('category_name', '')})"
            for r in merchant_rules
        )
        merchant_rules_str = f"\n### MAPEO EXACTO DE COMERCIOS (PRIORIDAD MÁXIMA):\nSi el nombre del comercio en el correo coincide (total o parcialmente) con alguno de los siguientes, USA ese categoria_id sin excepción:\n{lines}\n"

    # Prompt optimizado para LLMs locales con delimitadores Markdown claros
    prompt = f"""Eres un asistente automatizado de finanzas personales. Tu tarea es analizar el correo bancario adjunto y estructurar la transacción en el formato JSON solicitado.
### CORREO BANCARIO A ANALIZAR:
---
{body_text[:1500]}
---

### CATÁLOGOS DISPONIBLES:
CUENTAS_DISPONIBLES:
{accounts_str}
CATEGORÍAS_DISPONIBLES:
{categories_str}
{merchant_rules_str}
### REGLAS DE EXTRACCIÓN Y LÓGICA:
1. "fecha": Extrae la fecha de la transacción y conviértela a formato estricto YYYY-MM-DD.
2. "monto": Extrae solo el valor numérico sin símbolos de moneda.
- Si la moneda es COP: el punto es separador de miles → $85.900 = 85900.00
- Si la moneda es USD: el punto es separador decimal → $15.99 = 15.99
3. "moneda": Debe ser estrictamente "COP" o "USD". Infiere del símbolo o contexto del correo.
4. "cuenta_id": Elige el ID de la cuenta siguiendo esta prioridad:
a. Si el correo menciona el nombre o últimos dígitos de la tarjeta, úsalos para identificarla.
b. Si no, elige la cuenta cuya moneda coincida con la del correo.
c. Entre varias cuentas en la misma moneda, prefiere la que mencione
    la misma red (Mastercard, Visa, etc.) o banco.
d. Si aún es ambiguo, asigna null.
5. "categoria_id": Si el comercio aparece en el MAPEO DE COMERCIOS, usa ese ID sin excepción.
Si no, infiere por contexto. Si es ambiguo, usa null.
6. "comentario": Extrae ÚNICAMENTE el nombre del comercio o lugar donde ocurrió la transacción. NO incluyas frases de tipo de movimiento ("COMPRAS", "PAGO", "TRANSFERENCIA"), ni información del banco o tarjeta ("tarjeta débito MASTERCARD terminación XXXX"). Solo el nombre del negocio o lugar. Ejemplo: si el correo dice "COMPRAS con tarjeta débito MASTERCARD terminación 5545, en DIDI RIDES CO", el comentario es "DIDI RIDES CO".

### FORMATO DE SALIDA:
Devuelve EXCLUSIVAMENTE un objeto JSON válido. Sin bloques markdown, sin explicaciones.
{{
"fecha": "YYYY-MM-DD",
"monto": 0.00,
"moneda": "COP o USD según el correo",
"cuenta_id": null,
"categoria_id": null,
"comentario": "descripción"
}}"""

    selected_model = model or OLLAMA_MODEL
    response = _http_client.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",  # Esto obliga a Ollama a usar json-grammars
            "options": {
                "temperature": 0.1,
                "num_ctx": 2048,
                "num_predict": 150,
            },
        },
        timeout=90.0,
    )
    response.raise_for_status()

    raw = response.json().get("response", "{}").strip()

    try:
        data = json.loads(raw)

        # Post-procesamiento de seguridad: Asegurar que los IDs sean enteros o None
        if data.get("cuenta_id") is not None:
            data["cuenta_id"] = int(data["cuenta_id"])
        if data.get("categoria_id") is not None:
            data["categoria_id"] = int(data["categoria_id"])
        if data.get("monto") is not None:
            data["monto"] = float(data["monto"])

        # Validar que los IDs devueltos existan en los catálogos enviados al modelo
        valid_account_ids = {a["id"] for a in accounts}
        valid_category_ids = {c["id"] for c in categories}
        if data.get("cuenta_id") not in valid_account_ids:
            data["cuenta_id"] = None
        if data.get("categoria_id") not in valid_category_ids:
            data["categoria_id"] = None

        data["_prompt"] = prompt
        return data

    except (json.JSONDecodeError, ValueError) as e:
        # Fallback por si el modelo envuelve el JSON en markdown a pesar de las reglas
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            if data.get("cuenta_id") is not None:
                data["cuenta_id"] = int(data["cuenta_id"])
            if data.get("categoria_id") is not None:
                data["categoria_id"] = int(data["categoria_id"])
            valid_account_ids = {a["id"] for a in accounts}
            valid_category_ids = {c["id"] for c in categories}
            if data.get("cuenta_id") not in valid_account_ids:
                data["cuenta_id"] = None
            if data.get("categoria_id") not in valid_category_ids:
                data["categoria_id"] = None
            data["_prompt"] = prompt
            return data
        raise ValueError(f"Error procesando la respuesta del modelo: {raw[:200]}")
