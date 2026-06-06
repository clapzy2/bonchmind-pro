"""
main.py - запускает веб-интерфейс.
Пользователь может загружать файлы и задавать вопросы по текстам.
"""
import warnings
warnings.filterwarnings("ignore")

import os
import sys
import gc
import re
from src.export_utils import export_last_answer_to_docx, export_text_to_docx

from src.chat_utils import (
    is_greeting,
    is_refusal,
    is_correction,
    is_followup,
    history_to_context,
    get_last_qa,
)

# Подавляем предупреждения от torch, HuggingFace и других библиотек
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TORCH_DISTRIBUTED_DEBUG"] = "OFF"
os.environ["GLOG_minloglevel"] = "3"

import logging
logging.getLogger("torch").setLevel(logging.CRITICAL)
logging.getLogger("torch.distributed").setLevel(logging.CRITICAL)
logging.getLogger("transformers").setLevel(logging.CRITICAL)
logging.getLogger("sentence_transformers").setLevel(logging.CRITICAL)
logging.getLogger("huggingface_hub").setLevel(logging.CRITICAL)

# Отключаем прокси для API
os.environ["NO_PROXY"] = "localhost,127.0.0.1,api.groq.com,openrouter.ai"
os.environ["no_proxy"] = "localhost,127.0.0.1,api.groq.com,openrouter.ai"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
import config
from src.llm_engine import LLMEngine
from src.knowledge_base import KnowledgeBase

# Глобальные объекты (создаются один раз при первом обращении)
_llm = None
_kb  = None



def _get_llm():
    """Получить или создать LLM-движок."""
    global _llm
    if _llm is None:
        _llm = LLMEngine()
    return _llm


def _get_kb(log=None):
    """Получить или создать базу знаний."""
    global _kb
    if _kb is None:
        _kb = KnowledgeBase(progress_callback=log, llm_engine=_get_llm())
    elif _kb._llm is None:
        _kb.set_llm(_get_llm())
    return _kb


def _gradio_chatbot_kwargs():
    """Параметры чат-бота в зависимости от версии Gradio."""
    major = gr.__version__.split(".")[0]
    return {"type": "messages"} if major == "5" else {}


# Обработчики вкладки "Файлы"
def on_index_books():
    """Проиндексиировать все файлы из папки docs/."""
    import re as _re
    log_lines = []
    def log(msg):
        log_lines.append(_re.sub(r'\[.*?\]', '', str(msg)))
        return log_lines[-1]
    try:
        kb = _get_kb(log)
        result = kb.index_all_books()
        stats = kb.stats()
        # gc.collect()
        out = f"{result}\n\n📊 Итого:\n  Файлов: {stats['total_books']}\n  Фрагментов: {stats['total_chunks']}"
        if stats["books"]:
            out += "\n  Файлы: " + ", ".join(stats["books"])
        if stats.get("sections"):
            out += f"\n  Разделов: {len(stats['sections'])}"
        return out
    except Exception as e:
        return f"Ошибка: {e}"


def on_add_book(files):
    """Загрузить файлы через интерфейс и проиндексировать."""
    if not files:
        return "Выберите файлы для загрузки"
    import shutil
    try:
        kb = _get_kb()
        os.makedirs(config.DOCS_DIR, exist_ok=True)
        results = []
        for file in files:
            src = file.name if hasattr(file, "name") else str(file)
            dest = os.path.join(config.DOCS_DIR, os.path.basename(src))
            shutil.copy2(src, dest)
            results.append(kb.add_book(dest))
        # gc.collect()
        stats = kb.stats()
        return "\n".join(results) + f"\n\n📊 Всего: {stats['total_books']} файлов, {stats['total_chunks']} фрагментов"
    except Exception as e:
        return f"{e}"


def on_clear_kb():
    """Очистить базу знаний."""
    try:
        result = _get_kb().clear()
        gc.collect()
        return result
    except Exception as e:
        return f"{e}"


def on_stats():
    """Показать статистику базы."""
    try:
        stats = _get_kb().stats()
        text = f"📚 Файлов: {stats['total_books']}\n📄 Фрагментов: {stats['total_chunks']}\n"
        if stats["books"]:
            text += "\n📖 Файлы:\n" + "".join(f"  • {b}\n" for b in stats["books"])
        if stats.get("sections"):
            text += f"\n📑 Разделов: {len(stats['sections'])}"
        else:
            text += "\n⚠️ База пуста. Загрузите файлы."
        return text
    except Exception as e:
        return f"{e}"


def get_file_choices():
    """Список файлов для выпадающего списка."""
    try:
        return ["Все файлы"] + _get_kb().get_available_files()
    except Exception:
        return ["Все файлы"]


