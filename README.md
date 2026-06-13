# BonchMind Pro

**BonchMind Pro** — это RAG-платформа для работы с учебными материалами.
Система позволяет загружать документы, индексировать их в базу знаний, искать информацию по смыслу, генерировать конспекты и задавать вопросы ассистенту с опорой на загруженные источники.

Проект развивается как продуктовая версия учебного AI-инструмента для работы с материалами, конспектами и вопросами по документам.

> **Кратко (для портфолио / защиты):** полноценная multi-user RAG-платформа на Next.js + FastAPI + PostgreSQL + ChromaDB + BGE-моделях, с авторизацией, изоляцией данных по пользователям и упаковкой в Docker. Пользователь загружает учебные документы в личное пространство, получает по ним конспекты с опорой на источники и задаёт вопросы ассистенту.

📐 Архитектура — [ARCHITECTURE.md](ARCHITECTURE.md) · 🎬 Демо-сценарий — [DEMO.md](DEMO.md)

---

## Скриншоты

Скриншоты интерфейса будут добавлены **отдельным follow-up PR** после финального smoke. Список нужных кадров (shot-list с именами файлов) — в [`screenshots/README.md`](screenshots/README.md).

---

## Возможности

* Регистрация и вход пользователей (JWT в HttpOnly-cookie).
* Личное рабочее пространство для каждого пользователя.
* Изоляция данных между пользователями.
* Загрузка учебных материалов — в том числе прямо из экранов Конспекта и Ассистента (скрепка).
* Индексация документов в ChromaDB, переиндексация и удаление.
* Семантический поиск по фрагментам + reranking (cross-encoder).
* Генерация конспектов по теме / файлу / разделу, проверка покрытия источниками, экспорт в `.docx`.
* Ассистент, отвечающий по загруженным материалам с опорой на найденные фрагменты.
* Markdown-рендеринг ответов и конспектов.
* Работа через OpenRouter API или локальную Ollama.
* Production-запуск в Docker на PostgreSQL.

---

## Текущий статус

Единственный интерфейс проекта — **Next.js frontend + FastAPI backend**. Старый Gradio-UI удалён (Stage 6), `workspace_id` всегда берётся из авторизованного пользователя.

Что сделано к текущему моменту:

