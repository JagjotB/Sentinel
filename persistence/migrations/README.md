# Migrations

Schema version 1 is applied transactionally by `persistence.migration_runner`. SQLAlchemy metadata keeps
the migration portable across SQLite and PostgreSQL. Future versions must add explicit upgrade functions
and retain previous schema versions for rolling upgrades.

