"""Pydantic models for the BonchMind API."""

from typing import Any

from pydantic import BaseModel, Field


class MaterialInfo(BaseModel):
    # Stage 3c: ``id`` is the ``Document.id`` (UUID) and is the canonical
    # handle for delete/reindex/sections going forward. ``name`` stays as the
    # human-visible ``Document.original_name`` and remains the URL parameter
    # for the legacy ``/api/materials/{file_name}/*`` routes until the
    # frontend migrates. Empty default keeps the type backwards-compatible
    # for Gradio/test paths that have no Document row.
    id: str = ""
    name: str
    sections_count: int = 0
    quality_label: str = "ready"
    quality_reason: str = ""
    status: str = "ready"


class MaterialActionResponse(BaseModel):
    ok: bool = True
    message: str = ""
    material_name: str = ""


class MaterialProgressResponse(BaseModel):
    active: bool = False
    operation: str = "idle"
    phase: str = ""
    message: str = ""
    progress: int = 0
    current_file: str = ""
    error: str = ""


class SystemStatus(BaseModel):
    llm_mode: str
    model: str
    embedding_model: str
    reranker_model: str
    chunk_size: int
    hyde_enabled: bool
    total_books: int = 0
    total_chunks: int = 0


class SummaryRequest(BaseModel):
    selected_file: str = "Все файлы"
    selected_section: str = "Все разделы"
    topic: str = ""
    summary_type: str = "Средний"


class SummaryExportRequest(BaseModel):
    text: str = ""
    selected_file: str = "Все файлы"
    selected_section: str = "Все разделы"
    summary_type: str = "Средний"


class SummaryResponse(BaseModel):
    text: str
    diagnostics: str = ""
    trace: dict[str, Any] | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatSource(BaseModel):
    source_file: str = ""
    section: str = ""
    score: float = 0.0
    label: str = ""


class ChatRequest(BaseModel):
    message: str = ""
    history: list[ChatMessage] = Field(default_factory=list)
    selected_file: str = "Все файлы"
    answer_mode: str = "Обычный"


class ChatResponse(BaseModel):
    answer: str
    summary: str = ""
    confidence_label: str = ""
    followup_suggestions: list[str] = Field(default_factory=list)
    history: list[ChatMessage] = Field(default_factory=list)
    sources: list[ChatSource] = Field(default_factory=list)
    diagnostics: str = ""
    trace: dict[str, Any] | None = None


class DiagnosticsResponse(BaseModel):
    text: str
    trace: dict[str, Any] | None = None


class SectionsResponse(BaseModel):
    sections: list[str] = Field(default_factory=list)


class MaterialsResponse(BaseModel):
    materials: list[MaterialInfo] = Field(default_factory=list)
