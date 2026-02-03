import imaplib
import email
from email.message import Message
import re
import csv
import logging
import os
from datetime import datetime
from dateutil import parser as dateparser
from dotenv import load_dotenv
from email.utils import parsedate_to_datetime

# =========================
# ENV & LOGGING
# =========================
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# =========================
# CONFIG (GMAIL)
# =========================
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = os.getenv("GMAIL_EMAIL")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

MAILBOX = "INBOX"
OUTPUT_CSV = "compras.csv"
LAST_N_EMAILS = 100  # leer últimos 100 correos

if not EMAIL_ACCOUNT or not APP_PASSWORD:
    raise RuntimeError("Faltan variables de entorno GMAIL_EMAIL / GMAIL_APP_PASSWORD")

# =========================
# HELPERS
# =========================
def extract_text_from_message(msg: Message) -> str:
    """Extrae texto plano; si no hay, convierte html simple a texto."""
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
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()
                return text
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    return ""

def normalize_amount(raw: str) -> float:
    raw = raw.strip()
    raw = re.sub(r"[^\d,.\-]", "", raw)

    if "," in raw and "." not in raw:
        if re.search(r",\d{1,2}$", raw):      # decimal
            raw = raw.replace(",", ".")
        elif re.search(r",\d{3}$", raw):      # miles
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", "")
    elif "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")

    return float(raw)

# -------- Panamá (Davivienda Panamá) --------
def parse_panama_compra_fields(text: str):
    """
    Ej:
    Se registró COMPRAS ... en 5814JUAN VALDEZ ..., por $ 7.08.
    """
    t = " ".join(text.split())

    m_amount = re.search(
        r"por\s+\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)",
        t,
        re.IGNORECASE,
    )
    amount = normalize_amount(m_amount.group(1)) if m_amount else None

    m_place = re.search(r"\ben\s+(.+?)\s*,\s*por\s+\$", t, re.IGNORECASE)
    place = m_place.group(1).strip() if m_place else None

    if place and amount is not None:
        return {
            "pais": "PANAMA",
            "cuenta": "PANAMA",
            "moneda": "USD",
            "valor": amount,
            "clase_movimiento": "",
            "lugar_transaccion": place,
        }

    return None

# -------- Colombia (Davivienda Colombia) --------
def parse_colombia_movimiento_fields(text: str):
    """
    Ej:
    Clase de Movimiento: Descuento en Internet,
    Lugar de Transacción: PSE ...
    Valor Transacción: $583,000
    """
    m_amount = re.search(
        r"(?im)^\s*Valor\s*Transacci[oó]n\s*:\s*\$?\s*([0-9][0-9.,]*)\s*$",
        text
    )
    amount = normalize_amount(m_amount.group(1)) if m_amount else None

    m_place = re.search(
        r"(?im)^\s*Lugar\s+de\s+Transacci[oó]n\s*:\s*(.+?)\s*$",
        text
    )
    place = m_place.group(1).strip() if m_place else None

    m_class = re.search(
        r"(?im)^\s*Clase\s+de\s+Movimiento\s*:\s*(.+?)\s*$",
        text
    )
    clase = m_class.group(1).strip().rstrip(",") if m_class else None

    if place and amount is not None:
        return {
            "pais": "COLOMBIA",
            "cuenta": "COLOMBIA",
            "moneda": "COP",
            "valor": amount,
            "clase_movimiento": clase or "",
            "lugar_transaccion": place,
        }

    return None

# -------- Fechas --------
def parse_datetime_from_fecha_hora(text: str):
    m_fecha = re.search(r"(?im)^\s*Fecha\s*:\s*([0-9]{4}/[0-9]{2}/[0-9]{2})\s*$", text)
    m_hora = re.search(r"(?im)^\s*Hora\s*:\s*([0-9]{2}:[0-9]{2}:[0-9]{2})\s*$", text)

    if not m_fecha:
        return None

    fecha = m_fecha.group(1).strip()
    hora = m_hora.group(1).strip() if m_hora else "00:00:00"

    try:
        return datetime.strptime(f"{fecha} {hora}", "%Y/%m/%d %H:%M:%S")
    except Exception:
        return None

def parse_datetime_from_sent_line(text: str):
    m = re.search(r"(?im)^\s*Sent:\s*(.+?)\s*$", text)
    if not m:
        return None

    raw = m.group(1).strip()
    raw = re.sub(r"\s*\([^)]*\)", "", raw).strip()

    m2 = re.search(
        r"^(?:[A-Za-z]+,\s*)?\d{1,2}\s+[A-Za-z]+\s+\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s+[AP]M)?",
        raw
    )
    if m2:
        raw = m2.group(0)

    try:
        return dateparser.parse(raw, fuzzy=True)
    except Exception:
        return None

def parse_datetime_from_headers(msg: Message):
    hdr = msg.get("Date")
    if not hdr:
        return None
    try:
        return parsedate_to_datetime(hdr)
    except Exception:
        return None

def parse_any_datetime(msg: Message, body_text: str):
    dt = parse_datetime_from_fecha_hora(body_text)
    if dt:
        return dt
    dt = parse_datetime_from_sent_line(body_text)
    if dt:
        return dt
    return parse_datetime_from_headers(msg)

# -------- Router: detecta formato --------
def parse_any_transaction(body_text: str):
    """
    Devuelve dict con:
    pais, cuenta, moneda, valor, clase_movimiento, lugar_transaccion
    """
    # 1) Colombia (porque es más estructurado)
    tx = parse_colombia_movimiento_fields(body_text)
    if tx:
        return tx

    # 2) Panamá (compra)
    tx = parse_panama_compra_fields(body_text)
    if tx:
        return tx

    return None

# =========================
# MAIN
# =========================
def main():
    logger.info("Leyendo últimos %s correos de Gmail", LAST_N_EMAILS)

    imap = imaplib.IMAP4_SSL(IMAP_SERVER)
    imap.login(EMAIL_ACCOUNT, APP_PASSWORD)
    imap.select(MAILBOX)

    status, data = imap.search(None, "ALL")
    if status != "OK":
        logger.error("Error buscando correos")
        return

    ids = data[0].split()
    ids = ids[-LAST_N_EMAILS:] if len(ids) > LAST_N_EMAILS else ids

    rows = []

    for i, mail_id in enumerate(reversed(ids), start=1):
        logger.info("Procesando correo %s/%s", i, len(ids))

        status, msg_data = imap.fetch(mail_id, "(RFC822)")
        if status != "OK":
            continue

        msg = email.message_from_bytes(msg_data[0][1])

        body = extract_text_from_message(msg)
        if not body:
            continue

        # 🚫 EXCLUIR "pending"
        if re.search(r"\bpending\b", body, re.IGNORECASE):
            logger.info("Correo ignorado (estado pending)")
            continue

        tx = parse_any_transaction(body)
        if not tx:
            continue

        dt = parse_any_datetime(msg, body)

        rows.append({
            "fecha": dt.isoformat() if dt else "",
            "valor": tx["valor"],
            "moneda": tx["moneda"],
            "cuenta": tx["cuenta"],
            "clase_movimiento": tx["clase_movimiento"],
            "lugar_transaccion": tx["lugar_transaccion"],
        })

    imap.logout()

    logger.info("Guardando CSV (%s filas)", len(rows))
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["fecha", "valor", "moneda", "cuenta", "clase_movimiento", "lugar_transaccion"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Proceso finalizado")

if __name__ == "__main__":
    main()
