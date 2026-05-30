"""
chat_utils.py - вспомогательные функции для обработки сообщений и истории чата.
"""

REFUSAL_PHRASES = [
    "нет информации", "не упоминается", "не содержит",
    "не могу найти", "отсутствует", "нет данных",
    "no information", "not mentioned",
]

FOLLOWUP_PHRASES = [
    "точно", "уверен", "правда", "докажи", "обоснуй",
    "подробнее", "аргументы", "аргумент", "объясни", "почему",
    "зачем", "пример", "примеры", "поясни", "разъясни", "расскажи подробнее",
    "как так", "серьёзно", "не понял", "уточни", "ещё", "что такое",
    "а что", "а как", "а почему", "а зачем", "расскажи ещё",
    "продолжи", "дальше",
]

CORRECTION_PHRASES = [
    "нет,", "неправильно", "неверно", "ошибка", "ты ошибся",
    "правильный ответ", "на самом деле", "не так", "неточно",
    "ты не прав", "это неправда", "некорректно", "нет это",
    "ответ неверный", "ответ неправильный", "нет правильный",
    "все-таки", "всё-таки", "однако нет", "а вот нет",
]

GREETING_PHRASES = [
    "привет", "здравствуй", "добрый", "hi", "hello",
]


def extract_content(msg):
    """Извлечь текст из сообщения Gradio."""
    content = msg.get("content", "") if isinstance(msg, dict) else str(msg)

    if isinstance(content, list):
        content = " ".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )

    return str(content).strip()


def is_greeting(text):
    """Определяет короткое приветствие."""
    lower = text.lower().strip()
    words = lower.replace(",", " ").replace("!", " ").replace(".", " ").split()

    if len(words) > 3:
        return False

    return any(word in GREETING_PHRASES for word in words)


def is_refusal(text):
    """Проверяет, сказала ли LLM, что информации нет."""
    lower = text.lower().strip()

    if not lower:
        return True

    if len(lower) < 150:
        return any(phrase in lower for phrase in REFUSAL_PHRASES)

    return any(phrase in lower[:100] for phrase in REFUSAL_PHRASES)


def is_correction(text):
    """Определяет, исправляет ли пользователь предыдущий ответ."""
    lower = text.lower().strip()

    if len(lower.split()) > 20:
        return False

    return any(
        lower.startswith(phrase) or f" {phrase} " in lower
        for phrase in CORRECTION_PHRASES
    )


def is_followup(text):
    """Определяет уточняющий вопрос."""
    lower = text.lower().strip()

    if len(lower.split()) <= 12:
        return any(lower == phrase or lower.startswith(phrase) for phrase in FOLLOWUP_PHRASES)

    return False


def history_to_context(history, n_last=4):
    """Превращает историю чата в текст для промпта."""
    if not history or len(history) < 2:
        return ""

    recent = history[-n_last * 2:] if len(history) > n_last * 2 else history
    lines = []

    for msg in recent:
        role = "Пользователь" if msg.get("role") == "user" else "Ассистент"
        content = extract_content(msg)

        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines)


def get_last_qa(history):
    """Извлекает последний вопрос и ответ из истории."""
    last_answer, last_question = "", ""

    for msg in reversed(history):
        role = msg.get("role", "")
        content = extract_content(msg)

        if role == "assistant" and not last_answer:
            last_answer = content
        elif role == "user" and not last_question:
            last_question = content
            break

    return last_question, last_answer