def on_file_change_for_summary(selected_file):
    """Обновить список разделов после выбора файла."""
    try:
        if selected_file == "Все файлы":
            return gr.Dropdown(
                choices=["Все разделы"],
                value="Все разделы"
            )

        sections = _get_kb().get_sections_for_file(selected_file)

        return gr.Dropdown(
            choices=["Все разделы"] + sections,
            value="Все разделы"
        )

    except Exception:
        return gr.Dropdown(
            choices=["Все разделы"],
            value="Все разделы"
        )

def clear_summary_output():
    """Очистить результат конспекта при изменении параметров."""
    return "", None

def on_refresh_sections():
    """Обновить список разделов для вкладки конспекта."""
    try:
        sections = _get_kb().get_available_sections()
        return gr.Dropdown(choices=["Все разделы"] + sections, value="Все разделы")
    except Exception:
        return gr.Dropdown(choices=["Все разделы"], value="Все разделы")

def on_refresh_files():
    return gr.Dropdown(choices=get_file_choices(), value="Все файлы")


def format_sources_for_answer(
    sources,
    selected_file="Все файлы",
    title="**Основные источники:**",
    limit=3,
):
    """
    Оформляет источники так, чтобы не показывать лишнее.

    Если выбран конкретный файл:
    - файл не дублируется;
    - показывается только раздел, если он есть.

    Если выбраны все файлы:
    - показывается файл и раздел.
    """
    if not sources:
        return ""

    grouped = {}

    for src in sources:
        source_file = src.get("source_file", "?")
        section = src.get("section", "")
        score = float(src.get("score", 0))

        key = (source_file, section)

        if key not in grouped:
            grouped[key] = {
                "source_file": source_file,
                "section": section,
                "best_score": score,
            }
        else:
            grouped[key]["best_score"] = max(grouped[key]["best_score"], score)

    sorted_sources = sorted(
        grouped.values(),
        key=lambda item: item["best_score"],
        reverse=True,
    )[:limit]

    lines = [f"\n\n{title}"]

    for i, src in enumerate(sorted_sources, start=1):
        source_file = src["source_file"]
        section = src["section"]
        score = round(src["best_score"], 3)

        if selected_file != "Все файлы":
            if not section:
                continue

            lines.append(
                f"{i}. Раздел: {section}\n"
                f"   Релевантность: {score}"
            )
        else:
            if section:
                lines.append(
                    f"{i}. {source_file} → {section}\n"
                    f"   Релевантность: {score}"
                )
            else:
                lines.append(
                    f"{i}. {source_file}\n"
                    f"   Релевантность: {score}"
                )

    if len(lines) == 1:
        return ""

    return "\n".join(lines)

def format_no_information_message(selected_file):
    """Красивое сообщение, если информации нет."""
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

# Обработчик чата

def chat_respond(message, history, selected_file, answer_mode):
    """
    Основной обработчик: получает вопрос, ищет фрагменты,
    генерирует ответ в режиме стриминга.
    """
    if not message.strip():
        yield history
        return

    # Приветствие, шаблон
    if is_greeting(message):
        yield history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": "Привет! Задайте вопрос по загруженным текстам."}
        ]
        return

    try:
        kb = _get_kb()
        llm = _get_llm()
        file_filter = "all" if selected_file == "Все файлы" else selected_file

        # Определяем тип сообщения: исправление или уточнение
        is_corr = is_correction(message)
        is_fu = is_followup(message)
        search_query = message
        prev_question, prev_answer = "", ""

        if is_corr or is_fu:
            prev_question, prev_answer = get_last_qa(history)
            if prev_question:
                search_query = prev_question

        # Определяем раздел для фильтрации
        section_filter = kb.find_section_in_query(message)

        # Ищем релевантные фрагменты (RAG-пайплайн)
        context, sources = kb.search_with_sources(
            search_query,
            file_filter=file_filter,
            section_filter=section_filter
        )
        if not context:
            yield history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": "НЕТ ИНФОРМАЦИИ - база пуста или файлы не проиндексированы."}
            ]
            return

        prompt_key = {
            "Обычный": "qa",
            "Кратко": "short_answer",
            "Подробно": "detailed_answer",
            "Только цитаты": "quotes_only",
        }.get(answer_mode, "qa")

        # Выбираем промпт: обычный вопрос или исправление
        if is_corr and prev_question and prev_answer:
            full_prompt = config.PROMPTS["correction"].format(
                system=config.SYSTEM_PROMPT, context=context,
                prev_question=prev_question, prev_answer=prev_answer, correction=message,
            )
        else:
            history_ctx = history_to_context(history, n_last=3)
            if history_ctx:
                full_prompt = config.PROMPTS[prompt_key].format(
                    system=config.SYSTEM_PROMPT, topic=message,
                    context=f"ПРЕДЫДУЩИЙ ДИАЛОГ:\n{history_ctx}\n\nТЕКСТ ДОКУМЕНТА:\n{context}"
                )
            else:
                full_prompt = config.PROMPTS[prompt_key].format(
                    system=config.SYSTEM_PROMPT, topic=message, context=context
                )

        # Генерируем ответ потоково (токен за токеном)
        answer = ""
        new_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": ""}
        ]
        for token in llm.stream(full_prompt):
            answer += token
            new_history[-1]["content"] = answer
            yield new_history

        # Если LLM отказалась отвечать
        if is_refusal(answer):
            refusal_text = format_no_information_message(selected_file)

            nearby_sources = format_sources_for_answer(
                sources,
                selected_file=selected_file,
                title="**Близкие найденные источники:**",
            )

            if nearby_sources:
                refusal_text += nearby_sources

            new_history[-1]["content"] = refusal_text
            yield new_history
            return

        source_block = format_sources_for_answer(
            sources,
            selected_file=selected_file,
        )

        if source_block:
            new_history[-1]["content"] = answer + source_block
        else:
            new_history[-1]["content"] = answer

        yield new_history

    except Exception as e:
        yield history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": f"Ошибка: {e}"}
        ]


