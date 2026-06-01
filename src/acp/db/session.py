"""Database engine / session management (sync + async)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from acp.db.base import Base


def to_sync_url(url: str) -> str:
    """Map an async SQLAlchemy URL to its sync driver equivalent."""
    return (
        url.replace("+aiosqlite", "")
        .replace("+asyncpg", "+psycopg")
        .replace("postgresql+psycopg", "postgresql+psycopg")
    )


def make_engine(database_url: str, *, echo: bool = False) -> Engine:
    sync_url = to_sync_url(database_url)
    connect_args = {"check_same_thread": False} if sync_url.startswith("sqlite") else {}
    return create_engine(sync_url, echo=echo, future=True, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    """Create all tables (test/dev convenience; prod uses Alembic)."""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
