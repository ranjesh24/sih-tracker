"""Shared test fixtures — in-memory SQLite with the FK/WAL pragma applied."""
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Importing app.db.session registers the global connect listener that turns on
# foreign_keys, so cascade/restrict rules are enforced in tests too.
import app.db.session  # noqa: F401
import app.models  # noqa: F401  (registers all tables on SQLModel.metadata)


@pytest.fixture
def session() -> Session:
    """A fresh in-memory database session with every table created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
