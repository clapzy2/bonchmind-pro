"""UI-neutral service functions for BonchMind.

Every service function takes ``workspace_id`` as its first argument;
``api_app`` resolves it from ``current_user.personal_workspace.id`` via the
``get_current_workspace_id`` dependency. As of Stage 6e there is no implicit
workspace fallback anywhere in the backend — ``KnowledgeBase`` /
``summary_engine`` require ``workspace_id`` explicitly at every call site.

Two pieces stay shared on purpose:

* ``runtime.get_kb()`` returns one ``KnowledgeBase`` instance for the whole
  process — Chroma scopes data by ``workspace_id`` metadata, not by separate
  collections, so a single client is correct.
* ``_material_job_lock`` is a single global lock. It serialises background
  uploads/deletes across the instance, which is fine for the current
  single-node deployment. Per-workspace progress *state* is kept separate
  (``_material_progress_states`` keyed by ``workspace_id``) so a caller can
  never see another workspace's filename, progress percent or error.

Summary generation calls ``src.summary_engine`` strategies directly with
``workspace_id`` threaded all the way through to ``KnowledgeBase`` (Stage 4),
without going through the Gradio entrypoint (Stage 6d).
"""

import os
from threading import Lock, Thread

import config
from src import document_service, knowledge_base, runtime
from src import summary_engine
from src.api_models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatSource,
    MaterialActionResponse,
    MaterialInfo,
    MaterialProgressResponse,
    MaterialsResponse,
    SectionsResponse,
    SummaryExportRequest,
    SummaryRequest,
    SummaryResponse,
    SystemStatus,
)
from src.db import SessionLocal
from src.chat_utils import (
    get_last_qa,
    history_to_context,
    is_correction,
    is_followup,
    is_greeting,
    is_refusal,
)
from src.diagnostics import (
    DiagnosticLLM,
    finish_trace,
    format_last_trace,
    get_last_trace,
    start_trace,
)
from src.export_utils import export_text_to_docx


ALL_FILES_LABELS = {"Все файлы", "Все материалы", "all", ""}

# Single lock so two upload/delete/reindex jobs don't race against the
# vector index. State is per-workspace (see ``_material_progress_states``).
_progress_lock = Lock()
_material_job_lock = Lock()
_material_job_thread = None

_IDLE_PROGRESS_STATE = {
    "active": False,
    "operation": "idle",
    "phase": "",
    "message": "",
    "progress": 0,
    "current_file": "",
    "error": "",
}
_material_progress_states: dict[str, dict] = {}
# Cooperative-cancel flags, kept SEPARATE from the progress dict so they never
# leak into MaterialProgressResponse(**snapshot). Set by cancel_material_service,
# read by the indexing job's cancel_check, cleared when a job starts/finishes.
_material_cancel_flags: dict[str, bool] = {}


def _request_cancel(workspace_id: str) -> None:
    with _progress_lock:
        _material_cancel_flags[workspace_id] = True


def _is_cancel_requested(workspace_id: str) -> bool:
    with _progress_lock:
        return _material_cancel_flags.get(workspace_id, False)


def _clear_cancel(workspace_id: str) -> None:
    with _progress_lock:
        _material_cancel_flags.pop(workspace_id, None)


def _normalize_selected_file(selected_file):
    if selected_file is None:
        return "Все файлы"

    value = str(selected_file).strip()
    return "Все файлы" if value in ALL_FILES_LABELS else value


def _format_no_information_message(selected_file):
    """User-facing fallback when chat retrieval returned nothing.

    Moved out of the deleted ``main.py`` (Stage 6d) into the service layer
    so chat_service no longer references the Gradio entrypoint module.
    """
    if selected_file and selected_file != "Все файлы":
        return (
            "Информация по данному вопросу не найдена в выбранном материале.\n\n"
            "Попробуйте:\n"
            "• выбрать другой файл;\n"
            "• выбрать «Все файлы»;\n"
            "• переформулировать вопрос."
        )

    return (
        "Информация по данному вопросу не найдена в загруженных материалах.\n\n"
        "Попробуйте:\n"
        "• загрузить дополнительные материалы;\n"
        "• выбрать другой файл;\n"
        "• переформулировать вопрос."
    )


