from pathlib import Path

from src.document_loader import load_file


def test_load_txt_file():
    path = Path(__file__).parent / "sample.txt"
    text = load_file(str(path))

    assert "BonchMind Pro" in text
    assert "тестовый учебный текст" in text