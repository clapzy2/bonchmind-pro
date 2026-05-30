def test_import_config():
    import config
    assert config.CHUNK_SIZE > 0


def test_import_prompts():
    from src.prompts import SYSTEM_PROMPT, PROMPTS
    assert SYSTEM_PROMPT
    assert "qa" in PROMPTS
    assert "hyde" in PROMPTS


def test_import_document_loader():
    from src.document_loader import load_file
    assert callable(load_file)


def test_import_text_processing():
    from src.text_processing import detect_sections, clean_sections, get_splitter
    assert callable(detect_sections)
    assert callable(clean_sections)
    assert callable(get_splitter)


def test_import_chat_utils():
    from src.chat_utils import is_greeting, is_refusal, is_followup, is_correction
    assert is_greeting("привет")
    assert is_refusal("НЕТ ИНФОРМАЦИИ")
    assert is_followup("подробнее")
    assert is_correction("неправильно")