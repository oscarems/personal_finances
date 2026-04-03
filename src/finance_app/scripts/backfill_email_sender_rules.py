"""
Backfill de reglas de remitente desde historial de EmailScrapeTransaction.
Uso: python src/finance_app/scripts/backfill_email_sender_rules.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from finance_app.database import default_database_name, ensure_database_initialized, get_session_factory
from finance_app.models import Transaction, EmailScrapeTransaction
from finance_app.services.email_sender_rule_service import record_sender_seen
from finance_app.sync.email_scrape_sync import _ensure_email_sender_rules_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("backfill_email_sender_rules")
EMAIL_SOURCE = "email_scrape"


def run():
    db_name = default_database_name()
    ensure_database_initialized(db_name)
    session_factory = get_session_factory(db_name)
    db = session_factory()

    try:
        _ensure_email_sender_rules_table(db)

        email_rows = db.query(EmailScrapeTransaction).all()

        processed = 0
        skipped = 0

        for email_row in email_rows:
            tx = db.query(Transaction).filter_by(
                source=EMAIL_SOURCE,
                source_id=email_row.message_id,
            ).first()

            if not tx:
                skipped += 1
                continue

            # Usar el remitente real si existe, sino un proxy desde account_label
            sender_real = email_row.sender or f"historial:{email_row.account_label.lower()}"

            try:
                record_sender_seen(db, sender_real, tx.account_id)
                processed += 1
            except Exception as exc:
                LOGGER.warning("Error procesando message_id=%s: %s", email_row.message_id, exc)
                skipped += 1

        db.commit()
        LOGGER.info("Backfill completado. Procesados=%s Omitidos=%s", processed, skipped)

    finally:
        db.close()


if __name__ == "__main__":
    run()
