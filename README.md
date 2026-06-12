# BonchMind Pro

**BonchMind Pro** — это RAG-платформа для работы с учебными материалами.
Система позволяет загружать документы, индексировать их в базу знаний, искать информацию по смыслу, генерировать конспекты и задавать вопросы ассистенту с опорой на загруженные источники.

Проект развивается как продуктовая версия учебного AI-инструмента для работы с материалами, конспектами и вопросами по документам.

---

## Возможности

* Регистрация и вход пользователей.
* Личное рабочее пространство для каждого пользователя.
* Изоляция данных между пользователями.
* Загрузка учебных материалов.
* Индексация документов в ChromaDB.
* Семантический поиск по фрагментам документов.
* Генерация конспектов по теме, выбранному файлу или разделу.
* Assistant/Chat, который отвечает по загруженным материалам.
* Источники ответа: отображение файла и раздела, на которые опирался ответ.
* Проверка качества ответа и диагностика последнего запуска.
* Переиндексация и удаление материалов.
* Поддержка работы через OpenRouter API или локальную Ollama.

---

## Текущий статус

Основной интерфейс проекта — **Next.js frontend + FastAPI backend**.

Старый Gradio-интерфейс удалён в Stage 6, потому что он обходил авторизацию и работал через legacy `DEFAULT_WORKSPACE_ID`.
Теперь `workspace_id` всегда передаётся явно и берётся из авторизованного пользователя.

Актуальное состояние:

* Gradio удалён.
* `main.py` и `run.py` удалены.
* `DEFAULT_WORKSPACE_ID` удалён.
* Workspace isolation работает через auth/current user.
* Summary и Assistant используют workspace-aware поиск.
* Для коротких/plain-text материалов предусмотрен fallback: если semantic/lexical retrieval не находит фрагменты, Summary может использовать чанки выбранного файла напрямую.
* Старые runtime-ссылки на `main.py` удалены.

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
2. Загружает учебный материал во вкладке **Материалы**.
3. Дожидается завершения индексации.
4. Генерирует конспект во вкладке **Конспект**.
5. Задаёт вопросы по материалу во вкладке **Ассистент**.
6. Проверяет качество ответа и источники во вкладке **Проверка качества**.

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

## Проверка качества

Вкладка проверки качества показывает диагностику последнего запуска:

* стратегию;
* найденные фрагменты;
* LLM-вызовы;
* источники;
* статус выполнения;
* возможные слабые места ответа.

JSON export диагностики пока оставлен как follow-up.

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

На текущем этапе остаются known-gaps, которые не блокируют основную работу:

* загрузка нескольких файлов сразу;
* экспорт diagnostics trace в JSON через UI;
* полноценное содержимое вкладки Settings;
* отдельный admin diagnostics UI;
* light theme;
* production deployment через Docker.

---

## Roadmap

Ближайшие направления развития:

### Stage 7 — Product polish

* улучшение UX;
* более понятные ошибки;
* улучшение empty states;
* доработка Settings;
* улучшение Assistant/Summary UI;
* better loading states.

### Stage 8 — Production setup

* Docker / docker-compose;
* production env;
* инструкции деплоя;
* подготовка PostgreSQL;
* стабильная структура runtime-данных.

### Stage 9 — Security / Admin

* admin diagnostics UI;
* роли пользователей;
* ограничения доступа;
* rate limits;
* аудит cookie/auth flow.

### Stage 10 — Documentation / Presentation

* финальная документация;
* демонстрационный сценарий;
* описание архитектуры;
* подготовка проекта для защиты, портфолио или заказчика.

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
