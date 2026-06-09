from fastapi.testclient import TestClient

import api_app
from src.api_models import (
    ChatResponse,
    MaterialActionResponse,
    MaterialProgressResponse,
    MaterialsResponse,
    SectionsResponse,
    SummaryResponse,
    SystemStatus,
)


client = TestClient(api_app.app)


def test_health_endpoint():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_system_status_endpoint(monkeypatch):
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

    response = client.get("/api/system/status")

    assert response.status_code == 200
    assert response.json()["model"] == "qwen2.5:14b"


def test_materials_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "list_materials",
        lambda: MaterialsResponse(materials=[]),
    )

    response = client.get("/api/materials")

    assert response.status_code == 200
    assert response.json() == {"materials": []}


def test_material_upload_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_upload_material_service",
        lambda file_name, content: MaterialActionResponse(
            ok=True,
            message=f"uploaded:{file_name}:{len(content)}",
            material_name=file_name,
        ),
    )

    response = client.post(
        "/api/materials/upload",
        files={"file": ("book.pdf", b"hello", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["material_name"] == "book.pdf"


def test_material_progress_endpoint(monkeypatch):
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

    response = client.get("/api/materials/progress")

    assert response.status_code == 200
    assert response.json()["active"] is True
    assert response.json()["progress"] == 64


def test_sections_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "list_sections",
        lambda file_filter="all": SectionsResponse(sections=["Глава 1"]),
    )

    response = client.get("/api/materials/a.pdf/sections")

    assert response.status_code == 200
    assert response.json() == {"sections": ["Глава 1"]}


def test_material_reindex_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_reindex_material_service",
        lambda file_name=None: MaterialActionResponse(
            ok=True,
            message=f"reindex:{file_name or 'all'}",
            material_name=file_name or "",
        ),
    )

    response = client.post("/api/materials/a.pdf/reindex")

    assert response.status_code == 200
    assert response.json()["message"] == "reindex:a.pdf"


def test_library_reindex_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_reindex_material_service",
        lambda file_name=None: MaterialActionResponse(
            ok=True,
            message="reindex:all",
            material_name="",
        ),
    )

    response = client.post("/api/materials/reindex")

    assert response.status_code == 200
    assert response.json()["message"] == "reindex:all"


def test_material_delete_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "start_delete_material_service",
        lambda file_name: MaterialActionResponse(
            ok=True,
            message=f"deleted:{file_name}",
            material_name=file_name,
        ),
    )

    response = client.delete("/api/materials/a.pdf")

    assert response.status_code == 200
    assert response.json()["message"] == "deleted:a.pdf"


def test_summary_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "generate_summary_service",
        lambda request: SummaryResponse(
            text=f"summary:{request.topic}",
            diagnostics="trace",
            trace={"status": "ok"},
        ),
    )

    response = client.post(
        "/api/summaries",
        json={"topic": "Bluetooth", "summary_type": "Средний"},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "summary:Bluetooth"
    assert response.json()["diagnostics"] == "trace"
    assert response.json()["trace"] == {"status": "ok"}


def test_chat_endpoint(monkeypatch):
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

    response = client.post(
        "/api/chat",
        json={"message": "Что такое Bluetooth?", "answer_mode": "Обычный"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "answer:Что такое Bluetooth?"
    assert response.json()["summary"] == "короткий итог"
    assert response.json()["confidence_label"] == "high"
    assert response.json()["diagnostics"] == "trace"


def test_export_summary_endpoint(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "export_summary_docx_service",
        lambda request: __file__,
    )

    response = client.post(
        "/api/exports/summary",
        json={"text": "hello", "summary_type": "Средний"},
    )

    assert response.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in response.headers["content-type"]


def test_export_summary_endpoint_returns_400_for_empty_summary(monkeypatch):
    monkeypatch.setattr(
        api_app.services,
        "export_summary_docx_service",
        lambda request: None,
    )

    response = client.post(
        "/api/exports/summary",
        json={"text": ""},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "empty_summary"}
