"""SQLAlchemy engine + session factory for the multi-user foundation.

This module only sets up the connection plumbing. ORM models live in
``src.db_models`` and are registered against :data:`Base` defined here.

Design notes:
- ``DATABASE_URL`` is read from :mod:`config`, which in turn reads it from the
  environment. Tests override it via env var before importing this module
  (see ``tests/conftest.py``).
- For SQLite we pass ``check_same_thread=False`` so the FastAPI test client and
  background threads (used by ``src.app_services``) can share a connection
  without raising.
- The actual schema is created by Alembic migrations
  (``alembic upgrade head``). Tests use ``Base.metadata.create_all(engine)``
  directly through a fixture — Alembic is reserved for real deployments.
"""

from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import config


def _build_engine(database_url: str):
    """Create a SQLAlchemy engine with sensible defaults per backend."""
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        # FastAPI test client and background indexer threads need to share
        # the connection; this is the standard SQLite-with-threads recipe.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, future=True)


engine = _build_engine(config.DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models in :mod:`src.db_models`."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
