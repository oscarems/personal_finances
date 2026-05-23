import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from finance_app.config import get_settings
from finance_app.database import default_database_name, ensure_database_initialized, get_session_factory
from finance_app.models import Account, Currency, EmailScrapeTransaction, Transaction
from finance_app.services.transaction_service import create_transaction
from finance_app.services.email_sender_rule_service import (
    resolve_account_by_rule,
    resolve_category_by_rule,
    record_sender_seen,
)
import web_scrapping_email


LOGGER = logging.getLogger("finance_app.sync.email_scrape")
EMAIL_SOURCE = "email_scrape"
SCRAPE_MIN_DATE = datetime(2026, 2, 3)


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def _get_currency_map(db: Session) -> dict[str, Currency]:
    return {currency.code.upper(): currency for currency in db.query(Currency).all()}


def _find_account_by_name(db: Session, name: str | None) -> Account | None:
    if not name:
        return None
    normalized = _normalize_name(name)
    return db.query(Account).filter(text("lower(name) = :name")).params(name=normalized).first()


def _fallback_account_by_currency(db: Session, currency_id: int | None) -> Account | None:
    if currency_id is None:
        return db.query(Account).order_by(Account.id.asc()).first()
    currency = db.get(Currency, currency_id)
    if currency and currency.code == "USD":
        panama = db.query(Account).filter(Account.name == "Panama").first()
        if panama:
            return panama
    return db.query(Account).filter_by(currency_id=currency_id).order_by(Account.id.asc()).first()


def _ensure_email_sender_rules_table(db: Session) -> None:
    engine = db.get_bind()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_sender_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_pattern VARCHAR(255) NOT NULL UNIQUE,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                match_count INTEGER DEFAULT 1,
                last_seen DATETIME,
                confirmed_by_user BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
    # Agregar columna sender a email_scrape_transactions si no existe
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE email_scrape_transactions ADD COLUMN sender VARCHAR(500)"
            ))
    except Exception:
        pass  # columna ya existe


def _resolve_account(
    db: Session,
    currency_id: int | None,
    sender: str = "",
    email_context: dict | None = None,
) -> Account | None:
    account = resolve_account_by_rule(db, sender, context=email_context)
    if account:
        LOGGER.info("Cuenta resuelta por regla: sender=%r → %s", sender[:50], account.name)
        return account
    account = _fallback_account_by_currency(db, currency_id)
    if account:
        LOGGER.info("Cuenta resuelta por fallback de moneda → %s", account.name)
    return account


def _last_scraped_datetime(db: Session) -> datetime | None:
    last_dt = db.query(func.max(EmailScrapeTransaction.transaction_datetime)).scalar()
    if last_dt:
        return last_dt
    last_date = db.query(func.max(EmailScrapeTransaction.transaction_date)).scalar()
    if last_date:
        return datetime.combine(last_date, datetime.min.time())
    return None


def _effective_since_datetime(last_dt: datetime | None) -> datetime:
    if last_dt:
        since_dt = last_dt - timedelta(days=1)
    else:
        since_dt = SCRAPE_MIN_DATE
    if since_dt < SCRAPE_MIN_DATE:
        return SCRAPE_MIN_DATE
    return since_dt


def _cleanup_legacy_email_scrape_records(db: Session) -> None:
    cutoff_date = SCRAPE_MIN_DATE.date()
    email_deleted = db.query(EmailScrapeTransaction).filter(
        EmailScrapeTransaction.transaction_date < cutoff_date
    ).delete(synchronize_session=False)
    tx_deleted = db.query(Transaction).filter(
        Transaction.source == EMAIL_SOURCE,
        Transaction.date < cutoff_date,
    ).delete(synchronize_session=False)
    if email_deleted or tx_deleted:
        db.commit()
        LOGGER.info(
            "Eliminadas transacciones previas al %s: email=%s, movimientos=%s",
            cutoff_date.isoformat(),
            email_deleted,
            tx_deleted,
        )


