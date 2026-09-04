from __future__ import annotations

from sqlalchemy import Connection, Engine, inspect, text

from persistence.models import Base

SCHEMA_VERSION = 3


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
        if current_version < 3:
            _upgrade_v3(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (:version, CURRENT_TIMESTAMP)"
                ),
                {"version": 3},
            )


def _upgrade_v1(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)


def _upgrade_v2(connection: Connection) -> None:
    Base.metadata.tables["work_items"].create(bind=connection, checkfirst=True)


def _upgrade_v3(connection: Connection) -> None:
    Base.metadata.tables["approval_nonces"].create(bind=connection, checkfirst=True)
    approval_columns = {item["name"] for item in inspect(connection).get_columns("approvals")}
    if "request_hash" not in approval_columns:
        connection.execute(text("ALTER TABLE approvals ADD COLUMN request_hash VARCHAR(64)"))