def _build_answer_summary(answer):
    text = " ".join(str(answer or "").split())
    if not text:
        return ""

    for separator in [". ", "! ", "? "]:
        if separator in text:
            first_part = text.split(separator, 1)[0].strip()
            if first_part:
                return first_part[:220]

    return text[:220]


def _build_confidence_label(sources, trace_status="ok"):
    if trace_status != "ok":
        return "low"

    source_count = len(sources or [])
    if source_count >= 3:
        return "high"
    if source_count >= 1:
        return "medium"
    return "low"


def _build_followup_suggestions(message, answer_mode, has_sources):
    if answer_mode == "Только цитаты":
        suggestions = [
            "Теперь объясни это простыми словами.",
            "Собери краткий вывод по этим цитатам.",
            "Покажи, какой раздел документа важнее всего.",
        ]
    elif answer_mode == "Кратко":
        suggestions = [
            "Теперь раскрой это подробнее.",
            "Сравни это с близким понятием.",
            "Покажи подтверждающие цитаты из текста.",
        ]
    elif answer_mode == "Подробно":
        suggestions = [
            "Сожми это в 3-4 ключевых пункта.",
            "Какая здесь главная мысль?",
            "Покажи, на какие разделы ты опирался.",
        ]
    else:
        suggestions = [
            "Объясни это еще проще.",
            "Сравни это с похожим понятием.",
            "Приведи подтверждающие цитаты из материала.",
        ]

    if not has_sources:
        suggestions[-1] = "Попробуй ответить по-другому или сузить вопрос."

    cleaned = []
    normalized_message = str(message or "").strip().lower()
    for item in suggestions:
        if item.strip().lower() != normalized_message and item not in cleaned:
            cleaned.append(item)
    return cleaned[:3]


def get_system_status(workspace_id: str):
    kb = runtime.get_kb()
    stats = kb.stats(workspace_id=workspace_id)

    mode = config.LLM_MODE
    model = config.API_MODEL if mode == "api" else config.OLLAMA_MODEL

    return SystemStatus(
        llm_mode=mode,
        model=model,
        embedding_model=config.EMBEDDING_MODEL,
        reranker_model=config.RERANKER_MODEL,
        chunk_size=config.CHUNK_SIZE,
        hyde_enabled=config.USE_HYDE,
        total_books=stats.get("total_books", 0),
        total_chunks=stats.get("total_chunks", 0),
    )


def _ready_material_quality(sections_count, chunk_count):
    """Quality badge for a Document whose status is already ``ready``.

    Stage 3d invariant: a ready Document is **never** hidden from the
    materials list — ``Document.status`` is the source of truth for
    visibility. The badge below is purely informational: it tells the user
    whether the material has good structure, is plain text, or is
    degraded (indexed but produced no chunks).
    """
    if sections_count >= 3:
        return "ready", "Материал хорошо подходит для поиска, конспектов и ссылок на источники."
    if sections_count > 0:
        return "ready", "Структура короткая, но материал уже пригоден для поиска и опоры на разделы."
    if chunk_count > 0:
        return "plain_text", "Сплошной текст без явных разделов: подходит для чтения и диалога, слабее для навигации."
    # Document is marked ready but the indexer produced no chunks. Still
    # surfaced so the user can re-run /reindex from the UI; never hidden.
    return "weak", "Материал проиндексирован, но содержательных фрагментов выделить не удалось. Попробуйте переиндексировать."


