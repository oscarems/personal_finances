import re
from datetime import datetime
from sqlalchemy.orm import Session
from finance_app.models import Account
from finance_app.models.category import Category
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


def _build_search_text(context: dict) -> str:
    fields = [
        context.get("asunto") or "",
        context.get("lugar_transaccion") or "",
        context.get("clase_movimiento") or "",
        context.get("cuenta") or "",
        context.get("remitente") or "",
    ]
    return " ".join(fields).lower()


def _match_rule(rule: EmailSenderRule, sender_pattern: str, search_text: str) -> bool:
    if rule.match_type == "sender":
        return rule.sender_pattern == sender_pattern
    else:
        keywords = [k.strip() for k in rule.sender_pattern.lower().split(",") if k.strip()]
        return any(kw in search_text for kw in keywords)


def _find_account_by_name(db: Session, name: str) -> Account | None:
    return db.query(Account).filter(Account.name == name).first()


def _builtin_account_rule(db: Session, sender_pattern: str, search_text: str) -> Account | None:
    # Remitentes de Panamá (.pa) → cuenta Panama
    if sender_pattern.endswith(".pa"):
        return _find_account_by_name(db, "Panama")
    # Emails que mencionan tarjeta de credito → Mastercard Black
    if "tarjeta de credito" in search_text or "tarjeta crédito" in search_text:
        return _find_account_by_name(db, "Mastercard Black")
    return None


def resolve_account_by_rule(db: Session, sender: str, context: dict | None = None) -> Account | None:
    sender_pattern = extract_sender_pattern(sender)
    search_text = _build_search_text(context) if context else ""

    # Reglas integradas de alta prioridad
    builtin = _builtin_account_rule(db, sender_pattern, search_text)
    if builtin:
        return builtin

    rules = (
        db.query(EmailSenderRule)
        .filter_by(rule_purpose="account", confirmed_by_user=True)
        .order_by(
            EmailSenderRule.match_type.asc(),  # "keyword" > "sender" alphabetically, so sender first
            EmailSenderRule.match_count.desc(),
        )
        .all()
    )

    # Prioridad: sender exacto primero, luego keywords
    sender_match = next(
        (r for r in rules if r.match_type == "sender" and _match_rule(r, sender_pattern, search_text)),
        None,
    )
    if sender_match and sender_match.account:
        return sender_match.account

    keyword_match = next(
        (r for r in rules if r.match_type == "keyword" and _match_rule(r, sender_pattern, search_text)),
        None,
    )
    if keyword_match and keyword_match.account:
        return keyword_match.account

    return None


def resolve_category_by_rule(db: Session, sender: str, context: dict | None = None) -> Category | None:
    sender_pattern = extract_sender_pattern(sender)
    search_text = _build_search_text(context) if context else ""

    rules = (
        db.query(EmailSenderRule)
        .filter_by(rule_purpose="category", confirmed_by_user=True)
        .order_by(EmailSenderRule.match_count.desc())
        .all()
    )

    sender_match = next(
        (r for r in rules if r.match_type == "sender" and _match_rule(r, sender_pattern, search_text)),
        None,
    )
    if sender_match and sender_match.category:
        return sender_match.category

    keyword_match = next(
        (r for r in rules if r.match_type == "keyword" and _match_rule(r, sender_pattern, search_text)),
        None,
    )
    if keyword_match and keyword_match.category:
        return keyword_match.category

    return None


def record_sender_seen(db: Session, sender: str, account_id: int) -> EmailSenderRule:
    """
    Registra o actualiza el mapeo remitente → cuenta (purpose=account).
    Si la regla ya está confirmada por el usuario, no modifica account_id.
    """
    pattern = extract_sender_pattern(sender)
    rule = db.query(EmailSenderRule).filter_by(sender_pattern=pattern, rule_purpose="account").first()

    if rule:
        rule.match_count += 1
        rule.last_seen = datetime.utcnow()
        if not rule.confirmed_by_user:
            rule.account_id = account_id
    else:
        rule = EmailSenderRule(
            sender_pattern=pattern,
            match_type="sender",
            rule_purpose="account",
            account_id=account_id,
            match_count=1,
            last_seen=datetime.utcnow(),
            confirmed_by_user=False,
        )
        db.add(rule)

    db.flush()
    return rule
