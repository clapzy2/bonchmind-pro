"""UI-neutral service functions for BonchMind."""

import os
from threading import Lock, Thread

import config
import main
from src import runtime
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
_progress_lock = Lock()
_material_job_lock = Lock()
_material_job_thread = None
_material_progress_state = {
    "active": False,
    "operation": "idle",
    "phase": "",
    "message": "",
    "progress": 0,
    "current_file": "",
    "error": "",
}


def _normalize_selected_file(selected_file):
    if selected_file is None:
        return "Все файлы"

    value = str(selected_file).strip()
    return "Все файлы" if value in ALL_FILES_LABELS else value


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


def get_system_status():
    kb = runtime.get_kb()
    stats = kb.stats()

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


def _material_quality(sections_count, chunk_count):
    if chunk_count <= 0:
        return "hidden", "Внутри файла пока нет пригодного содержимого для поиска и генерации."
    if sections_count >= 3:
        return "ready", "Материал хорошо подходит для поиска, конспектов и ссылок на источники."
    if sections_count > 0:
        return "ready", "Структура короткая, но материал уже пригоден для поиска и опоры на разделы."
    return "plain_text", "Сплошной текст без явных разделов: хорош для чтения и диалога, слабее для навигации."


def list_materials():
    kb = runtime.get_kb()
    stats = kb.stats()

    materials = []
    for book in stats.get("books", []):
        profile = kb.get_file_profile(book)
        sections_count = int(profile.get("sections_count", 0) or 0)
        chunk_count = int(profile.get("chunk_count", 0) or 0)
        quality_label, quality_reason = _material_quality(sections_count, chunk_count)
        if quality_label == "hidden":
            continue

        materials.append(
            MaterialInfo(
                name=book,
                sections_count=sections_count,
                quality_label=quality_label,
                quality_reason=quality_reason,
            )
        )

    return MaterialsResponse(materials=materials)


def list_sections(file_filter="all"):
    kb = runtime.get_kb()
    normalized_filter = _normalize_selected_file(file_filter)

    if normalized_filter == "Все файлы":
        try:
            sections = kb.get_available_sections(file_filter="all")
        except TypeError:
            sections = kb.get_available_sections()
    else:
        sections = kb.get_sections_for_file(normalized_filter)

    return SectionsResponse(sections=sections)


def _set_material_progress(**updates):
    with _progress_lock:
        _material_progress_state.update(updates)


def _start_material_progress(operation, message="", current_file=""):
    _set_material_progress(
        active=True,
        operation=operation,
        phase="starting",
        message=message,
        progress=1,
        current_file=current_file,
        error="",
    )


def _queue_material_progress(operation, message="", current_file=""):
    _set_material_progress(
        active=True,
        operation=operation,
        phase="queued",
        message=message,
        progress=0,
        current_file=current_file,
        error="",
    )


def _update_material_progress(phase="", progress=None, message=None, current_file=None):
    payload = {}
    if phase is not None:
        payload["phase"] = phase
    if progress is not None:
        payload["progress"] = max(0, min(int(progress), 100))
    if message is not None:
        payload["message"] = message
    if current_file is not None:
        payload["current_file"] = current_file
    _set_material_progress(**payload)


def _finish_material_progress(message="", current_file=""):
    _set_material_progress(
        active=False,
        operation="idle",
        phase="done",
        message=message,
        progress=100,
        current_file=current_file,
        error="",
    )


def _fail_material_progress(message="", current_file=""):
    _set_material_progress(
        active=False,
        operation="idle",
        phase="error",
        message=message,
        progress=100,
        current_file=current_file,
        error=message,
    )


def get_material_progress():
    with _progress_lock:
        return MaterialProgressResponse(**_material_progress_state)


def reset_material_progress_for_tests():
    _set_material_progress(
        active=False,
        operation="idle",
        phase="",
        message="",
        progress=0,
        current_file="",
        error="",
    )


def _kb_add_book(kb, file_path):
    try:
        return kb.add_book(file_path, progress_callback=_update_material_progress)
    except TypeError:
        return kb.add_book(file_path)


def _kb_index_all_books(kb):
    try:
        return kb.index_all_books(progress_callback=_update_material_progress)
    except TypeError:
        return kb.index_all_books()


def _launch_material_job(operation, message, target, material_name=""):
    global _material_job_thread

    with _material_job_lock:
        current = get_material_progress()
        if current.active:
            return MaterialActionResponse(
                ok=False,
                message="Сейчас уже выполняется другая операция с библиотекой. Дождитесь завершения.",
                material_name=material_name,
            )

        _queue_material_progress(
            operation=operation,
            message=message,
            current_file=material_name,
        )

        def runner():
            try:
                target()
            except Exception as error:
                _fail_material_progress(str(error), current_file=material_name)

        _material_job_thread = Thread(target=runner, daemon=True)
        _material_job_thread.start()

    return MaterialActionResponse(
        ok=True,
        message=message,
        material_name=material_name,
    )


def _normalize_material_name(file_name):
    return os.path.basename(str(file_name or "")).strip()


def _material_path(file_name):
    normalized_name = _normalize_material_name(file_name)
    return os.path.join(config.DOCS_DIR, normalized_name)