def list_materials(workspace_id: str):
    """Stage 3c: enumerate materials from the ``Document`` table.

    Visibility is owned entirely by ``Document.status``. The KB profile is
    used only to set the informational quality label/sections_count — it
    never decides whether a row is shown. This protects against KB lookup
    misses (e.g. a stale ``source_file`` mismatch) silently hiding an
    indexed document from the user.
    """
    kb = runtime.get_kb()
    db = SessionLocal()
    try:
        documents = document_service.list_documents(db, workspace_id)
    finally:
        db.close()

    materials = []
    for doc in documents:
        if doc.status == document_service.STATUS_ERROR:
            materials.append(
                MaterialInfo(
                    id=doc.id,
                    name=doc.original_name,
                    sections_count=0,
                    quality_label="error",
                    quality_reason=doc.error_message
                    or "Материал не удалось проиндексировать. Попробуйте загрузить снова.",
                    status=doc.status,
                )
            )
            continue

        if doc.status == document_service.STATUS_PROCESSING:
            materials.append(
                MaterialInfo(
                    id=doc.id,
                    name=doc.original_name,
                    sections_count=0,
                    quality_label="processing",
                    quality_reason="Идёт индексация материала. Обновите список через минуту.",
                    status=doc.status,
                )
            )
            continue

        # Status is READY: surface the document, then ask the KB for a
        # quality badge. KB lookup failures degrade the badge, not the row.
        try:
            profile = kb.get_file_profile(doc.original_name, workspace_id=workspace_id)
        except Exception:
            profile = {}
        sections_count = int((profile or {}).get("sections_count", 0) or 0)
        chunk_count = int((profile or {}).get("chunk_count", 0) or 0)
        quality_label, quality_reason = _ready_material_quality(sections_count, chunk_count)

        materials.append(
            MaterialInfo(
                id=doc.id,
                name=doc.original_name,
                sections_count=sections_count,
                quality_label=quality_label,
                quality_reason=quality_reason,
                status=doc.status,
            )
        )

    return MaterialsResponse(materials=materials)


def list_sections(workspace_id: str, file_filter: str = "all"):
    kb = runtime.get_kb()
    normalized_filter = _normalize_selected_file(file_filter)

    if normalized_filter == "Все файлы":
        sections = kb.get_available_sections(workspace_id=workspace_id)
    else:
        sections = kb.get_sections_for_file(normalized_filter, workspace_id=workspace_id)

    return SectionsResponse(sections=sections)


# ---------------------------------------------------------------------------
# Material upload / delete / reindex — per-workspace progress
# ---------------------------------------------------------------------------


def _get_workspace_progress_snapshot(workspace_id: str) -> dict:
    """Return a copy of ``workspace_id``'s progress state (idle if missing)."""
    with _progress_lock:
        return dict(_material_progress_states.get(workspace_id, _IDLE_PROGRESS_STATE))


def _set_material_progress(workspace_id: str, **updates) -> None:
    with _progress_lock:
        state = _material_progress_states.setdefault(
            workspace_id, dict(_IDLE_PROGRESS_STATE)
        )
        state.update(updates)


def _start_material_progress(workspace_id, operation, message="", current_file=""):
    _set_material_progress(
        workspace_id,
        active=True,
        operation=operation,
        phase="starting",
        message=message,
        progress=1,
        current_file=current_file,
        error="",
    )


def _queue_material_progress(workspace_id, operation, message="", current_file=""):
    _set_material_progress(
        workspace_id,
        active=True,
        operation=operation,
        phase="queued",
        message=message,
        progress=0,
        current_file=current_file,
        error="",
    )


def _update_material_progress(workspace_id, phase="", progress=None, message=None, current_file=None):
    payload = {}
    if phase is not None:
        payload["phase"] = phase
    if progress is not None:
        payload["progress"] = max(0, min(int(progress), 100))
    if message is not None:
        payload["message"] = message
    if current_file is not None:
        payload["current_file"] = current_file
    _set_material_progress(workspace_id, **payload)


