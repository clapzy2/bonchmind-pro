"""
document_loader.py - загрузка и извлечение текста из документов разных форматов.
"""

import os
import zipfile
import tempfile


def load_txt(path):
    """Прочитать текстовый файл, пробуя разные кодировки."""
    for enc in ["utf-8", "cp1251", "latin-1", "cp866"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Не удалось прочитать: {path}")


def load_pdf(path):
    """Извлечь текст из PDF."""
    from PyPDF2 import PdfReader

    reader = PdfReader(path)
    return "\n\n".join(
        page.extract_text()
        for page in reader.pages
        if page.extract_text()
    )


def load_docx(path):
    """Извлечь текст из Word-документа."""
    from docx import Document

    doc = Document(path)
    return "\n\n".join(
        paragraph.text
        for paragraph in doc.paragraphs
        if paragraph.text.strip()
    )


def load_epub(path):
    """Извлечь текст из EPUB."""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(path)
    parts = []

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator="\n")
        if text.strip():
            parts.append(text.strip())

    return "\n\n".join(parts)


def load_fb2(path):
    """Извлечь текст из FB2."""
    from bs4 import BeautifulSoup

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "lxml-xml")

    body = soup.find("body")
    return body.get_text(separator="\n") if body else soup.get_text(separator="\n")


def load_fb2zip(path):
    """Распаковать ZIP и извлечь текст из FB2 внутри архива."""
    with zipfile.ZipFile(path, "r") as zf:
        fb2_files = [
            name for name in zf.namelist()
            if name.lower().endswith(".fb2")
        ]

        if not fb2_files:
            raise ValueError(f"Нет .fb2 внутри архива: {path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            zf.extract(fb2_files[0], tmpdir)
            return load_fb2(os.path.join(tmpdir, fb2_files[0]))


def load_html(path):
    """Извлечь текст из HTML."""
    from bs4 import BeautifulSoup

    text = load_txt(path)
    return BeautifulSoup(text, "html.parser").get_text(separator="\n")


LOADERS = {
    ".pdf": load_pdf,
    ".txt": load_txt,
    ".md": load_txt,
    ".docx": load_docx,
    ".epub": load_epub,
    ".fb2": load_fb2,
    ".fb2.zip": load_fb2zip,
    ".html": load_html,
    ".htm": load_html,
}


def load_file(path):
    """Определить формат файла и извлечь текст."""
    lower = path.lower()

    if lower.endswith(".fb2.zip"):
        return load_fb2zip(path)

    ext = os.path.splitext(path)[1].lower()
    loader = LOADERS.get(ext)

    if not loader:
        raise ValueError(f"Неподдерживаемый формат: {ext}")

    return loader(path)