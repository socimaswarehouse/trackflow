"""Database startup initialization helpers."""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import engine
from app.database.session import Base
from app.models import load_models

logger = logging.getLogger("trackflow.database")


def initialize_database() -> None:
    """Initialize database connectivity, model loading, and schema sync."""
    load_models()
    logger.info("MODELS LOADED")

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("DATABASE CONNECTED")
    except SQLAlchemyError:
        logger.exception("DATABASE CONNECTION FAILED")
        raise

    _create_tables_if_needed()


def _create_tables_if_needed() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = set(Base.metadata.tables.keys())

    missing_tables = required_tables.difference(existing_tables)
    if missing_tables:
        Base.metadata.create_all(bind=engine)
        logger.info("DATABASE SCHEMA SYNCED")

    _sync_additive_columns()
    _ensure_approver_id_nullable()


def _sync_additive_columns() -> None:
    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("documents")}
    statements: list[str] = []

    if "document_type" not in existing_columns:
        statements.append(
            "ALTER TABLE documents "
            "ADD COLUMN document_type VARCHAR(50) NOT NULL DEFAULT 'Invoice' "
            "AFTER doc_number"
        )

    if "qty_price" not in existing_columns:
        statements.append(
            "ALTER TABLE documents "
            "ADD COLUMN qty_price VARCHAR(255) NULL "
            "AFTER status"
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    logger.info("DATABASE COLUMN SYNCED")


def _ensure_approver_id_nullable() -> None:
    """Make documents.approver_id nullable if it is not already."""
    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return

    for col in inspector.get_columns("documents"):
        if col["name"] == "approver_id" and col.get("nullable") is False:
            with engine.begin() as connection:
                # 1. Drop foreign key constraint if it exists
                try:
                    connection.execute(
                        text("ALTER TABLE documents DROP FOREIGN KEY fk_documents_approver")
                    )
                except Exception as e:
                    logger.warning("Could not drop fk_documents_approver (might not exist): %s", e)

                # 2. Modify the column to be NULL
                connection.execute(
                    text(
                        "ALTER TABLE documents "
                        "MODIFY COLUMN approver_id INT NULL"
                    )
                )

                # 3. Re-create the foreign key constraint
                try:
                    connection.execute(
                        text(
                            "ALTER TABLE documents "
                            "ADD CONSTRAINT fk_documents_approver "
                            "FOREIGN KEY (approver_id) REFERENCES approvers(id)"
                        )
                    )
                except Exception as e:
                    logger.warning("Could not re-add fk_documents_approver constraint: %s", e)

            logger.info("APPROVER_ID COLUMN SET NULLABLE SUCCESSFULLY")
            break