def _finish_material_progress(workspace_id, message="", current_file=""):
    _set_material_progress(
        workspace_id,
        active=False,
        operation="idle",
        phase="done",
        message=message,
        progress=100,
        current_file=current_file,
        error="",
    )


def _fail_material_progress(workspace_id, message="", current_file=""):
    _set_material_progress(
        workspace_id,
        active=False,
        operation="idle",
        phase="error",
        message=message,
        progress=100,
        current_file=current_file,
        error=message,
    )


def _cancel_material_progress(workspace_id, message="", current_file=""):
    _set_material_progress(
        workspace_id,
        active=False,
        operation="idle",
        phase="cancelled",
        message=message,
        progress=100,
        current_file=current_file,
        error="",
    )


def get_material_progress(workspace_id: str) -> MaterialProgressResponse:
    return MaterialProgressResponse(**_get_workspace_progress_snapshot(workspace_id))


def reset_material_progress_for_tests():
    with _progress_lock:
        _material_progress_states.clear()


def _launch_material_job(workspace_id, operation, message, target, material_name=""):
    global _material_job_thread

    with _material_job_lock:
        current = get_material_progress(workspace_id)
        if current.active:
            return MaterialActionResponse(
                ok=False,
                message="Сейчас уже выполняется другая операция с библиотекой. Дождитесь завершения.",
                material_name=material_name,
            )

        # Clear any stale cancel flag so a new job doesn't inherit a cancel
        # request left over from a previous operation.
        _clear_cancel(workspace_id)

        _queue_material_progress(
            workspace_id,
            operation=operation,
            message=message,
            current_file=material_name,
        )

        def runner():
            try:
                target()
            except Exception as error:
                _fail_material_progress(workspace_id, str(error), current_file=material_name)

        _material_job_thread = Thread(target=runner, daemon=True)
        _material_job_thread.start()

    return MaterialActionResponse(
        ok=True,
        message=message,
        material_name=material_name,
    )


def _normalize_material_name(file_name):
    return os.path.basename(str(file_name or "")).strip()


def upload_material_service(workspace_id: str, user_id: str, file_name, content):
    """Persist + index a freshly uploaded material via :mod:`document_service`.

    Validation (name present, extension allowed, size below
    ``MAX_UPLOAD_BYTES``) happens here so the user gets a synchronous error
    response without ever creating a Document row for clearly-rejected
    uploads.
    """
    normalized_name = _normalize_material_name(file_name)
    if not normalized_name:
        return MaterialActionResponse(ok=False, message="Не выбран файл для загрузки.")

    lower_name = normalized_name.lower()
    if not any(lower_name.endswith(ext) for ext in config.SUPPORTED_FORMATS):
        return MaterialActionResponse(
            ok=False,
            message=f"Формат не поддерживается. Разрешены: {', '.join(config.SUPPORTED_FORMATS)}",
            material_name=normalized_name,
        )

    max_bytes = getattr(config, "MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        return MaterialActionResponse(
            ok=False,
            message=f"Файл слишком большой. Максимальный размер: {limit_mb} МБ.",
            material_name=normalized_name,
        )

    _start_material_progress(
        workspace_id,
        operation="upload",
        message=f"Готовлю загрузку {normalized_name}",
        current_file=normalized_name,
    )

    db = SessionLocal()
    try:
        try:
            doc = document_service.create_document(
                db,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                original_name=normalized_name,
                content=content,
                cancel_check=lambda: _is_cancel_requested(workspace_id),
                # Forward add_book's phase/percent reports to the polled
                # workspace progress so the bar moves smoothly instead of
                # jumping 1% -> 100%.
                progress_callback=lambda **payload: _update_material_progress(
                    workspace_id, **payload
                ),
            )
        except knowledge_base.IndexingCancelled:
            # Cooperative cancel (Stage 9a): create_document already rolled back
            # the partial document. Surface it as a cancelled (not failed) op.
            _clear_cancel(workspace_id)
            _cancel_material_progress(
                workspace_id,
                message=f"Загрузка {normalized_name} отменена.",
                current_file=normalized_name,
            )
            return MaterialActionResponse(
                ok=False,
                message=f"Загрузка {normalized_name} отменена.",
                material_name=normalized_name,
            )
        except Exception as error:
            _fail_material_progress(workspace_id, str(error), current_file=normalized_name)
            raise
    finally:
        db.close()

    if doc.status == document_service.STATUS_ERROR:
        message = doc.error_message or f"{normalized_name}: индексация не удалась."
        _fail_material_progress(workspace_id, message, current_file=normalized_name)
        return MaterialActionResponse(
            ok=False,
            message=message,
            material_name=normalized_name,
        )

    _finish_material_progress(
        workspace_id,
        message=f"{normalized_name} готов к поиску и конспектам",
        current_file=normalized_name,
    )
    return MaterialActionResponse(
        ok=True,
        message=f"✅ {normalized_name}: материал загружен и проиндексирован.",
        material_name=normalized_name,
    )


