"""
Microsoft Graph integration for importing bank emails.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import BASE_DIR


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
DEVICE_CODE_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

TOKEN_CACHE_PATH = BASE_DIR / "data" / "microsoft_token.json"

DEVICE_FLOW_STATE: Dict[str, Any] = {}


def _get_config() -> Dict[str, Any]:
    import os

    return {
        "client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
        "tenant_id": os.getenv("MICROSOFT_TENANT_ID", "consumers"),
        "scopes": os.getenv("MICROSOFT_SCOPES", "Mail.Read").split(),
    }


def _ensure_client_id(config: Dict[str, Any]) -> None:
    if not config["client_id"]:
        raise ValueError(
            "MICROSOFT_CLIENT_ID no está configurado. "
            "Registra una app en Azure y configura la variable de entorno."
        )


def start_device_flow() -> Dict[str, Any]:
    config = _get_config()
    _ensure_client_id(config)
    response = requests.post(
        DEVICE_CODE_URL.format(tenant_id=config["tenant_id"]),
        data={"client_id": config["client_id"], "scope": " ".join(config["scopes"])},
        timeout=10
    )
    response.raise_for_status()
    payload = response.json()
    expires_at = time.time() + int(payload.get("expires_in", 0))
    DEVICE_FLOW_STATE.update(
        {
            "device_code": payload.get("device_code"),
            "expires_at": expires_at,
            "interval": payload.get("interval", 5),
        }
    )
    return payload


def poll_device_flow() -> Dict[str, Any]:
    config = _get_config()
    _ensure_client_id(config)
    if not DEVICE_FLOW_STATE.get("device_code"):
        raise ValueError("No hay un flujo de dispositivo activo. Inicia la conexión primero.")

    if time.time() >= DEVICE_FLOW_STATE.get("expires_at", 0):
        DEVICE_FLOW_STATE.clear()
        raise ValueError("El código de dispositivo expiró. Inicia de nuevo la conexión.")

    response = requests.post(
        TOKEN_URL.format(tenant_id=config["tenant_id"]),
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": config["client_id"],
            "device_code": DEVICE_FLOW_STATE["device_code"],
        },
        timeout=10
    )

    if response.status_code == 200:
        token_data = response.json()
        _store_token(token_data)
        DEVICE_FLOW_STATE.clear()
        return {"status": "success", "account": token_data.get("id_token_claims")}

    error_payload = response.json()
    error_code = error_payload.get("error")
    if error_code in {"authorization_pending", "slow_down"}:
        return {"status": "pending", "message": error_payload.get("error_description", "")}

    if error_code in {"authorization_declined", "expired_token"}:
        DEVICE_FLOW_STATE.clear()

    raise ValueError(error_payload.get("error_description", "Error de autenticación con Microsoft."))


def _store_token(token_data: Dict[str, Any]) -> None:
    expires_in = int(token_data.get("expires_in", 0))
    token_data["expires_at"] = time.time() + expires_in
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_PATH.write_text(json.dumps(token_data), encoding="utf-8")


def _load_token() -> Optional[Dict[str, Any]]:
    if not TOKEN_CACHE_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _refresh_token(refresh_token: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    response = requests.post(
        TOKEN_URL.format(tenant_id=config["tenant_id"]),
        data={
            "client_id": config["client_id"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(config["scopes"]),
        },
        timeout=10
    )
    if response.status_code != 200:
        return None
    token_data = response.json()
    _store_token(token_data)
    return token_data


def get_access_token() -> str:
    config = _get_config()
    _ensure_client_id(config)
    token_data = _load_token()
    if token_data and token_data.get("expires_at", 0) > time.time() + 60:
        return token_data.get("access_token")

    refresh_token = token_data.get("refresh_token") if token_data else None
    if refresh_token:
        refreshed = _refresh_token(refresh_token, config)
        if refreshed:
            return refreshed.get("access_token")

    raise ValueError("No hay un token válido. Conecta Outlook primero.")


def _normalize_domain(domain: str) -> str:
    cleaned = domain.strip().lower()
    if "@" in cleaned:
        cleaned = cleaned.split("@")[-1]
    return cleaned


def _strip_html(content: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", content)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _parse_amount(raw_amount: str) -> Optional[float]:
    if not raw_amount:
        return None
    cleaned = raw_amount.replace(" ", "")
    cleaned = cleaned.replace(".", "").replace(",", ".")
    cleaned = re.sub(r"[^\d\.-]", "", cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(raw_date: str) -> Optional[str]:
    if not raw_date:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_date, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(raw_date)
        return parsed.date().isoformat()
    except ValueError:
        return None


def _extract_field(patterns: List[str], text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group("value").strip()
    return None


def parse_transaction_from_message(message: Dict[str, Any]) -> Dict[str, Any]:
    body = message.get("body", {}) or {}
    content = body.get("content", "") or ""
    content_type = (body.get("contentType") or "").lower()
    text_content = _strip_html(content) if content_type == "html" else content

    patterns = {
        "date": [
            r"fecha[:\s]+(?P<value>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"fecha[:\s]+(?P<value>\d{4}-\d{2}-\d{2})",
        ],
        "payee": [
            r"comercio[:\s]+(?P<value>.+?)\s+(monto|valor|importe|moneda|fecha)",
            r"establecimiento[:\s]+(?P<value>.+?)\s+(monto|valor|importe|moneda|fecha)",
        ],
        "amount": [
            r"monto[:\s]+(?P<value>[\d\.,]+)",
            r"valor[:\s]+(?P<value>[\d\.,]+)",
            r"importe[:\s]+(?P<value>[\d\.,]+)",
        ],
        "currency": [
            r"moneda[:\s]+(?P<value>[A-Z]{3})",
            r"(?P<value>USD|COP|EUR|MXN|ARS)",
        ],
    }

    raw_date = _extract_field(patterns["date"], text_content)
    raw_payee = _extract_field(patterns["payee"], text_content)
    raw_amount = _extract_field(patterns["amount"], text_content)
    raw_currency = _extract_field(patterns["currency"], text_content)

    parsed_date = _parse_date(raw_date) or (
        message.get("receivedDateTime", "")[:10] if message.get("receivedDateTime") else None
    )
    parsed_amount = _parse_amount(raw_amount)

    subject = message.get("subject") or ""
    from_address = (
        message.get("from", {}).get("emailAddress", {}).get("address")
        if message.get("from")
        else None
    )

    return {
        "source_id": message.get("id"),
        "received_at": message.get("receivedDateTime"),
        "subject": subject,
        "from_address": from_address,
        "date": parsed_date,
        "payee_name": raw_payee or subject,
        "amount": parsed_amount,
        "currency": raw_currency,
        "memo": subject,
        "raw_body": text_content[:500],
    }


def fetch_bank_messages(domain: str, days: int = 30, limit: int = 50) -> List[Dict[str, Any]]:
    access_token = get_access_token()
    normalized_domain = _normalize_domain(domain)
    since = datetime.utcnow() - timedelta(days=days)
    filter_query = (
        f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"and endswith(from/emailAddress/address,'@{normalized_domain}')"
    )
    params = {
        "$select": "id,subject,from,receivedDateTime,body",
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$filter": filter_query,
    }
    response = requests.get(
        f"{GRAPH_BASE_URL}/me/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15
    )
    response.raise_for_status()
    messages = response.json().get("value", [])
    return [parse_transaction_from_message(message) for message in messages]