def on_export_docx(history):
    """Экспортировать последний ответ в DOCX."""
    path = export_last_answer_to_docx(history)

    if not path:
        return None

    return path

def on_export_summary_docx(summary_text, selected_file, selected_section, summary_type):
    """Экспортировать конспект в DOCX."""
    if not summary_text or not str(summary_text).strip():
        return None

    return export_text_to_docx(
        title="BonchMind Pro — конспект",
        content=summary_text,
        prefix="bonchmind_summary",
        name_parts=[selected_file, selected_section, summary_type],
    )

def _summary_generation_params(summary_type):
    """Параметры поиска и генерации для разных размеров конспекта."""
    summary_type = (summary_type or "").lower()
    base_top_k = getattr(config, "SUMMARY_TOP_K", 40)

    if "крат" in summary_type:
        return {
            "top_k": max(18, min(30, base_top_k)),
            "group_size": 6,
            "chunk_tokens": 700,
            "final_tokens": 1800,
        }

    if "подроб" in summary_type:
        return {
            "top_k": max(80, base_top_k * 2),
            "group_size": 6,
            "chunk_tokens": 1200,
            "final_tokens": 3600,
        }

    return {
        "top_k": base_top_k,
        "group_size": 5,
        "chunk_tokens": 900,
        "final_tokens": 2200,
    }

def generate_selected_section_summary(
    kb,
    llm,
    selected_file,
    section_filter,
    topic,
    summary_type,
):
    """
    Быстрый конспект по выбранному разделу.

    Если пользователь явно выбрал раздел, не делаем semantic search.
    Берём только чанки этого раздела и конспектируем их напрямую.
    """
    params = _summary_generation_params(summary_type)

    file_filter = "all" if selected_file == "Все файлы" else selected_file

    chunks = kb.get_file_chunks(
        file_filter=file_filter,
        section_filter=section_filter,
    )

    if not chunks:
        return (
            "Информация по выбранному разделу не найдена.\n\n"
            "Попробуйте:\n"
            "• выбрать другой раздел;\n"
            "• выбрать «Все разделы»;\n"
            "• переиндексировать материал."
        )

    group_size = params["group_size"]
    partial_summaries = []

    for i in range(0, len(chunks), group_size):
        group = chunks[i:i + group_size]

        context_parts = []

        for chunk in group:
            section = chunk.get("section", "")
            label = (
                f'{chunk["source_file"]} | {section}'
                if section
                else chunk["source_file"]
            )
            context_parts.append(f"[{label}]\n{chunk['text']}")

        context = "\n\n---\n\n".join(context_parts)

        if topic:
            prompt = config.PROMPTS["topic_summary_chunk"].format(
                system=config.SYSTEM_PROMPT,
                topic=topic,
                context=context,
            )
        else:
            prompt = config.PROMPTS["summary_chunk"].format(
                system=config.SYSTEM_PROMPT,
                context=context,
            )

        partial = llm.call(prompt, max_tokens=params["chunk_tokens"]).strip()

        if partial and not partial.upper().startswith("НЕ ОТНОСИТСЯ"):
            partial_summaries.append(partial)

    if not partial_summaries:
        return (
            "Информация по указанной теме не найдена в выбранном разделе.\n\n"
            "Попробуйте:\n"
            "• убрать тему и сделать конспект всего раздела;\n"
            "• выбрать другой раздел;\n"
            "• выбрать «Все разделы»."
        )

    combined_context = "\n\n---\n\n".join(partial_summaries)

    if topic:
        final_prompt = config.PROMPTS["topic_summary_reduce"].format(
            system=config.SYSTEM_PROMPT,
            topic=topic,
            context=combined_context,
            summary_type=summary_type.lower(),
        )
    else:
        final_prompt = config.PROMPTS["summary_reduce"].format(
            system=config.SYSTEM_PROMPT,
            context=combined_context,
            summary_type=summary_type.lower(),
        )

    result = llm.call(final_prompt, max_tokens=params["final_tokens"])

    header = (
        f"Конспект по выбранному разделу\n"
        f"Материал: {selected_file}\n"
        f"Раздел: {section_filter}\n"
        f"Тип: {summary_type.lower()}\n"
    )

    if topic:
        header += f"Тема / период: {topic}\n"

    header += f"Фрагментов раздела: {len(chunks)}\n\n"

    return header + result

