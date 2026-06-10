"""End-to-end tests for the BonchMind API.

Stage 3a flipped every non-public endpoint to require authentication, so all
of the original "happy path" tests now go through the ``authed_client``
fixture (registers a regular user, cookie is auto-replayed on every
subsequent request). Public endpoints stay on the bare ``api_client``
fixture so we keep verifying they don't accidentally start demanding auth.

The ``test_auth_required_for_protected_endpoints`` matrix is the safety net
that catches a missing auth dependency on any future endpoint.
"""

from src.api_models import (
    ChatResponse,
    MaterialActionResponse,
    MaterialProgressResponse,
    MaterialsResponse,
    SectionsResponse,
    SummaryResponse,
    SystemStatus,
)

import api_app


# ---------------------------------------------------------------------------
# Public endpoints — must keep working without authentication
# ---------------------------------------------------------------------------


def test_health_endpoint_is_public(api_client):
    response = api_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_register_is_public(api_client):
    response = api_client.post(
        "/api/auth/register",
        json={
            "email": "newcomer@example.com",
            "password": "password12345",
            "display_name": "Newcomer",
        },
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "newcomer@example.com"


def test_auth_login_is_public(api_client):
    api_client.post(
        "/api/auth/register",
        json={
            "email": "returning@example.com",
            "password": "password12345",
        },
    )
    # Drop the registration cookie so the login call is genuinely unauthenticated.
    api_client.cookies.clear()

    response = api_client.post(
        "/api/auth/login",
        json={"email": "returning@example.com", "password": "password12345"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "returning@example.com"


# ---------------------------------------------------------------------------
# Unauthenticated callers must be rejected on protected endpoints
# ---------------------------------------------------------------------------


_PROTECTED_ENDPOINTS = [
    ("GET", "/api/system/status"),
    ("GET", "/api/materials"),
    ("POST", "/api/materials/upload"),
    ("GET", "/api/materials/progress"),
    ("GET", "/api/materials/book.pdf/sections"),
    ("POST", "/api/materials/reindex"),
    ("POST", "/api/materials/book.pdf/reindex"),
    ("DELETE", "/api/materials/book.pdf"),
    ("POST", "/api/summaries"),
    ("POST", "/api/chat"),
    ("POST", "/api/exports/summary"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
]


def test_protected_endpoints_reject_unauthenticated_requests(api_client):
    """Each protected endpoint should answer with 401 when no session cookie
    is present. JSON payloads/uploaded files are kept minimal — the assertion
    here is about the auth gate, not the business logic."""
    for method, path in _PROTECTED_ENDPOINTS:
        if method == "POST" and "upload" in path:
            response = api_client.post(
                path,
                files={"file": ("book.pdf", b"hello", "application/pdf")},
            )
        elif method == "POST":
            response = api_client.post(path, json={})
        elif method == "DELETE":
            response = api_client.delete(path)
        else:
            response = api_client.get(path)

        assert response.status_code == 401, (
            f"{method} {path} expected 401 without auth, got {response.status_code}"
        )


_ADMIN_ENDPOINTS = [
    "/api/diagnostics/latest",
    "/api/diagnostics/latest.json",
]


def test_admin_endpoints_reject_unauthenticated_requests(api_client):
    for path in _ADMIN_ENDPOINTS:
        response = api_client.get(path)
        assert response.status_code == 401, (
            f"GET {path} expected 401 without auth, got {response.status_code}"
        )


def test_admin_endpoints_reject_regular_users(authed_client):
    """A logged-in non-superuser should hit 403, not 401."""
    for path in _ADMIN_ENDPOINTS:
        response = authed_client.get(path)
        assert response.status_code == 403, (
            f"GET {path} expected 403 for non-superuser, got {response.status_code}"
        )
        assert response.json()["detail"] == "superuser_required"


def test_admin_endpoints_allow_superusers(superuser_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services, "get_latest_diagnostics_text", lambda: "trace dump"
    )
    monkeypatch.setattr(
        api_app.services, "get_latest_diagnostics_json", lambda: {"status": "ok"}
    )

    text_response = superuser_client.get("/api/diagnostics/latest")
    json_response = superuser_client.get("/api/diagnostics/latest.json")

    assert text_response.status_code == 200
    assert text_response.json() == {"text": "trace dump"}
    assert json_response.status_code == 200
    assert json_response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Authenticated happy-path tests (parity with the pre-Stage-3a coverage)
# ---------------------------------------------------------------------------


def test_system_status_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "get_system_status",
        lambda: SystemStatus(
            llm_mode="ollama",
            model="qwen2.5:14b",
            embedding_model="BAAI/bge-m3",
            reranker_model="BAAI/bge-reranker-v2-m3",
            chunk_size=1200,
            hyde_enabled=False,
            total_books=1,
            total_chunks=2,
        ),
    )

    response = authed_client.get("/api/system/status")

    assert response.status_code == 200
    assert response.json()["model"] == "qwen2.5:14b"


def test_materials_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "list_materials",
        lambda: MaterialsResponse(materials=[]),
    )

    response = authed_client.get("/api/materials")

    assert response.status_code == 200
    assert response.json() == {"materials": []}


def test_material_upload_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_upload_material_service",
        lambda file_name, content: MaterialActionResponse(
            ok=True,
            message=f"uploaded:{file_name}:{len(content)}",
            material_name=file_name,
        ),
    )

    response = authed_client.post(
        "/api/materials/upload",
        files={"file": ("book.pdf", b"hello", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["material_name"] == "book.pdf"


def test_material_progress_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "get_material_progress",
        lambda: MaterialProgressResponse(
            active=True,
            operation="upload",
            phase="indexing",
            message="Сохраняю фрагменты",
            progress=64,
            current_file="book.pdf",
            error="",
        ),
    )

    response = authed_client.get("/api/materials/progress")

    assert response.status_code == 200
    assert response.json()["active"] is True
    assert response.json()["progress"] == 64


def test_sections_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "list_sections",
        lambda file_filter="all": SectionsResponse(sections=["Глава 1"]),
    )

    response = authed_client.get("/api/materials/a.pdf/sections")

    assert response.status_code == 200
    assert response.json() == {"sections": ["Глава 1"]}


def test_material_reindex_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_reindex_material_service",
        lambda file_name=None: MaterialActionResponse(
            ok=True,
            message=f"reindex:{file_name or 'all'}",
            material_name=file_name or "",
        ),
    )

    response = authed_client.post("/api/materials/a.pdf/reindex")

    assert response.status_code == 200
    assert response.json()["message"] == "reindex:a.pdf"


def test_library_reindex_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_reindex_material_service",
        lambda file_name=None: MaterialActionResponse(
            ok=True,
            message="reindex:all",
            material_name="",
        ),
    )

    response = authed_client.post("/api/materials/reindex")

    assert response.status_code == 200
    assert response.json()["message"] == "reindex:all"


