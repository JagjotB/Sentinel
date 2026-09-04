from __future__ import annotations

from sqlalchemy import Connection, Engine, text

from persistence.models import Base

SCHEMA_VERSION = 2


def run_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            )
        )
        current = connection.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar()
        current_version = int(current) if current is not None else 0
        if current_version < 1:
            _upgrade_v1(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (:version, CURRENT_TIMESTAMP)"
                ),
                {"version": 1},
            )
        if current_version < 2:
            _upgrade_v2(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (:version, CURRENT_TIMESTAMP)"
                ),
                {"version": 2},
            )


def _upgrade_v1(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)


def _upgrade_v2(connection: Connection) -> None:
    Base.metadata.tables["work_items"].create(bind=connection, checkfirst=True)