def _clean_plan_line(line):
    """Очищает строку плана от нумерации и мусора."""
    line = str(line or "").strip()
    line = re.sub(r"^\s*[\-\*\d\.\)\:]+\s*", "", line)
    line = line.strip(" -—–•\t")
    return line.strip()


def build_topic_search_plan(llm, topic, summary_type, max_items=None):
    """
    Универсальный планировщик темы.

    Не пишет конспект, а создаёт поисковые подпункты.
    Работает для истории, сетей, математики, программирования и других дисциплин.
    """
    if max_items is None:
        max_items = getattr(config, "PLANNED_SUMMARY_QUERIES", 7)

    prompt = f"""{config.SYSTEM_PROMPT}

ТЕМА ПОЛЬЗОВАТЕЛЯ:
{topic}

Задача:
Разбей тему на {max_items} коротких поисковых подпунктов для поиска в учебных материалах.

Важно:
1. Не пиши конспект.
2. Не добавляй факты от себя.
3. Каждый подпункт должен быть коротким поисковым запросом.
4. Подпункты должны покрывать тему с разных сторон.
5. Если тема историческая — сохраняй хронологию.
6. Если тема техническая — иди от основных понятий к деталям.
7. Если тема математическая — выдели определения, свойства, формулы, методы и примеры.

Формат:
Каждый подпункт с новой строки.
Без пояснений.

ПОИСКОВЫЕ ПОДПУНКТЫ:"""

    raw = llm.call(prompt, max_tokens=500)

    lines = []
    for line in raw.splitlines():
        item = _clean_plan_line(line)
        if not item:
            continue
        if len(item) < 4:
            continue
        if item.lower() in {"поисковые подпункты", "план", "ответ"}:
            continue
        lines.append(item)

    # Убираем дубли, сохраняя порядок
    unique = []
    seen = set()

    for item in lines:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Fallback, если модель дала плохой план
    if not unique:
        unique = [topic]

    # Всегда добавляем исходную тему первым запросом
    if topic.lower() not in {x.lower() for x in unique}:
        unique.insert(0, topic)

    return unique[:max_items]


def _dedupe_chunks(chunks):
    """Убирает дубли найденных чанков."""
    unique = []
    seen = set()

    for chunk in chunks:
        text = chunk.get("text", "").strip()
        if not text:
            continue

        key = text[:500].lower()

        if key in seen:
            continue

        seen.add(key)
        unique.append(chunk)

    return unique


def _limit_chunks_per_section(chunks, max_per_section=None):
    """
    Не даёт одному разделу забить весь конспект.
    Это важно для больших тем.
    """
    if max_per_section is None:
        max_per_section = getattr(config, "PLANNED_SUMMARY_MAX_CHUNKS_PER_SECTION", 4)

    result = []
    section_counts = {}

    for chunk in chunks:
        section = chunk.get("section", "") or "Без раздела"
        source_file = chunk.get("source_file", "")
        key = (source_file, section)

        count = section_counts.get(key, 0)

        if count >= max_per_section:
            continue

        section_counts[key] = count + 1
        result.append(chunk)

    return result


def _chunks_to_context(chunks):
    """Собирает чанки в контекст для LLM."""
    context_parts = []

    for chunk in chunks:
        section = chunk.get("section", "")
        label = (
            f'{chunk["source_file"]} | {section}'
            if section
            else chunk["source_file"]
        )
        context_parts.append(f"[{label}]\n{chunk['text']}")

    return "\n\n---\n\n".join(context_parts)


def retrieve_chunks_by_plan(kb, topic, plan, file_filter="all", section_filter=None):
    """
    Ищет чанки по нескольким подпунктам плана.
    """
    per_query = getattr(config, "PLANNED_SUMMARY_CHUNKS_PER_QUERY", 5)
    max_chunks = getattr(config, "PLANNED_SUMMARY_MAX_CHUNKS", 40)

    all_chunks = []

    for item in plan:
        query = f"{topic}. {item}"

        chunks = kb.search_chunks_for_summary(
            query=query,
            file_filter=file_filter,
            section_filter=section_filter,
            top_k=per_query,
        )

        all_chunks.extend(chunks)

    all_chunks = _dedupe_chunks(all_chunks)
    all_chunks = _limit_chunks_per_section(all_chunks)

    # Возвращаем в порядке документа, а не в порядке релевантности.
    all_chunks.sort(
        key=lambda x: (
            x.get("source_file", ""),
            int(x.get("chunk_id", 0)),
        )
    )

    return all_chunks[:max_chunks]


