"""Tests for the superuser-only admin endpoints (Stage 9b).

Covers access control (401 anonymous / 403 regular user / 200 superuser) plus
the shape and content of ``/api/admin/stats`` and ``/api/admin/audit``.
"""

from __future__ import annotations

import pytest


ADMIN_PATHS = ["/api/admin/stats", "/api/admin/audit"]


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_requires_authentication(api_client, path):
    """Anonymous callers get 401 on every admin endpoint."""
    resp = api_client.get(path)
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_forbidden_for_regular_user(authed_client, path):
    """A logged-in non-superuser gets 403 — the admin surface is fully gated."""
    resp = authed_client.get(path)
    assert resp.status_code == 403


class _StubKB:
    """Stand-in for ``runtime.get_kb()`` so the reconcile endpoint test never
    instantiates the real KnowledgeBase (which would load the 2 GB BGE models)."""

    def list_workspace_ids(self):
        return []

    def remove_orphan_chunks(self, **kwargs):
        return {"removed_chunks": 0, "removed_document_ids": []}


def test_admin_reconcile_requires_authentication(api_client):
    assert api_client.post("/api/admin/reconcile").status_code == 401


def test_admin_reconcile_forbidden_for_regular_user(authed_client):
    assert authed_client.post("/api/admin/reconcile").status_code == 403


def test_admin_reconcile_runs_for_superuser(superuser_client, monkeypatch):
    """Superuser can run reconcile; response carries the totals shape.

    ``runtime.get_kb`` is stubbed so the test exercises the endpoint wiring
    (auth gate → service → audit → response model) without loading models.
    """
    from src import runtime

    monkeypatch.setattr(runtime, "get_kb", lambda: _StubKB())

    resp = superuser_client.post("/api/admin/reconcile")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"workspaces", "total_removed_chunks", "total_removed_documents"}
    assert body["workspaces"] == []
    assert body["total_removed_chunks"] == 0
    assert body["total_removed_documents"] == 0


def test_admin_stats_counts_whole_instance(superuser_client):
    """Stats count every user/workspace in the instance, not just the caller's."""
    from src import auth_service
    from src.auth_models import UserCreate
    from src.db import SessionLocal

    # Seed a second user directly via the service (not through the HTTP client,
    # which would replace the superuser's session cookie with the new user's).
    db = SessionLocal()
    try:
        auth_service.register_user(
            db, UserCreate(email="second@example.com", password="password12345")
        )
    finally:
        db.close()

    resp = superuser_client.get("/api/admin/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"users", "workspaces", "documents", "audit_events"}
    # admin (from the fixture) + the second user we just seeded.
    assert body["users"] == 2
    assert body["workspaces"] == 2
    assert body["documents"] == 0
    assert body["audit_events"] >= 0


def test_admin_audit_lists_recent_events_newest_first(superuser_client):
    """The audit endpoint surfaces recorded events newest-first with full fields."""
    from src import audit_service

    audit_service.record(audit_service.ACTION_UPLOAD, target="first.pdf", ip="1.1.1.1")
    audit_service.record(audit_service.ACTION_DELETE, target="second.pdf", ip="2.2.2.2")

    resp = superuser_client.get("/api/admin/audit")
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert len(events) >= 2

    # Newest first: the DELETE we recorded last leads.
    top = events[0]
    assert top["action"] == audit_service.ACTION_DELETE
    assert top["target"] == "second.pdf"
    assert top["ip"] == "2.2.2.2"
    assert events[1]["action"] == audit_service.ACTION_UPLOAD
    assert set(top) >= {
        "id",
        "action",
        "user_id",
        "workspace_id",
        "target",
        "ip",
        "created_at",
    }


def test_admin_audit_limit_is_clamped(superuser_client):
    """``limit`` below 1 clamps up to 1; a huge limit just returns everything."""
    from src import audit_service

    for i in range(5):
        audit_service.record(audit_service.ACTION_LOGIN, target=f"event-{i}")

    resp = superuser_client.get("/api/admin/audit", params={"limit": 0})
    assert resp.status_code == 200
    assert len(resp.json()["events"]) == 1

    resp = superuser_client.get("/api/admin/audit", params={"limit": 100_000})
    assert resp.status_code == 200
    assert len(resp.json()["events"]) >= 5
