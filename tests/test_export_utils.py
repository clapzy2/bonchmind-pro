from src.export_utils import _message_to_text, make_safe_filename


def test_message_to_text_from_string():
    assert _message_to_text("Привет") == "Привет"


def test_message_to_text_from_gradio_list():
    content = [{"text": "Цитаты из Речи Федра", "type": "text"}]
    assert _message_to_text(content) == "Цитаты из Речи Федра"


def test_message_to_text_from_multiple_parts():
    content = [
        {"text": "Первая часть", "type": "text"},
        {"text": "Вторая часть", "type": "text"},
    ]
    assert _message_to_text(content) == "Первая часть\nВторая часть"


def test_make_safe_filename():
    result = make_safe_filename("Пир: Речь Федра / краткий")
    assert "пир" in result
    assert "речь_федра" in result
    assert "/" not in result
    assert ":" not in result