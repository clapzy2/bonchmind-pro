"""
main.py - запускает веб-интерфейс.
Пользователь может загружать файлы и задавать вопросы по текстам.
"""
import warnings
warnings.filterwarnings("ignore")

import os
import sys
import gc
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
            refusal_text = "НЕТ ИНФОРМАЦИИ"

            if sources:
                source_lines = ["\n\n**Близкие найденные фрагменты:**"]

                for i, src in enumerate(sources[:3], start=1):
                    section = src.get("section", "")
                    score = src.get("score", 0)

                    if section:
                        source_lines.append(
                            f"{i}. {src['source_file']} → {section}\n"
                            f"   Релевантность: {score}"
                        )
                    else:
                        source_lines.append(
                            f"{i}. {src['source_file']}\n"
                            f"   Релевантность: {score}"
                        )

                refusal_text += "\n".join(source_lines)

            new_history[-1]["content"] = refusal_text
            yield new_history
            return

        if sources:
            source_lines = ["\n\n**Основные найденные источники:**"]

            for i, src in enumerate(sources[:3], start=1):
                section = src.get("section", "")
                score = src.get("score", 0)

                if section:
                    source_lines.append(
                        f"{i}. {src['source_file']} → {section}\n"
                        f"   Релевантность: {score}"
                    )
                else:
                    source_lines.append(
                        f"{i}. {src['source_file']}\n"
                        f"   Релевантность: {score}"
                    )

            new_history[-1]["content"] = answer + "\n".join(source_lines)
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

def on_generate_summary(selected_file, selected_section, summary_type):
    """Сгенерировать конспект по выбранному файлу через обработку чанков."""
    try:
        kb = _get_kb()
        llm = _get_llm()

        file_filter = "all" if selected_file == "Все файлы" else selected_file
        chunks = kb.get_file_chunks(file_filter=file_filter)

        if selected_section and selected_section != "Все разделы":
            chunks = [
                chunk for chunk in chunks
                if chunk.get("section") == selected_section
            ]

        if not chunks:
            return "НЕТ ИНФОРМАЦИИ - база пуста или файл не проиндексирован."

        # Берём группы чанков, чтобы не перегружать модель.
        group_size = 5
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

            partial = llm.call(prompt, max_tokens=900)
            if partial.strip():
                partial_summaries.append(partial.strip())

        combined_context = "\n\n---\n\n".join(partial_summaries)

        final_prompt = config.PROMPTS["summary_reduce"].format(
            system=config.SYSTEM_PROMPT,
            context=combined_context,
            summary_type=summary_type.lower(),
        )

        summary = llm.call(final_prompt, max_tokens=1800)

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
                summary_btn.click(
                    on_generate_summary,
                    inputs=[summary_file, summary_section, summary_type],
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