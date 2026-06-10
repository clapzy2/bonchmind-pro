"""Shared pytest fixtures for the auth/db layer.

We force ``DATABASE_URL`` to a per-test SQLite file *before* anything imports
``config``/``src.db``, then recreate the schema for every test that asks for
the ``db_session`` or ``api_client`` fixture. This keeps the new auth tests
fully isolated from each other and from the developer's local ``data/app.db``.

Existing tests don't request any fixture from this file, so their behaviour
is unchanged — pytest only invokes a fixture when the test (or another
fixture) explicitly depends on it.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest

# Override the database URL BEFORE config / src.db are imported anywhere.
_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(prefix="bonchmind_test_", suffix=".db")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-only-for-pytest")


@pytest.fixture()
def db_session() -> Generator:
    """Yield a fresh DB session backed by an empty schema."""
    from src.db import Base, SessionLocal, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def api_client() -> Generator:
    """FastAPI TestClient with an empty auth schema for each test."""
    from fastapi.testclient import TestClient

    from api_app import app
    from src.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        yield client

    Base.metadata.drop_all(bind=engine)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    """Best-effort cleanup of the temporary SQLite file."""
    try:
        os.unlink(_TMP_DB_PATH)
    except OSError:
        pass