* **Multi-user ядро** (Stage 1–6): авторизация, личные workspace, изоляция данных, удаление Gradio и legacy `DEFAULT_WORKSPACE_ID`.
* **Product polish** (Stage 7): Assistant-first интерфейс, упрощённые экраны, inline-загрузка файлов, Markdown-рендеринг, сохранение результата при F5.
* **Production setup** (Stage 8): Docker / docker-compose, PostgreSQL, миграции в Docker-flow, тома для данных.
* **Документация** (Stage 10): [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DEMO.md`](DEMO.md), финальный README.

Для коротких/plain-text материалов есть fallback: если semantic/lexical retrieval не находит фрагменты, Summary использует чанки выбранного файла напрямую (чтобы не показывать «не найдено», когда материал реально проиндексирован).

---

## Архитектура

Общая схема работы:

```text
User
  ↓
Next.js Frontend
  ↓
FastAPI Backend
  ↓
Auth / Workspace
  ↓
Document Service
  ↓
KnowledgeBase / ChromaDB
  ↓
Embeddings / Reranker
  ↓
LLM
  ↓
Answer / Summary / Sources
```

Основные части проекта:

* **Frontend:** Next.js, React, TypeScript.
* **Backend:** FastAPI.
* **Database:** SQLAlchemy + Alembic.
* **Vector storage:** ChromaDB.
* **Embeddings:** BGE-M3.
* **Reranker:** BGE reranker.
* **LLM:** OpenRouter API или Ollama.
* **Tests:** pytest.
* **CI:** backend tests + frontend typecheck/lint.

Подробная архитектура (компоненты, поток запроса, модель данных, изоляция) — в [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Технологический стек

### Backend

* Python
* FastAPI
* SQLAlchemy
* Alembic
* ChromaDB
* sentence-transformers
* BAAI/bge-m3
* BAAI/bge-reranker-v2-m3
* OpenRouter / Ollama
* pytest

### Frontend

* Next.js
* React
* TypeScript
* Tailwind CSS
* ESLint
* TypeScript typecheck

---

## Структура проекта

```text
bonchmind-pro/
├── api_app.py                    # FastAPI-приложение
├── run_api.py                    # запуск backend API
├── config.py                     # конфигурация проекта
├── requirements.txt              # Python-зависимости
├── alembic.ini                   # настройки миграций
├── src/                          # backend-логика
│   ├── app_services.py           # сервисный слой API
│   ├── auth_*.py                 # авторизация
│   ├── document_service.py       # работа с Document table
│   ├── knowledge_base.py         # ChromaDB / поиск / индексация
│   ├── summary_engine.py         # генерация конспектов
│   ├── llm_engine.py             # работа с LLM
│   └── diagnostics.py            # диагностика и trace
├── frontend/                     # Next.js frontend
│   ├── src/app/                  # страницы приложения
│   ├── src/components/           # UI-компоненты
│   └── src/lib/                  # frontend API/auth helpers
├── tests/                        # backend-тесты
├── design/                       # архитектурные документы
├── docs/                         # загружаемые пользовательские материалы
├── data/                         # SQLite/ChromaDB runtime-данные
└── eval/                         # dev/eval-скрипты
```

---

## Быстрый запуск

### 1. Клонирование проекта

```powershell
git clone https://github.com/clapzy2/bonchmind-pro.git
cd bonchmind-pro
```

### 2. Backend

Создать и активировать виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Установить зависимости:

```powershell
pip install -r requirements.txt
```

Применить миграции:

```powershell
python -m alembic upgrade head
```

Запустить FastAPI backend:

```powershell
python run_api.py
```

Backend будет доступен по адресу:

```text
http://127.0.0.1:8000
```

---

### 3. Frontend

В отдельном терминале:

```powershell
cd frontend
npm install
npm run dev
```

Frontend будет доступен по адресу:

```text
http://127.0.0.1:3000
```

Локальный dev-режим работает на SQLite и не требует Docker.

---

## Запуск через Docker (production-style)

Запуск, приближенный к продакшену — Postgres + backend + frontend в контейнерах через `docker-compose`.

### 1. Подготовить `.env`

```powershell
copy .env.example .env
```

Обязательно заполнить:

* `JWT_SECRET_KEY` — секрет (без него compose не стартует):

  ```powershell
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
* `API_KEY` — ключ OpenRouter (при `LLM_MODE=api`);
* `POSTGRES_PASSWORD` — пароль БД для любого реального развёртывания.

### 2. Поднять стек

```powershell
docker compose up --build
```

Что произойдёт:

1. Поднимается `db` (Postgres) и проходит healthcheck.
2. `backend` дожидается healthy-БД, применяет миграции (`alembic upgrade head`) и стартует API на `0.0.0.0:8000` внутри сети.
3. `frontend` (Next.js standalone) поднимается на порту `3000` и проксирует `/api/*` на `backend`.

Открыть: `http://localhost:3000`

> Первый старт backend медленный — скачиваются модели BGE-M3 и reranker (~2 ГБ) в том `models`. Дальше кэш переиспользуется.

### Тома (данные переживают перезапуск)

| Том | Что хранит |
|-----|------------|
| `pgdata` | Postgres: пользователи, workspace, документы |
| `data` | ChromaDB-векторы (файловые) |
| `docs` | загруженные материалы |
| `models` | кэш моделей BGE-M3 / reranker |

ChromaDB остаётся файловой и живёт в томе `data`; Postgres заменяет только реляционную БД. Перенос векторов в pgvector в Stage 8 не входит.

### Остановить

```powershell
docker compose down            # остановить, тома сохранить
docker compose down -v         # остановить и удалить тома (полный сброс)
```

---

## Настройка `.env`

Проект поддерживает два режима работы LLM:

* `api` — использование внешнего API, например OpenRouter;
* `ollama` — использование локальной Ollama.

Пример `.env`:

```env
LLM_MODE=api

API_KEY=your_api_key_here
API_MODEL=qwen/qwen3-32b
API_URL=https://openrouter.ai/api/v1/chat/completions

OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen2.5:7b
```

Для локальной Ollama нужно отдельно запустить Ollama и убедиться, что она доступна на порту `11434`.

---

## Работа с пользователями и workspace

В проекте каждый пользователь получает своё личное рабочее пространство.

Это значит:

* материалы Alice не видны Bob;
* материалы Bob не видны Alice;
* поиск, конспекты и чат работают только внутри workspace текущего пользователя;
* `workspace_id` больше не подставляется неявно;
* legacy `DEFAULT_WORKSPACE_ID` удалён.

Workspace определяется backend'ом на основе текущего авторизованного пользователя.

---

## Основной пользовательский сценарий

1. Пользователь регистрируется или входит в аккаунт.
2. Загружает учебный материал во вкладке **Библиотека** (или прямо из Конспекта/Ассистента через скрепку).
3. Дожидается завершения индексации (статус «Готов»).
4. Генерирует конспект во вкладке **Конспект**, при желании проверяет источники и экспортирует в DOCX.
5. Задаёт вопросы по материалу во вкладке **Ассистент**.

Подробный пошаговый показ — в [DEMO.md](DEMO.md).

---

## Материалы и индексация

Материалы загружаются через frontend и сохраняются в workspace пользователя.

После загрузки backend:

1. создаёт запись в `Document` table;
2. сохраняет файл;
3. индексирует документ;
4. добавляет чанки в ChromaDB;
5. сохраняет metadata:

   * `workspace_id`;
   * `document_id`;
   * `source_file`;
   * `section`;
   * `chunk_id`.

Если материал короткий или не имеет явных разделов, он всё равно может быть пригоден для поиска, чата и конспектов.

---

## Summary / Конспект

Модуль конспектов поддерживает несколько сценариев:

* конспект по выбранному файлу;
* конспект по выбранному разделу;
* конспект по теме;
* краткий, средний и подробный формат.

Summary использует workspace-aware поиск и не выходит за пределы материалов текущего пользователя.

Для коротких и plain-text документов предусмотрен fallback: если semantic search и lexical scoring не нашли кандидатов, но выбранный файл существует и содержит чанки, Summary может использовать чанки выбранного файла напрямую. Это защищает от ситуации, когда Assistant видит материал, а Summary ошибочно показывает “Информация не найдена”.

---

## Assistant / Chat

Assistant отвечает на вопросы по загруженным материалам.

Он использует:

* semantic search;
* reranking;
* историю последних сообщений;
* источники из ChromaDB;
* workspace isolation.

Ответ сопровождается источниками, если они были найдены.

---

## Качество и источники

Отдельная вкладка «Проверка качества» убрана в Stage 7 — диагностика для рядового пользователя избыточна. Вместо неё:

* после генерации конспекта показываются чипы: стратегия, число фрагментов, LLM-вызовы, время;
* кнопка **«Проверить источники»** раскрывает покрытие — какие разделы/фрагменты поддержали каждый пункт.

Полная диагностика (логика сохранена в `frontend/src/components/run-diagnostics.tsx`) вернётся в Stage 9 под admin-доступ.

---

## Проверки проекта

### Backend tests

```powershell
pytest tests/ -q
```

### Frontend typecheck

```powershell
cd frontend
npm run typecheck
```

### Frontend lint

```powershell
cd frontend
npm run lint
```

Перед merge в main проект должен проходить:

```text
pytest tests/ -q
npm run typecheck
npm run lint
CI green
```

---

## CI

В проекте используется GitHub Actions.

CI проверяет:

* backend tests;
* frontend typecheck;
* frontend lint.

PR не должен попадать в main, если CI красный.

---

## Безопасность

Важные принципы:

* пользовательские данные разделены по workspace;
* backend получает `workspace_id` из авторизации;
* frontend не выбирает workspace вручную;
* старый Gradio UI удалён;
* `DEFAULT_WORKSPACE_ID` удалён;
* прямые runtime-вызовы без workspace больше не допускаются;
* отсутствие `workspace_id` в KB/Summary API должно приводить к ошибке на уровне Python, а не к тихому fallback.

---

## Известные ограничения

Осознанно отложенные known-gaps, которые не блокируют основную работу:

* загрузка нескольких файлов сразу;
* admin diagnostics UI и роли пользователей;
* мобильная адаптация (сейчас базовая CSS-деградация, без mobile-first);
* английский язык интерфейса (UI только на русском, без i18n);
* light theme;
* перенос векторов в pgvector (ChromaDB остаётся файловой).

---

## Roadmap

### ✅ Сделано

* **Stage 1–6 — Multi-user ядро:** auth, workspace, изоляция, удаление Gradio/`DEFAULT_WORKSPACE_ID`.
* **Stage 7 — Product polish:** Assistant-first, чистка экранов, inline upload, Markdown, F5-persist.
* **Stage 8 — Production setup:** Docker / docker-compose, PostgreSQL, миграции в Docker, тома.
* **Stage 10 — Documentation:** ARCHITECTURE.md, DEMO.md, финальный README.

### Дальше

* **Stage 9 — Security / Admin:** роли пользователей, admin diagnostics UI (логика уже сохранена в `run-diagnostics.tsx`), rate limits, аудит auth-flow.
* **Responsive polish:** mobile-first вёрстка, гамбургер-меню, тач-оптимизация.
* **i18n:** английский интерфейс (next-intl).
* **pgvector:** перенос векторного хранилища в PostgreSQL.

---

## Статус Gradio

Gradio больше не используется.

Удалено:

```text
main.py
run.py
gradio dependency
DEFAULT_WORKSPACE_ID
legacy Gradio bridge
```

Причина удаления: Gradio обходил авторизацию и workspace isolation, поэтому не соответствовал текущей multi-user архитектуре проекта.

---

## License

Проект находится в активной разработке.
Лицензия может быть уточнена позже.