def start_upload_material_service(workspace_id: str, user_id: str, file_name, content):
    normalized_name = _normalize_material_name(file_name)
    return _launch_material_job(
        workspace_id,
        operation="upload",
        message=f"Запустил загрузку и индексацию {normalized_name}",
        material_name=normalized_name,
        target=lambda: upload_material_service(workspace_id, user_id, file_name, content),
    )


def cancel_material_service(workspace_id: str) -> MaterialActionResponse:
    """Request cooperative cancellation of the workspace's in-flight job.

    The running indexing loop checks the flag between batches and aborts,
    rolling back any partial data. No active operation → nothing to cancel.
    """
    if not get_material_progress(workspace_id).active:
        return MaterialActionResponse(ok=False, message="Сейчас нечего отменять.")

    _request_cancel(workspace_id)
    return MaterialActionResponse(ok=True, message="Отмена запрошена. Останавливаю операцию…")


def delete_material_service(workspace_id: str, file_name):
    normalized_name = _normalize_material_name(file_name)
    if not normalized_name:
        return MaterialActionResponse(ok=False, message="Материал не указан.")

    _start_material_progress(
        workspace_id,
        operation="delete",
        message=f"Удаляю {normalized_name} из библиотеки",
        current_file=normalized_name,
    )

    db = SessionLocal()
    try:
        doc = document_service.find_document_by_name(db, workspace_id, normalized_name)
        if doc is None:
            _fail_material_progress(
                workspace_id,
                f"{normalized_name} не найден в библиотеке.",
                current_file=normalized_name,
            )
            return MaterialActionResponse(
                ok=False,
                message=f"{normalized_name} не найден в библиотеке.",
                material_name=normalized_name,
            )
        document_service.delete_document(db, workspace_id, doc.id)
    finally:
        db.close()

    _finish_material_progress(
        workspace_id,
        message=f"{normalized_name} удалён из библиотеки",
        current_file=normalized_name,
    )
    return MaterialActionResponse(
        ok=True,
        message=f"🗑️ {normalized_name}: удалено. Файл убран из библиотеки.",
        material_name=normalized_name,
    )


def start_delete_material_service(workspace_id: str, file_name):
    normalized_name = _normalize_material_name(file_name)
    return _launch_material_job(
        workspace_id,
        operation="delete",
        message=f"Запустил удаление {normalized_name}",
        material_name=normalized_name,
        target=lambda: delete_material_service(workspace_id, file_name),
    )


