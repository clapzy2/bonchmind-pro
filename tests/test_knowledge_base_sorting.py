from src.knowledge_base import KnowledgeBase
import config


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


def test_is_library_file_path_accepts_root_docs_file(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    monkeypatch.setattr(config, "DOCS_DIR", str(docs_dir))

    target = docs_dir / "book.pdf"

    assert KnowledgeBase._is_library_file_path(str(target)) is True


def test_is_library_file_path_rejects_internal_subdirectory_file(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    (docs_dir / "superpowers" / "specs").mkdir(parents=True)
    monkeypatch.setattr(config, "DOCS_DIR", str(docs_dir))

    target = docs_dir / "superpowers" / "specs" / "design.md"

    assert KnowledgeBase._is_library_file_path(str(target)) is False

