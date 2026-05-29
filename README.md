# BonchMind Pro

BonchMind Pro — RAG-система для работы с учебными материалами.  
Преподаватель загружает документы, а студенты задают вопросы и получают ответы с цитатами из источников.

## Возможности

- загрузка PDF, DOCX, TXT, EPUB, FB2, HTML и Markdown;
- автоматическая индексация документов;
- поиск по смыслу через BGE-M3;
- реранжирование найденных фрагментов;
- ответы с цитатами;
- фильтрация по файлу и разделу;
- работа через OpenRouter API или локально через Ollama;
- веб-интерфейс на Gradio.

## Архитектура

Пользовательский вопрос проходит несколько этапов:

1. HyDE-переформулировка запроса;
2. преобразование запроса в эмбеддинг;
3. поиск релевантных фрагментов в ChromaDB;
4. реранжирование через cross-encoder;
5. генерация ответа через LLM.

## Стек

- Python
- Gradio
- ChromaDB
- Sentence-Transformers
- BGE-M3
- BGE-Reranker-v2-m3
- Qwen3
- Ollama
- OpenRouter

## Режимы работы

BonchMind Pro поддерживает два режима работы языковой модели.

### API-режим

В этом режиме ответы генерируются через OpenRouter API.

Файл `.env`:

```env
LLM_MODE=api
API_KEY=your_openrouter_api_key_here
API_MODEL=qwen/qwen3-32b
```

Преимущества:

- выше качество ответов;
- не требуется мощный компьютер;
- быстрее запуск.

Недостатки:

- нужен интернет;
- нужен API-ключ;
- данные отправляются во внешний сервис.

### Локальный режим через Ollama

В этом режиме модель запускается локально на компьютере.

Файл `.env`:

```env
LLM_MODE=ollama
OLLAMA_MODEL=qwen3:8b
```

Перед запуском нужно установить Ollama и скачать модель:

```bash
ollama pull qwen3:8b
```

Преимущества:

- можно работать без интернета;
- данные не отправляются во внешний сервис;
- подходит для локального развёртывания.

Недостатки:

- нужен более мощный компьютер;
- генерация может быть медленнее.

## Установка

Клонирование проекта:

```bash
git clone https://github.com/clapzy2/bonchmind-pro.git
cd bonchmind-pro
```

Создание виртуального окружения:

```bash
python -m venv .venv
```

Активация на Windows:

```bash
.venv\Scripts\activate
```

Активация на Linux / macOS:

```bash
source .venv/bin/activate
```

Установка зависимостей:

```bash
pip install -r requirements.txt
```

Создайте файл `.env` на основе `.env.example`.

Пример `.env` для API-режима:

```env
LLM_MODE=api
API_KEY=your_openrouter_api_key_here
API_MODEL=qwen/qwen3-32b
OLLAMA_MODEL=qwen3:8b
```

## Запуск

Основная точка входа:

```bash
python run.py
```

Альтернативный запуск:

```bash
python main.py
```

После запуска интерфейс откроется в браузере по адресу:

```text
http://127.0.0.1:7860
```

## Структура проекта

```text
bonchmind-pro/
├── src/
│   ├── knowledge_base.py
│   ├── llm_engine.py
│   └── __init__.py
├── docs/
├── data/
├── sample_docs/
├── screenshots/
├── config.py
├── ingest.py
├── main.py
├── run.py
├── requirements.txt
├── .env.example
└── README.md
```

## Roadmap

- [ ] генерация конспектов по файлу или разделу;
- [ ] генерация тестов и контрольных вопросов для преподавателя;
- [ ] режим подготовки учебных материалов;
- [ ] Docker;
- [ ] FastAPI backend;
- [ ] роли преподавателя и студента;
- [ ] Telegram-бот.