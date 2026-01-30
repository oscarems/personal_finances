import imaplib
import email
from email.message import Message
import re
import csv
import logging
import os
from dateutil import parser as dateparser
from dotenv import load_dotenv

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

def parse_compra_fields(body_text: str):
    text = " ".join(body_text.split())

    m_amount = re.search(
        r"por\s+\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)",
        text,
        re.IGNORECASE,
    )

    amount = None
    if m_amount:
        raw = m_amount.group(1)
        if raw.count(",") > 0 and raw.count(".") == 0:
            raw = raw.replace(",", ".")
        elif raw.count(",") > 0 and raw.count(".") > 0:
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        amount = float(raw)

    m_place = re.search(r"\ben\s+(.+?),\s+por\s+\$", text, re.IGNORECASE)
    place = m_place.group(1).strip() if m_place else None

    return place, amount

def parse_email_date_from_body(body_text: str):
    """
    Extrae fecha desde una línea tipo:
    Sent: 03 December 2025 11:12 PM
    """
    match = re.search(
        r"Sent:\s*([0-9]{2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{1,2}:[0-9]{2}\s+[AP]M)",
        body_text,
        re.IGNORECASE,
    )

    if not match:
        return None

    raw_date = match.group(1)

    try:
        return dateparser.parse(raw_date)
    except Exception:
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

        # 🚫 EXCLUIR MENSAJES CON "pending" (may/min)
        if re.search(r"\bpending\b", body, re.IGNORECASE):
            logger.info("Correo ignorado (estado pending)")
            continue

        place, amount = parse_compra_fields(body)
        if place and amount is not None:
            dt = parse_email_date_from_body(body)  # ✅ AQUÍ el fix
            rows.append({
                "fecha": dt.isoformat() if dt else "",
                "valor": amount,
                "lugar": place,
            })

    imap.logout()

    logger.info("Guardando CSV (%s filas)", len(rows))
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["fecha", "valor", "lugar"])
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Proceso finalizado")

if __name__ == "__main__":
    main()
