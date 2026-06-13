"""Stage 14-1: streaming chat endpoint (/api/chat/stream).

Drives the endpoint through the TestClient (which collects the full streamed
body) and parses the NDJSON lines. KB/LLM are faked so no models load.
"""

from __future__ import annotations

import json

import config
from src import app_services
from src.db import SessionLocal
from src.db_models import UsageEvent, User, Workspace


class _ChatKB:
    """Minimal KB for the chat pipeline: returns context + one source."""

    def find_section_in_query(self, message, workspace_id=None):
        return None

    def search_with_sources(self, query, file_filter="all", section_filter=None, workspace_id=None):
        return ("Текст документа про тему.", [{"source_file": "a.pdf", "section": "Глава 1", "score": 0.9}])


class _EmptyKB(_ChatKB):
    def search_with_sources(self, query, file_filter="all", section_filter=None, workspace_id=None):
        return ("", [])


class _StreamLLM:
    def __init__(self, tokens):
        self._tokens = tokens

    def stream(self, prompt, temperature=None, max_tokens=None):
        for token in self._tokens:
            yield token

    def call(self, prompt, temperature=None, max_tokens=None):
        return "".join(self._tokens)


def _events(response):
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_stream_greeting_emits_single_done_no_tokens(authed_client):
    resp = authed_client.post("/api/chat/stream", json={"message": "привет"})
    events = _events(resp)
    assert all(e["type"] != "token" for e in events)
    assert events[-1]["type"] == "done"
    assert "Привет" in events[-1]["answer"]


def test_stream_generate_streams_tokens_then_done(authed_client, monkeypatch):
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: _ChatKB())
    monkeypatch.setattr(app_services.runtime, "get_llm", lambda: _StreamLLM(["Это ", "ответ", "."]))

    resp = authed_client.post(
        "/api/chat/stream",
        json={"message": "Объясни тему", "selected_file": "Все материалы", "answer_mode": "Обычный"},
    )
    events = _events(resp)

    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "Это ответ."

    done = events[-1]
    assert done["type"] == "done"
    assert done["answer"] == "Это ответ."
    assert len(done["sources"]) == 1
    assert done["sources"][0]["source_file"] == "a.pdf"
    # The user turn + assistant answer are appended to history.
    assert done["history"][-1] == {"role": "assistant", "content": "Это ответ."}


def test_stream_normalizes_em_dash_to_hyphen(authed_client, monkeypatch):
    """Bot answers print a plain hyphen — live tokens and the final answer alike."""
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: _ChatKB())
    monkeypatch.setattr(app_services.runtime, "get_llm", lambda: _StreamLLM(["Bluetooth ", "— это ", "стандарт.–конец"]))

    resp = authed_client.post("/api/chat/stream", json={"message": "Объясни тему"})
    events = _events(resp)

    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert all("—" not in t and "–" not in t for t in tokens)
    assert events[-1]["answer"] == "Bluetooth - это стандарт.-конец"


def test_stream_no_context_emits_done_without_tokens(authed_client, monkeypatch):
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: _EmptyKB())
    # get_llm must never be called on the no-context path.
    monkeypatch.setattr(
        app_services.runtime, "get_llm", lambda: (_ for _ in ()).throw(AssertionError("LLM should not run"))
    )

    resp = authed_client.post("/api/chat/stream", json={"message": "Вопрос без контекста"})
    events = _events(resp)
    assert all(e["type"] != "token" for e in events)
    assert events[-1]["type"] == "done"
    assert "НЕТ ИНФОРМАЦИИ" in events[-1]["answer"]


def test_stream_quota_exceeded_returns_402_before_stream(authed_client, monkeypatch):
    """A hit quota surfaces as a plain 402 JSON, never a half-streamed answer."""
    monkeypatch.setattr(config, "QUOTAS_ENABLED", True)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "tester@example.com").one()
        ws = db.query(Workspace).filter(Workspace.owner_user_id == user.id).one()
        for _ in range(config.PLAN_LIMITS["free"]["chat_per_day"]):
            db.add(
                UsageEvent(
                    workspace_id=ws.id,
                    user_id=user.id,
                    action="chat",
                    units=1,
                    billing_subject_type="user",
                    billing_subject_id=user.id,
                )
            )
        db.commit()
    finally:
        db.close()

    resp = authed_client.post("/api/chat/stream", json={"message": "вопрос по теме"})
    assert resp.status_code == 402
    assert resp.json()["error"] == "quota_exceeded"