def generate_planned_topic_summary(
    kb,
    llm,
    topic,
    summary_type,
    file_filter="all",
    section_filter=None,
):
    """
    Универсальный тематический конспект.

    Подходит для широких тем:
    - история России XX века;
    - компьютерные сети;
    - преобразование Лапласа;
    - ООП;
    - базы данных;
    - медицина и т.д.

    Вместо одного поиска:
    тема → план → поиск по каждому пункту → сборка конспекта.
    """
    params = _summary_generation_params(summary_type)

    plan = build_topic_search_plan(
        llm=llm,
        topic=topic,
        summary_type=summary_type,
        max_items=getattr(config, "PLANNED_SUMMARY_QUERIES", 7),
    )

    topic_chunks = retrieve_chunks_by_plan(
        kb=kb,
        topic=topic,
        plan=plan,
        file_filter=file_filter,
        section_filter=section_filter,
    )

    if not topic_chunks:
        return (
            "Информация по указанной теме/периоду не найдена в выбранных материалах.\n\n"
            "Попробуйте:\n"
            "• выбрать другой файл;\n"
            "• выбрать конкретный раздел;\n"
            "• переформулировать тему."
        )

    group_size = params["group_size"]
    partial_summaries = []

    for i in range(0, len(topic_chunks), group_size):
        group = topic_chunks[i:i + group_size]
        context = _chunks_to_context(group)

        prompt = f"""{config.SYSTEM_PROMPT}

        ТЕМА:
        {topic}

        ФРАГМЕНТЫ УЧЕБНОГО МАТЕРИАЛА:
        {context}

        Задача:
        Сделай промежуточный конспект по этим фрагментам в рамках указанной темы.

        Важно:
        1. Используй только данные из фрагментов.
        2. Не добавляй факты от себя.
        3. Если часть фрагментов слабо относится к теме, просто не используй её.
        4. Не пиши "НЕ ОТНОСИТСЯ", если во фрагментах есть хотя бы немного полезной информации.
        5. Пиши кратко, структурно, на русском языке.

        ПРОМЕЖУТОЧНЫЙ КОНСПЕКТ:"""

        partial = llm.call(
            prompt,
            max_tokens=params["chunk_tokens"],
        ).strip()

        if partial:
            partial_summaries.append(partial)

    if not partial_summaries:
        return (
            "Информация по указанной теме не найдена в выбранных материалах.\n\n"
            "Попробуйте:\n"
            "• выбрать конкретный раздел;\n"
            "• выбрать другой файл;\n"
            "• переформулировать тему."
        )

    combined_context = "\n\n---\n\n".join(partial_summaries)

    final_prompt = f"""{config.SYSTEM_PROMPT}

ТЕМА:
{topic}

ПОИСКОВЫЙ ПЛАН:
{chr(10).join(f"- {item}" for item in plan)}

ПРОМЕЖУТОЧНЫЕ КОНСПЕКТЫ:
{combined_context}

Задача:
Составь {summary_type.lower()} итоговый тематический конспект.

Инструкция:
1. Используй только промежуточные конспекты.
2. Сохрани структуру темы.
3. Не добавляй факты от себя.
4. Если какие-то пункты плана не раскрыты в найденных фрагментах, укажи это в конце.
5. Для исторических тем сохраняй хронологический порядок.
6. Для технических тем объясняй от общего к частному.
7. Для математических тем выделяй определения, формулы, свойства и применение.
8. В конце добавь короткий итог.

ИТОГОВЫЙ КОНСПЕКТ:"""

    result = llm.call(
        final_prompt,
        max_tokens=params["final_tokens"],
    )

    section_label = section_filter if section_filter else "Все разделы"

    header = (
        f"Тематический конспект\n"
        f"Тема / период: {topic}\n"
        f"Раздел: {section_label}\n"
        f"Тип: {summary_type.lower()}\n"
        f"Режим: плановый тематический конспект\n"
        f"Пунктов плана: {len(plan)}\n"
        f"Найдено фрагментов: {len(topic_chunks)}\n\n"
        f"План поиска:\n"
        + "\n".join(f"• {item}" for item in plan)
        + "\n\n"
    )

    return header + result

