import logging

from sqlalchemy import text

from finance_app.database import default_database_name, get_engine_for_name, ensure_database_initialized


LOGGER = logging.getLogger("finance_app.migrations.telegram_source")


def _column_exists(connection, column_name: str) -> bool:
    columns = connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
    column_names = {row[1] for row in columns}
    return column_name in column_names


def _add_column(connection, column_name: str, column_definition: str) -> None:
    if _column_exists(connection, column_name):
        return
    connection.execute(text(f"ALTER TABLE transactions ADD COLUMN {column_definition}"))


def _create_unique_index(connection) -> None:
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_transactions_source_source_id ON transactions (source, source_id)"
        )
    )


def run_migration() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_name = default_database_name()
    ensure_database_initialized(db_name)
    engine = get_engine_for_name(db_name)
    if engine.url.drivername != "sqlite":
        LOGGER.warning("Migración manual requerida: base de datos no SQLite.")
        return

    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
        if not columns:
            LOGGER.error("Tabla transactions no encontrada.")
            return

        _add_column(connection, "source", "source VARCHAR(50)")
        _add_column(connection, "source_id", "source_id VARCHAR(120)")
        _create_unique_index(connection)

    LOGGER.info("Migración completada: source/source_id agregados en transactions.")


if __name__ == "__main__":
    run_migration()