def reindex_material_service(workspace_id: str, file_name=None):
    normalized_name = _normalize_material_name(file_name)

    # Single-file reindex: route through document_service so the existing
    # Document row is reused (and Chroma rebuilt by document_id).
    if normalized_name:
        _start_material_progress(
            workspace_id,
            operation="reindex_material",
            message=f"Переиндексирую {normalized_name}",
            current_file=normalized_name,
        )

        db = SessionLocal()
        try:
            doc = document_service.find_document_by_name(db, workspace_id, normalized_name)
            if doc is None:
                _fail_material_progress(
                    workspace_id,
                    f"{normalized_name} не найден в библиотеке.",
                    current_file=normalized_name,
                )
                return MaterialActionResponse(
                    ok=False,
                    message=f"{normalized_name} не найден в библиотеке.",
                    material_name=normalized_name,
                )
            refreshed = document_service.reindex_document(db, workspace_id, doc.id)
        finally:
            db.close()

        if refreshed is None or refreshed.status == document_service.STATUS_ERROR:
            message = (
                (refreshed.error_message if refreshed else "")
                or f"{normalized_name}: переиндексация не удалась."
            )
            _fail_material_progress(workspace_id, message, current_file=normalized_name)
            return MaterialActionResponse(
                ok=False,
                message=message,
                material_name=normalized_name,
            )

        _finish_material_progress(
            workspace_id,
            message=f"{normalized_name} переиндексирован",
            current_file=normalized_name,
        )
        return MaterialActionResponse(
            ok=True,
            message=f"✅ {normalized_name}: переиндексировано.",
            material_name=normalized_name,
        )

    # Full-library reindex: walk every Document, rebuild its chunks. The KB
    # is wiped per-workspace once at the start so orphaned chunks (left over
    # by a previous bug) are also cleared.
    kb = runtime.get_kb()
    _start_material_progress(
        workspace_id,
        operation="reindex_library",
        message="Полностью пересобираю библиотеку",
    )
    kb.clear(workspace_id=workspace_id)
    _update_material_progress(
        workspace_id,
        phase="cleanup",
        progress=5,
        message="Очищаю текущий индекс",
    )

    db = SessionLocal()
    try:
        documents = document_service.list_documents(db, workspace_id)
        for doc in documents:
            document_service.reindex_document(db, workspace_id, doc.id)
    finally:
        db.close()

    _finish_material_progress(workspace_id, message="Библиотека полностью переиндексирована")
    return MaterialActionResponse(
        ok=True,
        message=f"📚 Переиндексировано документов: {len(documents)}",
    )


def start_reindex_material_service(workspace_id: str, file_name=None):
    normalized_name = _normalize_material_name(file_name)
    operation = "reindex_material" if normalized_name else "reindex_library"
    title = (
        f"Запустил переиндексацию {normalized_name}"
        if normalized_name
        else "Запустил полную пересборку библиотеки"
    )
    return _launch_material_job(
        workspace_id,
        operation=operation,
        message=title,
        material_name=normalized_name,
        target=lambda: reindex_material_service(workspace_id, file_name),
    )


