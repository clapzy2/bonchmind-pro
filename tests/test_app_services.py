import config
from src import app_services
from src.api_models import ChatRequest, SummaryExportRequest, SummaryRequest


# Stage 3b: every service function takes ``workspace_id`` as its first
# argument. Using a fixed string keeps assertions predictable and verifies
# that the path layout / KB scoping uses what the caller passes in, not the
# legacy ``DEFAULT_WORKSPACE_ID`` bridge.
WORKSPACE_ID = "test-workspace"


def setup_function():
    app_services.reset_material_progress_for_tests()


class FakeKB:
    """Test double for KnowledgeBase.

    All methods accept ``workspace_id`` as a keyword argument matching the
    real ``KnowledgeBase`` signature and capture the value into
    ``self.calls`` so tests can assert the scoping is correct.
    """

    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []

    def stats(self, workspace_id=None):
        self.calls.append(("stats", workspace_id))
        return {
            "total_books": 2,
            "total_chunks": 10,
            "books": ["a.pdf", "b.pdf"],
            "sections": ["Глава 1", "Глава 2"],
        }

    def get_available_sections(self, workspace_id=None):
        self.calls.append(("get_available_sections", workspace_id))
        return ["Глава 1", "Глава 2"]

    def get_sections_for_file(self, file_name, workspace_id=None):
        self.calls.append(("get_sections_for_file", workspace_id))
        mapping = {
            "a.pdf": ["Глава 1", "Глава 2"],
            "b.pdf": ["Введение"],
        }
        return mapping.get(file_name, [])

    def get_file_profile(self, file_name, workspace_id=None):
        self.calls.append(("get_file_profile", workspace_id))
        mapping = {
            "a.pdf": {"chunk_count": 6, "sections_count": 2, "sections": ["Глава 1", "Глава 2"]},
            "b.pdf": {"chunk_count": 3, "sections_count": 1, "sections": ["Введение"]},
        }
        return mapping.get(file_name, {"chunk_count": 0, "sections_count": 0, "sections": []})

    def remove_book(self, file_name, workspace_id=None):
        self.calls.append(("remove_book", workspace_id))
        return f"🗑️ {file_name}: удалено 3 фрагментов"

    def add_book(self, file_path, workspace_id=None, progress_callback=None):
        self.calls.append(("add_book", workspace_id))
        return f"✅ {file_path}: добавлено 3 фрагментов"

    def clear(self, workspace_id=None):
        self.calls.append(("clear", workspace_id))
        return "✅ База очищена"

    def index_all_books(self, workspace_id=None, progress_callback=None):
        self.calls.append(("index_all_books", workspace_id))
        return "📚 Найдено файлов: 2"


def test_get_system_status_uses_config_and_kb_stats(monkeypatch):
    fake = FakeKB()
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: fake)

    status = app_services.get_system_status(WORKSPACE_ID)

    assert status.llm_mode == config.LLM_MODE
    assert status.embedding_model == config.EMBEDDING_MODEL
    assert status.total_books == 2
    assert status.total_chunks == 10
    assert ("stats", WORKSPACE_ID) in fake.calls


def test_list_materials_maps_books_to_material_info(monkeypatch):
    fake = FakeKB()
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: fake)

    response = app_services.list_materials(WORKSPACE_ID)

    assert [item.name for item in response.materials] == ["a.pdf", "b.pdf"]
    assert [item.sections_count for item in response.materials] == [2, 1]
    assert [item.quality_label for item in response.materials] == ["ready", "ready"]
    # Both the stats call and the per-file profile lookups must be scoped.
    assert all(workspace == WORKSPACE_ID for _, workspace in fake.calls)


def test_list_materials_keeps_plain_text_but_hides_empty_materials(monkeypatch):
    class MixedKB(FakeKB):
        def stats(self, workspace_id=None):
            self.calls.append(("stats", workspace_id))
            return {
                "total_books": 4,
                "total_chunks": 10,
                "books": ["a.pdf", "story.txt", "weak.txt", "b.pdf"],
                "sections": ["Глава 1", "Глава 2"],
            }

        def get_file_profile(self, file_name, workspace_id=None):
            self.calls.append(("get_file_profile", workspace_id))
            mapping = {
                "a.pdf": {"chunk_count": 6, "sections_count": 2, "sections": ["Глава 1", "Глава 2"]},
                "story.txt": {"chunk_count": 2, "sections_count": 0, "sections": []},
                "weak.txt": {"chunk_count": 0, "sections_count": 0, "sections": []},
                "b.pdf": {"chunk_count": 3, "sections_count": 1, "sections": ["Введение"]},
            }
            return mapping.get(file_name, {"chunk_count": 0, "sections_count": 0, "sections": []})

    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: MixedKB())

    response = app_services.list_materials(WORKSPACE_ID)

    assert [item.name for item in response.materials] == ["a.pdf", "story.txt", "b.pdf"]
    assert [item.quality_label for item in response.materials] == ["ready", "plain_text", "ready"]


