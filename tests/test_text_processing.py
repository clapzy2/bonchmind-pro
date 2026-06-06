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


def test_detect_sections_accepts_number_only_chapter_headers():
    text = """
ГЛАВА 1

Первый раздел.

ГЛАВА 2.

Второй раздел.
"""

    sections = detect_sections(text)

    assert [name for name, _ in sections] == ["ГЛАВА 1", "ГЛАВА 2."]


def test_detect_sections_ignores_pdf_caption_and_bibliography_noise():
    text = """
§ 10. Советская экономика после войны

Основной текст раздела.

(КАМАЗ, г. Набережные Челны), Вол -

100. М.В. Ломоносов. Российская грамматика / [соч.] Михаила Ломоносова. – СПб.,

Июль 2023 г. Автор фото: Мария Девахина. © РИА Новости».

11. Почему СССР победил в Великой Отечественной вой не? Каковы были цена

Продолжение основного текста.

§ 11. Политические реформы

Следующий раздел.
"""

    sections = detect_sections(text)
    section_names = [name for name, _ in sections]

    assert section_names == [
        "§ 10. Советская экономика после войны",
        "§ 11. Политические реформы",
    ]


def test_detect_sections_keeps_real_uppercase_topic_headers():
    text = """
РОССИЯ 1990-Х ГОДОВ

Текст раздела.

РОССИЙСКАЯ ФЕДЕРАЦИЯ В НАЧАЛЕ XXI ВЕКА

Следующий текст.
"""

    sections = detect_sections(text)

    assert [name for name, _ in sections] == [
        "РОССИЯ 1990-Х ГОДОВ",
        "РОССИЙСКАЯ ФЕДЕРАЦИЯ В НАЧАЛЕ XXI ВЕКА",
    ]


def test_detect_sections_does_not_treat_acronym_heavy_sentences_as_headers():
    text = """
§ 12. Великая Отечественная война

Почему СССР и РККА смогли победить в Великой Отечественной войне?

В тексте встречаются КПСС, СНК, ВЦИК и другие сокращения, но это обычный абзац.

§ 13. Послевоенное восстановление

Следующий раздел.
"""

    sections = detect_sections(text)

    assert [name for name, _ in sections] == [
        "§ 12. Великая Отечественная война",
        "§ 13. Послевоенное восстановление",
    ]


def test_clean_sections_removes_extra_spaces_and_newlines():
    sections = [
        ("Раздел", "Текст   с   лишними    пробелами.\n\n\n\nНовая строка.")
    ]

    cleaned = clean_sections(sections)

    assert cleaned[0][1] == "Текст с лишними пробелами.\n\nНовая строка."
