import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from finance_app.config import get_settings
from finance_app.database import default_database_name, ensure_database_initialized, get_session_factory
from finance_app.models import Account, Currency, EmailScrapeTransaction, Transaction
from finance_app.services.transaction_service import create_transaction
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
    return db.query(Account).filter_by(currency_id=currency_id).order_by(Account.id.asc()).first()


def _resolve_account(
    db: Session,
    account_label: str,
    currency_id: int | None,
    settings,
) -> Account | None:
    normalized_label = _normalize_name(account_label)
    account_name = None
    if normalized_label in {"panama", "pnama", "ahorros usd"}:
        account_name = settings.email_panama_account
    elif normalized_label in {"colombia", "cuenta corriente cop"}:
        account_name = settings.email_colombia_account
    elif normalized_label == "mastercard_black":
        account_name = settings.email_mastercard_black_account

    account = _find_account_by_name(db, account_name)
    if account:
        return account
    return _fallback_account_by_currency(db, currency_id)


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
            account = _resolve_account(db, account_label, currency.id, settings)
            if not account:
                LOGGER.warning("No se encontró cuenta para '%s'.", account_label)
                ignored += 1
                continue

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
            if account_label.upper() == "MASTERCARD_BLACK" and not memo:
                memo = "Mastercard Black"

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
