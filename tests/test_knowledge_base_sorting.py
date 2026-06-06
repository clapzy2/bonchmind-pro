from src.knowledge_base import KnowledgeBase


def test_section_sort_key_orders_chapters_naturally():
    sections = ["Глава 12", "Глава 2", "Глава 1", "Глава 10"]

    assert sorted(sections, key=KnowledgeBase._section_sort_key) == [
        "Глава 1",
        "Глава 2",
        "Глава 10",
        "Глава 12",
    ]


def test_section_sort_key_keeps_paragraph_numbers_natural():
    sections = ["§ 10. Экономика", "§ 2. Начало", "§ 11. Политика"]

    assert sorted(sections, key=KnowledgeBase._section_sort_key) == [
        "§ 2. Начало",
        "§ 10. Экономика",
        "§ 11. Политика",
    ]

