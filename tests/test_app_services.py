import config
from src import app_services
from src.api_models import ChatRequest, SummaryExportRequest, SummaryRequest


def setup_function():
    app_services.reset_material_progress_for_tests()


class FakeKB:
    def stats(self):
        return {
            "total_books": 2,
            "total_chunks": 10,
            "books": ["a.pdf", "b.pdf"],
            "sections": ["Глава 1", "Глава 2"],
        }

    def get_available_sections(self, file_filter="all"):
        return ["Глава 1", "Глава 2"]

    def get_sections_for_file(self, file_name):
        mapping = {
            "a.pdf": ["Глава 1", "Глава 2"],
            "b.pdf": ["Введение"],
        }
        return mapping.get(file_name, [])

    def get_file_profile(self, file_name):
        mapping = {
            "a.pdf": {"chunk_count": 6, "sections_count": 2, "sections": ["Глава 1", "Глава 2"]},
            "b.pdf": {"chunk_count": 3, "sections_count": 1, "sections": ["Введение"]},
        }
        return mapping.get(file_name, {"chunk_count": 0, "sections_count": 0, "sections": []})

    def remove_book(self, file_name):
        return f"🗑️ {file_name}: удалено 3 фрагментов"

    def add_book(self, file_path):
        return f"✅ {file_path}: добавлено 3 фрагментов"

    def clear(self):
        return "✅ База очищена"

    def index_all_books(self):
        return "📚 Найдено файлов: 2"


def test_get_system_status_uses_config_and_kb_stats(monkeypatch):
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    status = app_services.get_system_status()

    assert status.llm_mode == config.LLM_MODE
    assert status.embedding_model == config.EMBEDDING_MODEL
    assert status.total_books == 2
    assert status.total_chunks == 10


def test_list_materials_maps_books_to_material_info(monkeypatch):
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.list_materials()

    assert [item.name for item in response.materials] == ["a.pdf", "b.pdf"]
    assert [item.sections_count for item in response.materials] == [2, 1]
    assert [item.quality_label for item in response.materials] == ["ready", "ready"]


def test_list_materials_keeps_plain_text_but_hides_empty_materials(monkeypatch):
    class MixedKB(FakeKB):
        def stats(self):
            return {
                "total_books": 4,
                "total_chunks": 10,
                "books": ["a.pdf", "story.txt", "weak.txt", "b.pdf"],
                "sections": ["Глава 1", "Глава 2"],
            }

        def get_file_profile(self, file_name):
            mapping = {
                "a.pdf": {"chunk_count": 6, "sections_count": 2, "sections": ["Глава 1", "Глава 2"]},
                "story.txt": {"chunk_count": 2, "sections_count": 0, "sections": []},
                "weak.txt": {"chunk_count": 0, "sections_count": 0, "sections": []},
                "b.pdf": {"chunk_count": 3, "sections_count": 1, "sections": ["Введение"]},
            }
            return mapping.get(file_name, {"chunk_count": 0, "sections_count": 0, "sections": []})

    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: MixedKB())

    response = app_services.list_materials()

    assert [item.name for item in response.materials] == ["a.pdf", "story.txt", "b.pdf"]
    assert [item.quality_label for item in response.materials] == ["ready", "plain_text", "ready"]


def test_list_sections_returns_all_sections(monkeypatch):
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.list_sections(file_filter="all")

    assert response.sections == ["Глава 1", "Глава 2"]


def test_list_sections_returns_sections_for_specific_file(monkeypatch):
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.list_sections(file_filter="a.pdf")

    assert response.sections == ["Глава 1", "Глава 2"]


def test_list_sections_normalizes_all_materials_label(monkeypatch):
    calls = []

    class TrackingKB(FakeKB):
        def get_available_sections(self, file_filter="all"):
            calls.append(file_filter)
            return ["Глава 1"]

    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: TrackingKB())

    response = app_services.list_sections(file_filter="Все материалы")

    assert response.sections == ["Глава 1"]
    assert calls == ["all"]


def test_upload_material_service_saves_file_and_indexes(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.upload_material_service("book.pdf", b"hello")

    assert response.ok is True
    assert response.material_name == "book.pdf"
    assert (docs_dir / "book.pdf").read_bytes() == b"hello"


def test_delete_material_service_removes_file_and_index(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    target = docs_dir / "book.pdf"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.delete_material_service("book.pdf")

    assert response.ok is True
    assert not target.exists()
    assert "Файл убран из библиотеки" in response.message


def test_reindex_material_service_rebuilds_single_file(monkeypatch, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    target = docs_dir / "book.pdf"
    target.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.reindex_material_service("book.pdf")

    assert response.ok is True
    assert response.material_name == "book.pdf"


def test_reindex_material_service_rebuilds_full_library(monkeypatch):
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: FakeKB())

    response = app_services.reindex_material_service()

    assert response.ok is True
    assert "База очищена" in response.message


def test_material_progress_defaults_to_idle():
    progress = app_services.get_material_progress()

    assert progress.active is False
    assert progress.operation == "idle"
    assert progress.progress >= 0


def test_upload_material_service_marks_progress_done(monkeypatch, tmp_path):
    class ProgressKB(FakeKB):
        def add_book(self, file_path, progress_callback=None):
            if progress_callback:
                progress_callback(phase="reading", progress=10, message="Читаю файл")
                progress_callback(phase="indexing", progress=80, message="Сохраняю фрагменты")
            return "✅ done"

    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(app_services.config, "DOCS_DIR", str(docs_dir))
    monkeypatch.setattr(app_services.runtime, "get_kb", lambda: ProgressKB())

    response = app_services.upload_material_service("book.pdf", b"hello")
    progress = app_services.get_material_progress()

    assert response.ok is True
    assert progress.active is False
    assert progress.progress == 100
    assert "готов" in progress.message.lower()


def test_start_reindex_material_service_queues_background_job(monkeypatch):
    calls = []

    monkeypatch.setattr(
        app_services,
        "reindex_material_service",
        lambda file_name=None: calls.append(file_name) or app_services.MaterialActionResponse(
            ok=True,
            message="done",
            material_name=file_name or "",
        ),
    )

    response = app_services.start_reindex_material_service("book.pdf")

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
        SummaryRequest(
            selected_file="a.pdf",
            selected_section="Глава 1",
            topic="Bluetooth",
            summary_type="Средний",
        )
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
        SummaryRequest(
            selected_file="Все материалы",
            selected_section="Все разделы",
            topic="Россия после Николая II до 2000 года",
            summary_type="Средний",
        )
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
        ChatRequest(message="Привет"),
    )

    assert response.answer == "Привет! Задайте вопрос по загруженным текстам."
    assert response.history[-1].role == "assistant"
    assert response.summary == "Привет! Задайте вопрос по загруженным текстам."
    assert response.confidence_label == "system"


def test_chat_service_returns_structured_answer(monkeypatch):
    class FakeKBForChat:
        def find_section_in_query(self, message):
            return None

        def search_with_sources(self, query, file_filter="all", section_filter=None):
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
        ChatRequest(
            message="Что такое Bluetooth?",
            selected_file="Все материалы",
            answer_mode="Обычный",
        )
    )

    assert response.answer == "Готовый ответ"
    assert response.history[-1].content == "Готовый ответ"
    assert response.sources[0].label == "book.pdf -> Глава 1"
    assert response.summary == "Готовый ответ"
    assert response.confidence_label == "medium"
    assert len(response.followup_suggestions) == 3
