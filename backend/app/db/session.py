"""Database engine and session (schema.md sections 1 & 5).

The ``connect`` listener enables foreign keys, WAL, and NORMAL synchronous on
every SQLite connection. Without ``foreign_keys=ON`` every ``ON DELETE`` rule in
schema.md is inert — this is the single most commonly missed line in a SQLite
project.
"""
import sqlite3
from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

_settings = get_settings()

# check_same_thread=False lets the SQLite connection be shared across the
# threadpool FastAPI uses for sync endpoints.
engine = create_engine(
    _settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    """Enable foreign keys, WAL, and NORMAL synchronous on every SQLite connection."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def init_db() -> None:
    """Create all tables. Import models so they register with SQLModel.metadata."""
    import app.models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


# Columns added after the first databases were created. create_all() only makes
# missing tables, never missing columns, so each is added here idempotently.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("sightings", "batch_id", "TEXT"),
)


def _add_missing_columns() -> None:
    """Add post-hoc columns to an existing SQLite file, skipping ones present."""
    with engine.connect() as connection:
        for table, column, column_type in _ADDED_COLUMNS:
            existing = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                connection.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
                )
        connection.commit()


def get_session() -> Iterator[Session]:
    """Yield a database session (FastAPI dependency)."""
    with Session(engine) as session:
        yield session
