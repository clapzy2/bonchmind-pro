from src.chat_utils import (
    is_greeting,
    is_refusal,
    is_followup,
    is_correction,
    history_to_context,
    get_last_qa,
)


def test_greeting_detection():
    assert is_greeting("привет")
    assert is_greeting("добрый день")
    assert not is_greeting("привет, расскажи подробно про главу")


def test_refusal_detection():
    assert is_refusal("НЕТ ИНФОРМАЦИИ")
    assert is_refusal("В тексте нет данных по этому вопросу.")
    assert not is_refusal("В тексте говорится о главном герое.")


def test_followup_detection():
    assert is_followup("подробнее")
    assert is_followup("почему")
    assert is_followup("а как это работает")
    assert not is_followup("Расскажи мне полностью содержание первой главы произведения")


def test_correction_detection():
    assert is_correction("неправильно")
    assert is_correction("нет, это не так")
    assert not is_correction("Расскажи подробно про неправильное поведение героя в тексте")


def test_history_helpers():
    history = [
        {"role": "user", "content": "Что такое RAG?"},
        {"role": "assistant", "content": "RAG — это подход с поиском по источникам."},
    ]

    ctx = history_to_context(history)
    question, answer = get_last_qa(history)

    assert "Пользователь: Что такое RAG?" in ctx
    assert "Ассистент: RAG" in ctx
    assert question == "Что такое RAG?"
    assert answer.startswith("RAG")