"""Shared pytest fixtures.

Each test gets a fresh in-memory DuckDB. Most fixtures also create a seeded test
user; ``auth_client`` is a TestClient carrying that user's session cookie.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.db as db_module
from app.auth import SESSION_COOKIE, create_session
from app.db import Database
from app.main import create_app
from app.services.seed import seed_user


@pytest.fixture()
def db(tmp_path) -> Database:
    # File-backed (not :memory:) so thread-local connections opened by TestClient
    # request threads all see the same database.
    database = Database(str(tmp_path / "test.db"))
    database.migrate()
    db_module._db = database
    yield database
    database.close()
    db_module._db = None


def _create_user(db: Database, email: str, sub: str, name: str) -> UUID:
    row = db.query_one(
        "INSERT INTO users (google_sub, email, name) VALUES (?, ?, ?) RETURNING id",
        [sub, email, name],
    )
    seed_user(db, row["id"])
    return row["id"]


@pytest.fixture()
def make_user(db: Database) -> Callable[..., UUID]:
    """Factory to create additional seeded users (for isolation tests)."""

    def _factory(email: str = "extra@example.com", sub: str = "sub-extra", name: str = "Extra"):
        return _create_user(db, email, sub, name)

    return _factory


@pytest.fixture()
def user_id(db: Database) -> UUID:
    return _create_user(db, "user@example.com", "sub-user", "Test User")


@pytest.fixture()
def client(db: Database) -> TestClient:
    # Unauthenticated client (lifespan skipped — the in-memory db fixture stands in).
    return TestClient(create_app(), raise_server_exceptions=True)


@pytest.fixture()
def auth_client(db: Database, user_id: UUID) -> TestClient:
    c = TestClient(create_app(), raise_server_exceptions=True)
    token = create_session(db, user_id)
    c.cookies.set(SESSION_COOKIE, token)
    return c
