import re
from datetime import datetime
from sqlalchemy.orm import Session
from finance_app.models import Account
from finance_app.models.email_sender_rule import EmailSenderRule


def extract_sender_pattern(sender: str) -> str:
    """
    Extrae el dominio del remitente como patrón.
    "Banco Davivienda <alertas@davivienda.com.pa>" → "@davivienda.com.pa"
    Si no hay @, retorna el string normalizado completo.
    """
    sender = sender.strip().lower()
    m = re.search(r"<([^>]+)>", sender)
    if m:
        sender = m.group(1).strip()
    if "@" in sender:
        return "@" + sender.split("@", 1)[1]
    return sender


def resolve_account_by_rule(db: Session, sender: str) -> Account | None:
    """Retorna cuenta si existe regla confirmada para este remitente."""
    pattern = extract_sender_pattern(sender)
    rule = db.query(EmailSenderRule).filter_by(
        sender_pattern=pattern,
        confirmed_by_user=True,
    ).first()
    return rule.account if rule and rule.account else None


def record_sender_seen(db: Session, sender: str, account_id: int) -> EmailSenderRule:
    """
    Registra o actualiza el mapeo remitente → cuenta.
    Si la regla ya está confirmada por el usuario, no modifica account_id.
    """
    pattern = extract_sender_pattern(sender)
    rule = db.query(EmailSenderRule).filter_by(sender_pattern=pattern).first()

    if rule:
        rule.match_count += 1
        rule.last_seen = datetime.utcnow()
        if not rule.confirmed_by_user:
            rule.account_id = account_id
    else:
        rule = EmailSenderRule(
            sender_pattern=pattern,
            account_id=account_id,
            match_count=1,
            last_seen=datetime.utcnow(),
            confirmed_by_user=False,
        )
        db.add(rule)

    db.flush()
    return rule