def generate_topic_summary(kb, llm, topic, summary_type, file_filter="all", section_filter=None):
    """
    Тематический конспект через semantic search + rerank.

    Тема → HyDE → embedding → ChromaDB → rerank → лучшие чанки → map-reduce конспект.
    """
    params = _summary_generation_params(summary_type)
    topic_chunks = kb.search_chunks_for_summary(
        query=topic,
        file_filter=file_filter,
        section_filter=section_filter,
        top_k=params["top_k"],
    )

    if not topic_chunks:
        return (
            "Информация по указанной теме/периоду не найдена в выбранных материалах.\n\n"
            "Попробуйте:\n"
            "• выбрать другой файл;\n"
            "• выбрать «Все разделы»;\n"
            "• указать тему иначе."
        )

    group_size = params["group_size"]
    partial_summaries = []

    for i in range(0, len(topic_chunks), group_size):
        group = topic_chunks[i:i + group_size]

        context_parts = []

        for chunk in group:
            section = chunk.get("section", "")
            label = (
                f'{chunk["source_file"]} | {section}'
                if section
                else chunk["source_file"]
            )
            context_parts.append(f"[{label}]\n{chunk['text']}")

        context = "\n\n---\n\n".join(context_parts)

        prompt = config.PROMPTS["topic_summary_chunk"].format(
            system=config.SYSTEM_PROMPT,
            topic=topic,
            context=context,
        )

        partial_raw = llm.call(prompt, max_tokens=params["chunk_tokens"])
        partial = partial_raw.strip()

        partial_clean = partial.strip()
        partial_upper = partial_clean.upper()

        if partial_clean and not partial_upper.startswith("НЕ ОТНОСИТСЯ"):
            partial_summaries.append(partial_clean)

    if not partial_summaries:
        return (
            "Информация по указанной теме/периоду не найдена в выбранных материалах.\n\n"
            "Попробуйте:\n"
            "• указать тему иначе;\n"
            "• выбрать другой файл;\n"
            "• выбрать «Все разделы»."
        )

    combined_context = "\n\n---\n\n".join(partial_summaries)

    final_prompt = config.PROMPTS["topic_summary_reduce"].format(
        system=config.SYSTEM_PROMPT,
        topic=topic,
        context=combined_context,
        summary_type=summary_type.lower(),
    )

    result = llm.call(final_prompt, max_tokens=params["final_tokens"])

    section_label = section_filter if section_filter else "Все разделы"

    header = (
        f"Тематический конспект\n"
        f"Тема / период: {topic}\n"
        f"Раздел: {section_label}\n"
        f"Тип: {summary_type.lower()}\n"
        f"Найдено фрагментов: {len(topic_chunks)}\n\n"
    )

    return header + result

def on_generate_summary(selected_file, selected_section, topic, summary_type):
    """Сгенерировать конспект по выбранному файлу через обработку чанков."""
    try:
        kb = _get_kb()
        llm = _get_llm()

        file_filter = "all" if selected_file == "Все файлы" else selected_file

        section_filter = None
        if selected_section and selected_section != "Все разделы":
            section_filter = selected_section

        topic = (topic or "").strip()

        # Если пользователь явно выбрал раздел — работаем только с ним.
        # Это быстрее и точнее, чем semantic search по всему учебнику.
        if section_filter:
            return generate_selected_section_summary(
                kb=kb,
                llm=llm,
                selected_file=selected_file,
                section_filter=section_filter,
                topic=topic,
                summary_type=summary_type,
            )

        # Если раздел не выбран, но тема указана — используем плановый тематический конспект.
        if topic:
            if getattr(config, "PLANNED_SUMMARY_ENABLED", True):
                return generate_planned_topic_summary(
                    kb=kb,
                    llm=llm,
                    topic=topic,
                    summary_type=summary_type,
                    file_filter=file_filter,
                    section_filter=None,
                )

            return generate_topic_summary(
                kb=kb,
                llm=llm,
                topic=topic,
                summary_type=summary_type,
                file_filter=file_filter,
                section_filter=None,
            )

        params = _summary_generation_params(summary_type)
        chunks = kb.get_file_chunks(file_filter=file_filter)

        if not chunks:
            return "НЕТ ИНФОРМАЦИИ - база пуста или файл не проиндексирован."

        # Берём группы чанков, чтобы не перегружать модель.
        group_size = params["group_size"]
        partial_summaries = []

        for i in range(0, len(chunks), group_size):
            group = chunks[i:i + group_size]

            context_parts = []
            for chunk in group:
                section = chunk["section"]
                label = f'{chunk["source_file"]} | {section}' if section else chunk["source_file"]
                context_parts.append(f"[{label}]\n{chunk['text']}")

            context = "\n\n---\n\n".join(context_parts)

            prompt = config.PROMPTS["summary_chunk"].format(
                system=config.SYSTEM_PROMPT,
                context=context,
            )

            partial = llm.call(prompt, max_tokens=params["chunk_tokens"])
            if partial.strip():
                partial_summaries.append(partial.strip())

        combined_context = "\n\n---\n\n".join(partial_summaries)

        final_prompt = config.PROMPTS["summary_reduce"].format(
            system=config.SYSTEM_PROMPT,
            context=combined_context,
            summary_type=summary_type.lower(),
        )

        summary = llm.call(final_prompt, max_tokens=params["final_tokens"])

        file_label = "всем материалам" if selected_file == "Все файлы" else selected_file
        section_label = (
            "всем разделам"
            if selected_section == "Все разделы"
            else selected_section
        )

        header = (
            f"Конспект по материалу: {file_label}\n"
            f"Раздел: {section_label}\n"
            f"Тип: {summary_type.lower()}\n\n"
        )

        return header + summary

    except Exception as e:
        return f"Ошибка: {e}"