def upload_material_service(file_name, content):
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

    os.makedirs(config.DOCS_DIR, exist_ok=True)

    kb = runtime.get_kb()
    destination = _material_path(normalized_name)
    existed_before = os.path.exists(destination)
    _start_material_progress(
        operation="upload",
        message=f"Готовлю загрузку {normalized_name}",
        current_file=normalized_name,
    )

    try:
        with open(destination, "wb") as output_file:
            output_file.write(content)
        _update_material_progress(
            phase="saving",
            progress=10,
            message=f"Файл {normalized_name} сохранен в библиотеку",
            current_file=normalized_name,
        )

        if existed_before:
            kb.remove_book(normalized_name)
            _update_material_progress(
                phase="cleanup",
                progress=18,
                message="Убираю старую версию материала из индекса",
                current_file=normalized_name,
            )

        result = _kb_add_book(kb, destination)
        ok = str(result).startswith("✅") or str(result).startswith("⏭️")
        if not ok and os.path.exists(destination):
            try:
                os.remove(destination)
            except OSError:
                pass

        if ok:
            _finish_material_progress(
                message=f"{normalized_name} готов к поиску и конспектам",
                current_file=normalized_name,
            )
        else:
            _fail_material_progress(result, current_file=normalized_name)

        return MaterialActionResponse(
            ok=ok,
            message=result,
            material_name=normalized_name,
        )
    except Exception as error:
        _fail_material_progress(str(error), current_file=normalized_name)
        raise


def start_upload_material_service(file_name, content):
    normalized_name = _normalize_material_name(file_name)
    return _launch_material_job(
        operation="upload",
        message=f"Запустил загрузку и индексацию {normalized_name}",
        material_name=normalized_name,
        target=lambda: upload_material_service(file_name, content),
    )


def delete_material_service(file_name):
    normalized_name = _normalize_material_name(file_name)
    if not normalized_name:
        return MaterialActionResponse(ok=False, message="Материал не указан.")

    kb = runtime.get_kb()
    file_path = _material_path(normalized_name)
    existed_on_disk = os.path.exists(file_path)
    _start_material_progress(
        operation="delete",
        message=f"Удаляю {normalized_name} из библиотеки",
        current_file=normalized_name,
    )
    remove_message = kb.remove_book(normalized_name)
    _update_material_progress(
        phase="cleanup",
        progress=60,
        message="Удаляю фрагменты из индекса",
        current_file=normalized_name,
    )

    if existed_on_disk:
        os.remove(file_path)

    ok = existed_on_disk or "удалено" in remove_message.lower()
    if not ok:
        _fail_material_progress(f"{normalized_name} не найден в библиотеке.", current_file=normalized_name)
        return MaterialActionResponse(
            ok=False,
            message=f"{normalized_name} не найден в библиотеке.",
            material_name=normalized_name,
        )

    _finish_material_progress(
        message=f"{normalized_name} удален из библиотеки",
        current_file=normalized_name,
    )
    return MaterialActionResponse(
        ok=True,
        message=f"{remove_message}. Файл убран из библиотеки.",
        material_name=normalized_name,
    )


def start_delete_material_service(file_name):
    normalized_name = _normalize_material_name(file_name)
    return _launch_material_job(
        operation="delete",
        message=f"Запустил удаление {normalized_name}",
        material_name=normalized_name,
        target=lambda: delete_material_service(file_name),
    )


def reindex_material_service(file_name=None):
    kb = runtime.get_kb()

    normalized_name = _normalize_material_name(file_name)
    if normalized_name:
        file_path = _material_path(normalized_name)
        if not os.path.exists(file_path):
            return MaterialActionResponse(
                ok=False,
                message=f"{normalized_name} не найден в папке docs.",
                material_name=normalized_name,
            )

        _start_material_progress(
            operation="reindex_material",
            message=f"Переиндексирую {normalized_name}",
            current_file=normalized_name,
        )
        kb.remove_book(normalized_name)
        _update_material_progress(
            phase="cleanup",
            progress=15,
            message="Снимаю старые фрагменты материала",
            current_file=normalized_name,
        )
        result = _kb_add_book(kb, file_path)
        ok = str(result).startswith("✅") or str(result).startswith("⏭️")
        if ok:
            _finish_material_progress(
                message=f"{normalized_name} переиндексирован",
                current_file=normalized_name,
            )
        else:
            _fail_material_progress(result, current_file=normalized_name)
        return MaterialActionResponse(
            ok=ok,
            message=result,
            material_name=normalized_name,
        )

    _start_material_progress(
        operation="reindex_library",
        message="Полностью пересобираю библиотеку",
    )
    result = kb.clear()
    _update_material_progress(
        phase="cleanup",
        progress=5,
        message="Очищаю текущий индекс",
    )
    index_result = _kb_index_all_books(kb)
    _finish_material_progress(message="Библиотека полностью переиндексирована")
    return MaterialActionResponse(
        ok=True,
        message=f"{result}\n{index_result}",
    )


def start_reindex_material_service(file_name=None):
    normalized_name = _normalize_material_name(file_name)
    operation = "reindex_material" if normalized_name else "reindex_library"
    title = (
        f"Запустил переиндексацию {normalized_name}"
        if normalized_name
        else "Запустил полную пересборку библиотеки"
    )
    return _launch_material_job(
        operation=operation,
        message=title,
        material_name=normalized_name,
        target=lambda: reindex_material_service(file_name),
    )


def generate_summary_service(request: SummaryRequest):
    # The legacy Gradio handler keeps its own module-level singletons. The API
    # layer owns runtime initialization, so we bridge them to avoid loading the
    # embedding model a second time on the first summary request.
    main._llm = runtime.get_llm()
    main._kb = runtime.get_kb()

    text = main.on_generate_summary(
        _normalize_selected_file(request.selected_file),
        request.selected_section,
        request.topic,
        request.summary_type,
    )

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


def chat_service(request: ChatRequest):
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

    section_filter = kb.find_section_in_query(message)
    context, raw_sources = kb.search_with_sources(
        search_query,
        file_filter=file_filter,
        section_filter=section_filter,
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
        answer = main.format_no_information_message(selected_file)

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
