"""
export_utils.py - экспорт ответов BonchMind Pro в DOCX.
"""

from datetime import datetime
from pathlib import Path

from docx import Document


EXPORT_DIR = Path("exports")


def _message_to_text(content):
    """Преобразовать сообщение Gradio в обычный текст."""
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")).strip())
            else:
                parts.append(str(item).strip())
        return "\n".join(part for part in parts if part)

    if isinstance(content, dict):
        return str(content.get("text", "")).strip()

    return str(content).strip()


def _extract_last_qa(history):
    """Получить последний вопрос и ответ из истории Gradio."""
    if not history:
        return "", ""

    last_question = ""
    last_answer = ""

    for msg in reversed(history):
        role = msg.get("role", "")
        content = _message_to_text(msg.get("content", ""))

        if role == "assistant" and not last_answer:
            last_answer = content
        elif role == "user" and not last_question:
            last_question = content
            break

    return last_question, last_answer


def export_last_answer_to_docx(history):
    """
    Экспортирует последний вопрос и ответ в DOCX.
    Возвращает путь к созданному файлу.
    """
    question, answer = _extract_last_qa(history)

    if not question or not answer:
        return None

    EXPORT_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = EXPORT_DIR / f"bonchmind_answer_{timestamp}.docx"

    doc = Document()

    doc.add_heading("BonchMind Pro — экспорт ответа", level=1)
    doc.add_paragraph(f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    doc.add_heading("Вопрос", level=2)
    doc.add_paragraph(question)

    doc.add_heading("Ответ", level=2)
    for block in answer.split("\n"):
        block = block.strip()
        if block:
            doc.add_paragraph(block)

    doc.save(filename)
    return str(filename)