def generate_summary_service(workspace_id: str, request: SummaryRequest):
    """Generate a summary scoped to ``workspace_id``.

    Routes the request to the matching ``summary_engine`` strategy and
    threads ``workspace_id`` through to every KB call. Replaces the
    pre-Stage-6d bridge that detoured through ``main.on_generate_summary``
    in the Gradio entrypoint.
    """
    selected_file = _normalize_selected_file(request.selected_file)
    selected_section = request.selected_section
    topic = (request.topic or "").strip()
    summary_type = request.summary_type

    start_trace(
        kind="summary",
        request={
            "workspace_id": workspace_id,
            "selected_file": selected_file,
            "selected_section": selected_section,
            "topic": topic,
            "summary_type": summary_type,
        },
    )

    try:
        kb = runtime.get_kb()
        llm = DiagnosticLLM(runtime.get_llm())

        file_filter = "all" if selected_file == "Все файлы" else selected_file
        section_filter = None
        if selected_section and selected_section != "Все разделы":
            section_filter = selected_section

        if section_filter:
            text = summary_engine.generate_selected_section_summary(
                kb=kb,
                llm=llm,
                selected_file=selected_file,
                section_filter=section_filter,
                topic=topic,
                summary_type=summary_type,
                workspace_id=workspace_id,
            )
        elif topic:
            summary_type_low = str(summary_type or "").lower()
            if (
                not summary_engine._looks_like_history_topic(topic)
                and ("крат" in summary_type_low or "сред" in summary_type_low)
            ):
                text = summary_engine.generate_direct_topic_summary(
                    kb=kb,
                    llm=llm,
                    topic=topic,
                    summary_type=summary_type,
                    file_filter=file_filter,
                    section_filter=None,
                    workspace_id=workspace_id,
                )
            elif getattr(config, "PLANNED_SUMMARY_ENABLED", True):
                text = summary_engine.generate_planned_topic_summary(
                    kb=kb,
                    llm=llm,
                    topic=topic,
                    summary_type=summary_type,
                    file_filter=file_filter,
                    section_filter=None,
                    workspace_id=workspace_id,
                )
            else:
                text = summary_engine.generate_topic_summary(
                    kb=kb,
                    llm=llm,
                    topic=topic,
                    summary_type=summary_type,
                    file_filter=file_filter,
                    section_filter=None,
                    workspace_id=workspace_id,
                )
        else:
            # No topic, no section — generic map-reduce over the selected file.
            text = summary_engine.generate_full_file_summary(
                kb=kb,
                llm=llm,
                selected_file=selected_file,
                selected_section=selected_section,
                summary_type=summary_type,
                file_filter=file_filter,
                workspace_id=workspace_id,
            )

        finish_trace(output=text)
    except Exception as error:
        text = f"Ошибка: {error}"
        finish_trace(output=text, error=error)

    return SummaryResponse(
        text=text,
        diagnostics=format_last_trace(),
        trace=get_last_trace(),
    )


def _group_chat_sources(sources, selected_file, limit=4):
    grouped = {}

    for src in sources or []:
        source_file = src.get("source_file", "")
        section = src.get("section", "")
        score = float(src.get("score", 0) or 0)
        key = (source_file, section)

        if key not in grouped:
            grouped[key] = {
                "source_file": source_file,
                "section": section,
                "score": score,
            }
        else:
            grouped[key]["score"] = max(grouped[key]["score"], score)

    sorted_sources = sorted(
        grouped.values(),
        key=lambda item: item["score"],
        reverse=True,
    )[:limit]

    result = []
    for item in sorted_sources:
        if selected_file != "Все файлы" and item["section"]:
            label = item["section"]
        elif item["section"]:
            label = f'{item["source_file"]} -> {item["section"]}'
        else:
            label = item["source_file"]

        result.append(
            ChatSource(
                source_file=item["source_file"],
                section=item["section"],
                score=round(item["score"], 3),
                label=label,
            )
        )

    return result


