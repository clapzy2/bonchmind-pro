from src.text_processing import detect_sections, clean_sections


def test_detect_sections_by_headers():
    text = """
ВВЕДЕНИЕ

Это первый раздел текста.

ГЛАВА 1

Это текст первой главы.
"""

    sections = detect_sections(text)

    assert len(sections) >= 2
    section_names = [name for name, _ in sections]

    assert "ВВЕДЕНИЕ" in section_names
    assert "ГЛАВА 1" in section_names


def test_clean_sections_removes_extra_spaces_and_newlines():
    sections = [
        ("Раздел", "Текст   с   лишними    пробелами.\n\n\n\nНовая строка.")
    ]

    cleaned = clean_sections(sections)

    assert cleaned[0][1] == "Текст с лишними пробелами.\n\nНовая строка."