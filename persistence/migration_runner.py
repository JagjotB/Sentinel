from __future__ import annotations

from sqlalchemy import Connection, Engine, inspect, text

from persistence.models import Base

SCHEMA_VERSION = 4


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
        if current_version < 4:
            _upgrade_v4(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (:version, CURRENT_TIMESTAMP)"
                ),
                {"version": 4},
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


def _upgrade_v4(connection: Connection) -> None:
    work_columns = {item["name"] for item in inspect(connection).get_columns("work_items")}
    if "parent_trace_id" not in work_columns:
        connection.execute(text("ALTER TABLE work_items ADD COLUMN parent_trace_id VARCHAR(32)"))
        connection.execute(
            text("CREATE INDEX ix_work_items_parent_trace_id ON work_items (parent_trace_id)")
        )