def test_list_sections_returns_all_sections(monkeypatch):
    fake = FakeKB()
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: fake)

    response = app_services.list_sections(WORKSPACE_ID, file_filter="all")

    assert response.sections == ["Глава 1", "Глава 2"]
    assert ("get_available_sections", WORKSPACE_ID) in fake.calls


def test_list_sections_returns_sections_for_specific_file(monkeypatch):
    fake = FakeKB()
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: fake)

    response = app_services.list_sections(WORKSPACE_ID, file_filter="a.pdf")

    assert response.sections == ["Глава 1", "Глава 2"]
    assert ("get_sections_for_file", WORKSPACE_ID) in fake.calls


def test_list_sections_normalizes_all_materials_label(monkeypatch):
    file_filters = []

    class TrackingKB(FakeKB):
        def get_available_sections(self, file_filter="all", workspace_id=None):
            self.calls.append(("get_available_sections", workspace_id))
            file_filters.append(file_filter)
            return ["Глава 1"]

    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: TrackingKB())

    response = app_services.list_sections(WORKSPACE_ID, file_filter="Все материалы")

    assert response.sections == ["Глава 1"]
    assert file_filters == ["all"]


def test_upload_material_service_saves_file_and_indexes(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.upload_material_service(WORKSPACE_ID, "book.pdf", b"hello")

    assert response.ok is True
    assert response.material_name == "book.pdf"
    # File must land under docs/<workspace_id>/, never under the legacy default.
    assert (docs_dir / WORKSPACE_ID / "book.pdf").read_bytes() == b"hello"
    assert not (docs_dir / config.DEFAULT_WORKSPACE_ID / "book.pdf").exists()


def test_upload_rejects_file_exceeding_size_limit(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.config, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.upload_material_service(WORKSPACE_ID, "book.pdf", b"x" * 11)

    assert response.ok is False
    assert "слишком большой" in response.message.lower()


def test_upload_rejects_unsupported_format(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.upload_material_service(WORKSPACE_ID, "virus.exe", b"payload")

    assert response.ok is False
    assert "формат" in response.message.lower()


def test_delete_material_service_removes_file_and_index(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    workspace_dir = docs_dir / WORKSPACE_ID
    workspace_dir.mkdir(parents=True)
    target = workspace_dir / "book.pdf"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.delete_material_service(WORKSPACE_ID, "book.pdf")

    assert response.ok is True
    assert not target.exists()
    assert "Файл убран из библиотеки" in response.message


def test_reindex_material_service_rebuilds_single_file(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    workspace_dir = docs_dir / WORKSPACE_ID
    workspace_dir.mkdir(parents=True)
    target = workspace_dir / "book.pdf"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.reindex_material_service(WORKSPACE_ID, "book.pdf")

    assert response.ok is True
    assert response.material_name == "book.pdf"


def test_reindex_material_service_rebuilds_full_library(monkeypatch):
    fake = FakeKB()
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: fake)

    response = app_services.reindex_material_service(WORKSPACE_ID)

    assert response.ok is True
    assert "База очищена" in response.message
    assert ("clear", WORKSPACE_ID) in fake.calls
    assert ("index_all_books", WORKSPACE_ID) in fake.calls


def test_material_progress_defaults_to_idle():
    progress = app_services.get_material_progress(WORKSPACE_ID)

    assert progress.active is False
    assert progress.operation == "idle"
    assert progress.progress >= 0


def test_material_progress_is_scoped_per_workspace():
    """A pending job in one workspace must not appear in another's progress."""
    other_workspace = "another-workspace"
    app_services._set_material_progress(
        WORKSPACE_ID,
        active=True,
        operation="upload",
        current_file="secret.pdf",
        message="Загружаю secret.pdf",
        progress=42,
    )

    own = app_services.get_material_progress(WORKSPACE_ID)
    foreign = app_services.get_material_progress(other_workspace)

    assert own.active is True
    assert own.current_file == "secret.pdf"
    assert foreign.active is False
    assert foreign.current_file == ""
    assert foreign.message == ""
    assert foreign.progress == 0


def test_upload_material_service_marks_progress_done(monkeypatch, tmp_path):
    class ProgressKB(FakeKB):
        def add_book(self, file_path, workspace_id=None, progress_callback=None):
            self.calls.append(("add_book", workspace_id))
            if progress_callback:
                progress_callback(phase="reading", progress=10, message="Читаю файл")
                progress_callback(phase="indexing", progress=80, message="Сохраняю фрагменты")
            return "✅ done"

    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: ProgressKB())

    response = app_services.upload_material_service(WORKSPACE_ID, "book.pdf", b"hello")
    progress = app_services.get_material_progress(WORKSPACE_ID)

    assert response.ok is True
    assert progress.active is False
    assert progress.progress == 100
    assert "готов" in progress.message.lower()


def test_start_reindex_material_service_queues_background_job(monkeypatch):
    calls = []

    monkeypatch.setattr(
        app_services,
        "reindex_material_service",
        lambda workspace_id, file_name=None: calls.append((workspace_id, file_name))
        or app_services.MaterialActionResponse(
            ok=True,
            message="done",
            material_name=file_name or "",
        ),
    )

    response = app_services.start_reindex_material_service(WORKSPACE_ID, "book.pdf")

    assert response.ok is True
    assert "Запустил" in response.message


def test_generate_summary_service_calls_summary_handler(monkeypatch):
    calls = []

    monkeypatch.setattr(app_services.runtime, "get_llm", lambda: "llm")
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: "kb")
    monkeypatch.setattr(app_services.main, "_llm", None)
    monkeypatch.setattr(app_services.main, "_kb", None)
    monkeypatch.setattr(
        app_services.main,
        "on_generate_summary",
        lambda *args: calls.append(args) or "summary text",
    )
    monkeypatch.setattr(app_services, "format_last_trace", lambda: "trace text")

    response = app_services.generate_summary_service(
        WORKSPACE_ID,
        SummaryRequest(
            selected_file="a.pdf",
            selected_section="Глава 1",
            topic="Bluetooth",
            summary_type="Средний",
        ),
    )

    assert response.text == "summary text"
    assert response.diagnostics == "trace text"
    assert app_services.main._llm == "llm"
    assert app_services.main._kb == "kb"
    assert calls[0][0] == "a.pdf"


def test_generate_summary_service_normalizes_all_materials_label(monkeypatch):
    calls = []

    monkeypatch.setattr(app_services.runtime, "get_llm", lambda: "llm")
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: "kb")
    monkeypatch.setattr(app_services.main, "_llm", None)
    monkeypatch.setattr(app_services.main, "_kb", None)
    monkeypatch.setattr(
        app_services.main,
        "on_generate_summary",
        lambda *args: calls.append(args) or "summary text",
    )
    monkeypatch.setattr(app_services, "format_last_trace", lambda: "trace text")

    app_services.generate_summary_service(
        WORKSPACE_ID,
        SummaryRequest(
            selected_file="Все материалы",
            selected_section="Все разделы",
            topic="Россия после Николая II до 2000 года",
            summary_type="Средний",
        ),
    )

    assert calls[0][0] == "Все файлы"


def test_export_summary_docx_service_uses_export_utils(monkeypatch):
    calls = []

    monkeypatch.setattr(
        app_services,
        "export_text_to_docx",
        lambda **kwargs: calls.append(kwargs) or "exports/test.docx",
    )

    path = app_services.export_summary_docx_service(
        SummaryExportRequest(
            text="summary body",
            selected_file="Все материалы",
            selected_section="Все разделы",
            summary_type="Средний",
        )
    )

    assert path == "exports/test.docx"
    assert calls[0]["name_parts"][0] == "Все файлы"


def test_export_summary_docx_service_returns_none_for_empty_text():
    path = app_services.export_summary_docx_service(
        SummaryExportRequest(text="   "),
    )

    assert path is None


def test_chat_service_returns_greeting_without_runtime(monkeypatch):
    response = app_services.chat_service(
        WORKSPACE_ID,
        ChatRequest(message="Привет"),
    )

    assert response.answer == "Привет! Задайте вопрос по загруженным текстам."
    assert response.history[-1].role == "assistant"
    assert response.summary == "Привет! Задайте вопрос по загруженным текстам."
    assert response.confidence_label == "system"


def test_chat_service_returns_structured_answer(monkeypatch):
    received = {}

    class FakeKBForChat:
        def find_section_in_query(self, message, workspace_id=None):
            received["find_section"] = workspace_id
            return None

        def search_with_sources(self, query, file_filter="all", section_filter=None, workspace_id=None):
            received["search"] = workspace_id
            return (
                "контекст",
                [{"source_file": "book.pdf", "section": "Глава 1", "score": 0.91}],
            )

    class FakeLLMForChat:
        def call(self, prompt, max_tokens=None, temperature=None):
            return "Готовый ответ"

    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKBForChat())
    monkeypatch.setattr(app_services.runtime, "get_llm", lambda: FakeLLMForChat())

    response = app_services.chat_service(
        WORKSPACE_ID,
        ChatRequest(
            message="Что такое Bluetooth?",
            selected_file="Все материалы",
            answer_mode="Обычный",
        ),
    )

    assert response.answer == "Готовый ответ"
    assert response.history[-1].content == "Готовый ответ"
    assert response.sources[0].label == "book.pdf -> Глава 1"
    assert response.summary == "Готовый ответ"
    assert response.confidence_label == "medium"
    assert len(response.followup_suggestions) == 3
    # Both KB queries must be scoped to the caller's workspace.
    assert received["find_section"] == WORKSPACE_ID
    assert received["search"] == WORKSPACE_ID