def test_material_delete_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_delete_material_service",
        lambda file_name: MaterialActionResponse(
            ok=True,
            message=f"deleted:{file_name}",
            material_name=file_name,
        ),
    )

    response = authed_client.delete("/api/materials/a.pdf")

    assert response.status_code == 200
    assert response.json()["message"] == "deleted:a.pdf"


def test_summary_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "generate_summary_service",
        lambda request: SummaryResponse(
            text=f"summary:{request.topic}",
            diagnostics="trace",
            trace={"status": "ok"},
        ),
    )

    response = authed_client.post(
        "/api/summaries",
        json={"topic": "Bluetooth", "summary_type": "Средний"},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "summary:Bluetooth"
    assert response.json()["diagnostics"] == "trace"
    assert response.json()["trace"] == {"status": "ok"}


def test_chat_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "chat_service",
        lambda request: ChatResponse(
            answer=f"answer:{request.message}",
            summary="короткий итог",
            confidence_label="high",
            followup_suggestions=["Объясни подробнее", "Сравни с Wi-Fi"],
            history=[{"role": "user", "content": request.message}],
            sources=[],
            diagnostics="trace",
            trace={"status": "ok"},
        ),
    )

    response = authed_client.post(
        "/api/chat",
        json={"message": "Что такое Bluetooth?", "answer_mode": "Обычный"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "answer:Что такое Bluetooth?"
    assert response.json()["summary"] == "короткий итог"
    assert response.json()["confidence_label"] == "high"
    assert response.json()["diagnostics"] == "trace"


def test_export_summary_endpoint(authed_client, monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "export_summary_docx_service",
        lambda request: __file__,
    )

    response = authed_client.post(
        "/api/exports/summary",
        json={"text": "hello", "summary_type": "Средний"},
    )

    assert response.status_code == 200
    assert (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        in response.headers["content-type"]
    )


def test_export_summary_filename_uses_basename_not_backslash_split(
    authed_client, monkeypatch, tmp_path
):
    """Ensure filename extraction works with forward-slash paths (Linux/macOS)."""
    fake_file = tmp_path / "my_summary.docx"
    fake_file.write_bytes(b"PK\x03\x04")
    forward_slash_path = str(fake_file).replace("\\", "/")

    monkeypatch.setattr(
        api_app.services,
        "export_summary_docx_service",
        lambda request: forward_slash_path,
    )

    response = authed_client.post(
        "/api/exports/summary",
        json={"text": "hello", "summary_type": "Средний"},
    )

    assert response.status_code == 200
    assert "my_summary.docx" in response.headers.get("content-disposition", "")


def test_export_summary_endpoint_returns_400_for_empty_summary(
    authed_client, monkeypatch
):
    monkeypatch.setattr(
        api_app.services,
        "export_summary_docx_service",
        lambda request: None,
    )

    response = authed_client.post(
        "/api/exports/summary",
        json={"text": ""},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "empty_summary"}
