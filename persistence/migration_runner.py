from __future__ import annotations

from sqlalchemy import Connection, Engine, text

from persistence.models import Base

SCHEMA_VERSION = 1


def run_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            )
        )
        current = connection.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar()
        if current is None or int(current) < SCHEMA_VERSION:
            _upgrade_v1(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (:version, CURRENT_TIMESTAMP)"
                ),
                {"version": SCHEMA_VERSION},
            )


def _upgrade_v1(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)