# Построение веб-интерфейса

def build_gui():
    chatbot_kwargs = _gradio_chatbot_kwargs()

    with gr.Blocks(title="BonchMind Pro", css="""
        footer {display: none !important;}
        .built-with {display: none !important;}
        .show-api {display: none !important;}
        .settings-btn {display: none !important;}
        #footer {display: none !important;}
        .gradio-container > footer {display: none !important;}
    """) as app:

        gr.HTML("""
        <div style="text-align:center;padding:16px 0 8px">
            <h1 style="font-size:2em;font-weight:bold;">BonchMind Pro</h1>
            <p style="color:#888;font-size:1em;">
                Умный ассистент по учебным текстам
            </p>
        </div>""")

        with gr.Tabs():

            # Вкладка "Чат"
            with gr.TabItem("💬 Ассистент"):
                gr.Markdown("### Вопросы по загруженным текстам")
                with gr.Row():
                    file_dropdown = gr.Dropdown(
                        choices=get_file_choices(), value="Все файлы",
                        label="📄 Искать в файле", scale=3, interactive=True,
                    )
                    answer_mode = gr.Dropdown(
                        choices=["Обычный", "Кратко", "Подробно", "Только цитаты"],
                        value="Обычный",
                        label="✍️ Тип ответа",
                        scale=2,
                        interactive=True,
                    )
                    refresh_btn = gr.Button("🔄", scale=1, size="sm")
                chatbot = gr.Chatbot(height=480, show_label=False, **chatbot_kwargs)
                with gr.Row():
                    chat_in = gr.Textbox(
                        placeholder="Задайте вопрос...",
                        show_label=False, scale=9, container=False
                    )
                    chat_btn = gr.Button("Отправить", variant="primary", scale=1)
                chat_clear = gr.Button("🗑️ Очистить историю", size="sm")

                export_btn = gr.Button("📄 Экспорт ответа в DOCX", size="sm")
                export_file = gr.File(label="Скачать DOCX", visible=True)

                refresh_btn.click(on_refresh_files, outputs=file_dropdown)
                chat_btn.click(
                    chat_respond, inputs=[chat_in, chatbot, file_dropdown, answer_mode], outputs=chatbot
                ).then(lambda: "", outputs=chat_in)
                chat_in.submit(
                    chat_respond, inputs=[chat_in, chatbot, file_dropdown, answer_mode], outputs=chatbot
                ).then(lambda: "", outputs=chat_in)
                chat_clear.click(lambda: [], outputs=chatbot)
                export_btn.click(
                    on_export_docx,
                    inputs=chatbot,
                    outputs=export_file
                )

            # Вкладка "Конспект"
            with gr.TabItem("📝 Конспект"):
                gr.Markdown("### Генерация конспекта по учебным материалам")

                with gr.Row():
                    summary_file = gr.Dropdown(
                        choices=get_file_choices(),
                        value="Все файлы",
                        label="📄 Материал",
                        scale=3,
                        interactive=True,
                    )
                    summary_refresh = gr.Button("🔄", scale=1, size="sm")

                summary_section = gr.Dropdown(
                    choices=["Все разделы"] + _get_kb().get_available_sections(),
                    value="Все разделы",
                    label="📑 Раздел",
                    scale=3,
                    interactive=True,
                )

                summary_file.change(
                    on_file_change_for_summary,
                    inputs=summary_file,
                    outputs=summary_section,
                )

                summary_topic = gr.Textbox(
                    label="Тема / период",
                    placeholder="Например: Россия после Николая II до 2000 года",
                    lines=2,
                )

                summary_type = gr.Dropdown(
                    choices=["Краткий", "Средний", "Подробный"],
                    value="Средний",
                    label="Тип конспекта",
                    interactive=True,
                )

                summary_btn = gr.Button("📄 Сгенерировать конспект", variant="primary")
                gr.Markdown("⚠️ Для больших документов генерация полного конспекта может занять несколько минут.")
                summary_out = gr.Textbox(
                    label="Конспект",
                    lines=18,
                )

                with gr.Row():
                    summary_export_btn = gr.Button("📄 Экспорт конспекта в DOCX", size="sm")
                    summary_export_file = gr.File(label="Скачать конспект DOCX", visible=True)

                summary_refresh.click(on_refresh_files, outputs=summary_file)
                summary_refresh.click(on_refresh_sections, outputs=summary_section)
                summary_file.change(
                    clear_summary_output,
                    outputs=[summary_out, summary_export_file],
                )

                summary_section.change(
                    clear_summary_output,
                    outputs=[summary_out, summary_export_file],
                )

                summary_type.change(
                    clear_summary_output,
                    outputs=[summary_out, summary_export_file],
                )
                summary_topic.change(
                    clear_summary_output,
                    outputs=[summary_out, summary_export_file],
                )
                summary_btn.click(
                    on_generate_summary,
                    inputs=[summary_file, summary_section, summary_topic, summary_type],
                    outputs=summary_out,
                )

                summary_export_btn.click(
                    on_export_summary_docx,
                    inputs=[summary_out, summary_file, summary_section, summary_type],
                    outputs=summary_export_file,
                )

            # Вкладка "Файлы"
            with gr.TabItem("📚 Материалы"):
                gr.Markdown("### Управление базой знаний")
                with gr.Row():
                    with gr.Column():
                        book_upload = gr.File(label="Загрузить файлы", file_count="multiple",
                                              file_types=config.SUPPORTED_FORMATS)
                        book_up_btn = gr.Button("📥 Загрузить и индексировать", variant="primary")
                    with gr.Column():
                        book_idx_btn = gr.Button("🔄 Индексировать папку docs/", variant="secondary")
                        book_stats_btn = gr.Button("📊 Статистика")
                        book_clr_btn = gr.Button("🗑️ Очистить базу", variant="stop")
                book_out = gr.Textbox(label="Результат", lines=10)
                book_up_btn.click(on_add_book, book_upload, book_out)
                book_idx_btn.click(on_index_books, None, book_out)
                book_stats_btn.click(on_stats, None, book_out)
                book_clr_btn.click(on_clear_kb, None, book_out)

            # Вкладка "О системе"
            with gr.TabItem("⚙️ Система"):
                gr.Markdown("""### BonchMind Pro

                AI-ассистент для работы с учебными материалами.

                **Основные возможности:**
                1. Загрузка и индексация учебных документов.
                2. Вопросы по материалам с опорой на найденные источники.
                3. Разные режимы ответа: обычный, краткий, подробный и только цитаты.
                4. Генерация кратких и подробных конспектов.
                5. Экспорт ответов и конспектов в DOCX.

                **Как пользоваться:**
                1. Перейдите во вкладку «📚 Материалы» и загрузите учебные материалы.
                2. Нажмите «Загрузить и индексировать».
                3. Вернитесь во вкладку «💬 Ассистент».
                4. Выберите нужный файл и тип ответа.
                5. Задавайте вопросы по материалам.

                **Поддерживаемые форматы:** PDF, TXT, EPUB, DOCX, Markdown, FB2, FB2.ZIP, HTML.

                **Режимы LLM:** OpenRouter API или локальный запуск через Ollama.
                """)
                gr.Markdown("### Оформление")
                theme_btn = gr.Button("🌙 Переключить тему (светлая / тёмная)", size="sm")
                theme_btn.click(fn=None, js="""
                    () => {
                        const url = new URL(window.location);
                        const html = document.querySelector('html');
                        const isDark = html.classList.contains('dark') ||
                                       url.searchParams.get('__theme') === 'dark' ||
                                       (!url.searchParams.has('__theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
                        url.searchParams.set('__theme', isDark ? 'light' : 'dark');
                        window.location.href = url.href;
                    }
                """)

    return app


# Запуск приложения

if __name__ == "__main__":
    config_errors = config.validate_config()
    if config_errors:
        print("Ошибки конфигурации:")
        for err in config_errors:
            print(f" - {err}")
        sys.exit(1)

    for d in [config.DOCS_DIR, config.DATA_DIR]:
        os.makedirs(d, exist_ok=True)

    mode = config.LLM_MODE
    if mode == "api":
        llm_label = f"API / {getattr(config, 'API_MODEL', '?')}"
    else:
        llm_label = f"OLLAMA / {config.OLLAMA_MODEL}"

    print("BonchMind")
    print(f" LLM: {llm_label}")
    print(f"Эмбеддинги: {config.EMBEDDING_MODEL}")
    print(f"Реранкер: {config.RERANKER_MODEL}")
    print(f" Чанк: {config.CHUNK_SIZE} симв.")
    print(f"HyDE: {'вкл' if config.USE_HYDE else 'выкл'}")
    print(f"Gradio: v{gr.__version__}")

    app = build_gui()
    app.launch(
        server_port=config.GUI_PORT,
        share=config.GUI_SHARE,
        inbrowser=True,
    )
