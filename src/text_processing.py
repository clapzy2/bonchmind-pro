"""
text_processing.py - обработка текста: разделы, очистка, чанкинг.
"""

import re

import config


def detect_sections(text):
    """
    Разбивает текст на разделы по заголовкам.

    Заголовок определяется по паттернам:
    - отступ;
    - заглавные буквы;
    - слова Глава / Часть / Раздел / Chapter / Part / Section;
    - окружение пустыми строками;
    - длина строки меньше 120 символов.
    """
    lines = text.split("\n")
    header_patterns = [
        r'^\s{2,}[А-ЯЁA-Z][А-Яа-яёЁA-Za-z\s:–\\.,-]+\s*$',
        r'^\s*(Глава|Часть|Раздел|Chapter|Part|Section)\s+[\dIVXLCDMivxlcdm]+.*$',
        r'^\s*[А-ЯЁA-Z\s:–\\-]{10,}\s*$',
    ]

    sections = []
    current_header = ""
    current_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not stripped:
            current_lines.append(line)
            continue

        is_header = False

        for pattern in header_patterns:
            if re.match(pattern, line) and len(stripped) < 120:
                prev_empty = (i == 0) or (i > 0 and not lines[i - 1].strip())
                next_empty = (i == len(lines) - 1) or (i < len(lines) - 1 and not lines[i + 1].strip())

                if prev_empty and next_empty:
                    is_header = True
                    break

        if is_header:
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append((current_header, body))

            current_header = stripped
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_header, body))

    if len(sections) <= 1:
        return [("", text)]

    return sections


def clean_sections(sections):
    """Очищает текст разделов от лишних пробелов и переносов."""
    cleaned = []

    for name, body in sections:
        body = re.sub(r"\n{3,}", "\n\n", body)
        body = re.sub(r" {2,}", " ", body)
        cleaned.append((name, body))

    return cleaned


def get_splitter():
    """Создаёт объект для разбиения текста на чанки."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n\n", "\n\n", "\n", ". ", "; ", " ", ""],
    )