def chat_service(workspace_id: str, request: ChatRequest):
    message = str(request.message or "").strip()
    selected_file = _normalize_selected_file(request.selected_file)
    history = [ChatMessage(role=item.role, content=item.content) for item in (request.history or [])]

    start_trace(
        kind="chat",
        request={
            "message": message,
            "selected_file": selected_file,
            "answer_mode": request.answer_mode,
            "history_len": str(len(history)),
        },
    )

    if not message:
        finish_trace(output="")
        return ChatResponse(
            answer="",
            history=history,
            sources=[],
            diagnostics=format_last_trace(),
            trace=get_last_trace(),
        )

    if is_greeting(message):
        answer = "Привет! Задайте вопрос по загруженным текстам."
        updated_history = history + [
            ChatMessage(role="user", content=message),
            ChatMessage(role="assistant", content=answer),
        ]
        finish_trace(output=answer)
        return ChatResponse(
            answer=answer,
            summary=answer,
            confidence_label="system",
            followup_suggestions=[
                "Объясни тему простыми словами.",
                "Сделай краткий ответ по разделу.",
                "Приведи только цитаты по теме.",
            ],
            history=updated_history,
            sources=[],
            diagnostics=format_last_trace(),
            trace=get_last_trace(),
        )

    kb = runtime.get_kb()
    llm = DiagnosticLLM(runtime.get_llm())
    file_filter = "all" if selected_file == "Все файлы" else selected_file

    is_corr = is_correction(message)
    is_fu = is_followup(message)
    search_query = message
    prev_question, prev_answer = "", ""

    if is_corr or is_fu:
        prev_question, prev_answer = get_last_qa([item.model_dump() for item in history])
        if prev_question:
            search_query = prev_question

    section_filter = kb.find_section_in_query(message, workspace_id=workspace_id)
    context, raw_sources = kb.search_with_sources(
        search_query,
        file_filter=file_filter,
        section_filter=section_filter,
        workspace_id=workspace_id,
    )

    grouped_sources = _group_chat_sources(raw_sources, selected_file=selected_file)

    if not context:
        answer = "НЕТ ИНФОРМАЦИИ - база пуста или файлы не проиндексированы."
        updated_history = history + [
            ChatMessage(role="user", content=message),
            ChatMessage(role="assistant", content=answer),
        ]
        finish_trace(output=answer)
        return ChatResponse(
            answer=answer,
            summary="Ответ не найден в текущей базе знаний.",
            confidence_label="low",
            followup_suggestions=[
                "Выбери другой материал.",
                "Сузь вопрос до конкретного раздела.",
                "Переформулируй тему короче.",
            ],
            history=updated_history,
            sources=grouped_sources,
            diagnostics=format_last_trace(),
            trace=get_last_trace(),
        )

    prompt_key = {
        "Обычный": "qa",
        "Кратко": "short_answer",
        "Подробно": "detailed_answer",
        "Только цитаты": "quotes_only",
    }.get(request.answer_mode, "qa")

    if is_corr and prev_question and prev_answer:
        full_prompt = config.PROMPTS["correction"].format(
            system=config.SYSTEM_PROMPT,
            context=context,
            prev_question=prev_question,
            prev_answer=prev_answer,
            correction=message,
        )
    else:
        history_ctx = history_to_context([item.model_dump() for item in history], n_last=3)
        if history_ctx:
            full_prompt = config.PROMPTS[prompt_key].format(
                system=config.SYSTEM_PROMPT,
                topic=message,
                context=f"ПРЕДЫДУЩИЙ ДИАЛОГ:\n{history_ctx}\n\nТЕКСТ ДОКУМЕНТА:\n{context}",
            )
        else:
            full_prompt = config.PROMPTS[prompt_key].format(
                system=config.SYSTEM_PROMPT,
                topic=message,
                context=context,
            )

    answer = llm.call(full_prompt)

    if is_refusal(answer):
        answer = _format_no_information_message(selected_file)

    updated_history = history + [
        ChatMessage(role="user", content=message),
        ChatMessage(role="assistant", content=answer),
    ]

    finish_trace(output=answer)
    trace = get_last_trace()
    return ChatResponse(
        answer=answer,
        summary=_build_answer_summary(answer),
        confidence_label=_build_confidence_label(grouped_sources, trace_status=(trace or {}).get("status", "ok")),
        followup_suggestions=_build_followup_suggestions(
            message=message,
            answer_mode=request.answer_mode,
            has_sources=bool(grouped_sources),
        ),
        history=updated_history,
        sources=grouped_sources,
        diagnostics=format_last_trace(),
        trace=trace,
    )


def export_summary_docx_service(request: SummaryExportRequest):
    text = str(request.text or "").strip()
    if not text:
        return None

    return export_text_to_docx(
        title="BonchMind Pro — конспект",
        content=text,
        prefix="bonchmind_summary",
        name_parts=[
            _normalize_selected_file(request.selected_file),
            request.selected_section,
            request.summary_type,
        ],
    )


def get_latest_diagnostics_text():
    return format_last_trace()


def get_latest_diagnostics_json():
    return get_last_trace()