def _ensure_transaction_source_columns(db: Session) -> bool:
    engine = db.get_bind()
    if engine.url.drivername != "sqlite":
        return True
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
    column_names = {row[1] for row in columns}
    return {"source", "source_id"}.issubset(column_names)


def sync_email_transactions() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()

    db_name = default_database_name()
    ensure_database_initialized(db_name)
    session_factory = get_session_factory(db_name)
    db = session_factory()

    try:
        if not _ensure_transaction_source_columns(db):
            LOGGER.error(
                "La base de datos no tiene columnas source/source_id. "
                "Ejecuta la migración antes de sincronizar."
            )
            return 1

        _ensure_email_sender_rules_table(db)
        _cleanup_legacy_email_scrape_records(db)

        currency_map = _get_currency_map(db)
        last_dt = _last_scraped_datetime(db)
        since_dt = _effective_since_datetime(last_dt)
        rows = web_scrapping_email.fetch_transactions(since_date=since_dt)

        inserted = 0
        ignored = 0

        for row in rows:
            message_id = row.get("message_id")
            if not message_id:
                ignored += 1
                continue

            existing = db.query(EmailScrapeTransaction).filter_by(message_id=message_id).first()
            if existing:
                ignored += 1
                continue

            currency_code = (row.get("moneda") or "").upper()
            currency = currency_map.get(currency_code)
            if not currency:
                LOGGER.warning("Moneda '%s' no encontrada en la base.", currency_code)
                ignored += 1
                continue

            account_label = row.get("cuenta") or "SIN_CUENTA"
            sender = row.get("remitente") or ""
            email_context = {
                "asunto": row.get("asunto") or "",
                "remitente": sender,
                "lugar_transaccion": row.get("lugar_transaccion") or "",
                "clase_movimiento": row.get("clase_movimiento") or "",
                "cuenta": account_label,
            }
            account = _resolve_account(db, currency.id, sender=sender, email_context=email_context)
            if not account:
                LOGGER.warning("No se encontró cuenta para '%s'.", account_label)
                ignored += 1
                continue

            category = resolve_category_by_rule(db, sender, context=email_context)

            if sender and account:
                try:
                    record_sender_seen(db, sender, account.id)
                except Exception as exc:
                    LOGGER.warning("Error registrando regla de remitente: %s", exc)

            raw_datetime = row.get("fecha")
            tx_datetime = None
            if raw_datetime:
                try:
                    tx_datetime = datetime.fromisoformat(raw_datetime)
                except ValueError:
                    tx_datetime = None
            tx_date = tx_datetime.date() if tx_datetime else date.today()

            email_row = EmailScrapeTransaction(
                message_id=message_id,
                transaction_date=tx_date,
                transaction_datetime=tx_datetime,
                amount=float(row.get("valor") or 0),
                currency=currency_code,
                account_label=account_label,
                movement_class=row.get("clase_movimiento") or None,
                location=row.get("lugar_transaccion") or None,
                sender=sender or None,
            )
            db.add(email_row)
            db.commit()

            existing_tx = db.query(Transaction).filter_by(
                source=EMAIL_SOURCE,
                source_id=message_id
            ).first()
            if existing_tx:
                ignored += 1
                continue

            memo = row.get("clase_movimiento") or None

            data = {
                "account_id": account.id,
                "date": tx_date,
                "payee_name": row.get("lugar_transaccion") or account_label,
                "memo": memo,
                "amount": -abs(float(row.get("valor") or 0)),
                "currency_id": currency.id,
                "cleared": False,
                "source": EMAIL_SOURCE,
                "source_id": message_id,
                "category_id": category.id if category else None,
            }
            try:
                create_transaction(db, data)
                db.commit()
                inserted += 1
            except Exception as exc:
                db.rollback()
                LOGGER.warning("Error insertando transacción %s: %s", message_id, exc)
                ignored += 1

        LOGGER.info(
            "Email sync completado. Insertados=%s Ignorados=%s",
            inserted,
            ignored
        )
        return 0
    finally:
        db.close()


def main() -> None:
    raise SystemExit(sync_email_transactions())


if __name__ == "__main__":
    main()
