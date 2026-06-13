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

Полная диагностика доступна суперпользователю в разделе **«Админ»** (Stage 9b) — см. [Администрирование](#администрирование).

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

**Изоляция и auth:**

* пользовательские данные разделены по workspace; `workspace_id` всегда из авторизации, а не из запроса;
* пароли хешируются bcrypt; JWT хранится в HttpOnly-cookie (`SameSite=Lax`), в браузерном storage токена нет;
* отсутствие `workspace_id` в KB/Summary API — ошибка на уровне Python, а не тихий fallback;
* удаление материала убирает файл, чанки ChromaDB и строку БД, всё в рамках workspace.

**Hardening (Stage 9a):**

* **rate limiting** (превышение → `429`): авторизованные ручки (`/api/chat`, `/api/materials/upload`) ключуются **по пользователю** (Stage 13 — один студент за общим NAT/IP вуза не душит остальных), а `/api/auth/login` / `/register` — **по IP** (анти-брутфорс, юзера ещё нет);
* **защита от upload-DoS**: ранняя проверка `Content-Length` + потоковое чтение с лимитом → файл больше `MAX_UPLOAD_BYTES` получает `413`, не читаясь целиком в память;
* **login timing**: для несуществующего email всё равно выполняется bcrypt-verify (нет таймингового определения существования аккаунта);
* **audit-log** (`audit_events`) важных действий: `login`, `upload`, `delete`, `reindex`, `reconcile`, `promote`/`demote`/`ban`/`unban`;
* **бан рубит живую сессию** (Stage 13): `get_current_user` отклоняет `is_active=false`, поэтому деактивация действует сразу на уже выданный JWT, а не только при следующем логине;
* `/api/diagnostics/*` и `/api/admin/*` (audit-лог, статистика, управление пользователями) — только для superuser;
* `AUTH_COOKIE_SECURE=true` обязателен в prod за HTTPS (backend предупреждает в логах, если на Postgres-развёртывании он `false`).

**Отложено (future):** per-workspace роли teacher/student/viewer и общие workspace (Stage 14 — B2B), отзыв/refresh JWT, CSRF-токен (сейчас прикрыто `SameSite=Lax`), проверка email, SSO.

---

## Администрирование

Раздел **«Админ»** (Stage 9b) виден только суперпользователю: обычный пользователь не видит его в сайдбаре, а прямые запросы к `/api/admin/*` получают `403`. Внутри:

* **статистика инстанса** — число пользователей, workspace, документов и событий аудита;
* **журнал аудита** — последние события `login` / `upload` / `delete` / `reindex` / `reconcile` (время, действие, пользователь, объект, IP);
* **диагностика** — сырой trace последнего запуска (раскрывающийся блок);
* **«Сверить базу»** (Stage 9c): сверяет векторную базу (ChromaDB) с таблицей `Document` и удаляет осиротевшие фрагменты — те, у которых больше нет материала в библиотеке (`POST /api/admin/reconcile`). Идемпотентно, по всем workspace, строго в их границах. Чинит рассинхрон вида «в Библиотеке 0 материалов, а в индексе ещё что-то лежит» (после сбоя best-effort удаления или сброса dev-БД поверх сохранённого Chroma-стора);
* **«Пользователи»** (Stage 13): таблица всех пользователей + управление — выдать/снять права админа (`promote`/`demote`) и заблокировать/разблокировать (`ban`/`unban`). Действовать можно только над **другими**: строка самого себя выключена (нельзя выстрелить себе в ногу), и нельзя забанить/разжаловать **последнего активного суперпользователя** (система не останется без админа). Бан действует немедленно — живая сессия рубится на следующем запросе.

### Назначение первого суперпользователя

Дальше админов можно назначать прямо из раздела «Пользователи» (Stage 13). Но **самого первого** суперпользователя сделать неоткуда — публичного API для этого нет намеренно, поэтому его выставляют напрямую в БД (`users.is_superuser = true`).

Сначала зарегистрируйте обычный аккаунт через UI (`/register`), затем повысьте его:

**Локально (любая БД — SQLite или Postgres):**

```powershell
python -c "from src.db import SessionLocal; from src.db_models import User; s=SessionLocal(); u=s.query(User).filter(User.email=='you@example.com').one(); u.is_superuser=True; s.commit(); print('promoted:', u.email)"
```

**В Docker:**

```powershell
docker compose exec api python -c "from src.db import SessionLocal; from src.db_models import User; s=SessionLocal(); u=s.query(User).filter(User.email=='you@example.com').one(); u.is_superuser=True; s.commit(); print('promoted:', u.email)"
```

После повторного входа (или обновления страницы) в сайдбаре появится пункт **«Админ»**. Понизить обратно — тот же сниппет с `is_superuser=False`.

---

## Тарифы и лимиты

Stage 12 закладывает фундамент монетизации: персональный план у пользователя + квоты + метеринг. Полная B2B-архитектура (кафедра → преподаватели → курсы → студенты) спроектирована в [`design/monetization-and-b2b.md`](design/monetization-and-b2b.md) и будет добавляться аддитивно.

**Планы** (поле `User.plan`):

| План | Материалы | Вопросы/день | Конспекты/день |
|------|-----------|--------------|----------------|
| `free` | 3 | 15 | 3 |
| `pro` | 50 | 200 | 50 |

Числа стартовые и env-overridable (`PLAN_FREE_MAX_MATERIALS`, `PLAN_PRO_CHAT_PER_DAY`, … — см. `config.PLAN_LIMITS`), чтобы крутить без миграций.

* **Квоты** считаются через `src/billing.get_billing_context()` по «субъекту биллинга» (сейчас — пользователь, потом — организация). Превышение → `402` с payload `{error:"quota_exceeded", action, limit, used, plan}`; фронт показывает «лимит исчерпан, обновите тариф». `chat` / `summary` — дневной лимит (сброс в полночь UTC); `upload` — общий лимит материалов (проверяется до чтения файла и индексации).
* **Метеринг**: каждое успешное действие пишет строку `usage_events` (`action`, `units`, `billing_subject_*`, `meta`) — для квот и будущего расчёта себестоимости.
* **Использование** видно в правой панели («Тариф и лимиты»); `GET /api/billing/me` отдаёт план + used/limit.
* Отключить энфорсмент целиком: `QUOTAS_ENABLED=false` (так делает тест-сьют).

### Сменить тариф пользователя

Биллинг-платёжки пока нет (отдельный будущий стейдж). Поднять/понизить план — напрямую в БД (как с суперпользователем):

```powershell
python -c "from src.db import SessionLocal; from src.db_models import User; s=SessionLocal(); u=s.query(User).filter(User.email=='you@example.com').one(); u.plan='pro'; s.commit(); print('plan:', u.email, u.plan)"
```

---

## Известные ограничения

Осознанно отложенные known-gaps, которые не блокируют основную работу:

* per-workspace роли (teacher/student/viewer) и общие workspace — это B2B-слой (Stage 14); promote/demote/бан на уровне платформы уже есть (Stage 13);
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
* **Stage 9 — Security / Admin:** rate limits, audit-лог, anti-enumeration, upload-DoS guard (9a); superuser-экран «Админ» — статистика, журнал аудита, диагностика (9b); орфан-скраббер — сверка ChromaDB ↔ `Document`, кнопка «Сверить базу» (9c).
* **Stage 10 — Documentation:** ARCHITECTURE.md, DEMO.md, финальный README.
* **Stage 11 — Мультизагрузка:** загрузка нескольких файлов сразу (выбор + drag-and-drop), последовательная очередь на фронте через существующий endpoint, прогресс «Файл i из N», отмена очереди.
* **Stage 12 — Тарифы/квоты/метеринг:** `User.plan` (free/pro), лимиты + квоты (chat/summary/upload → `402`), `usage_events` ledger, `get_billing_context` (форвард-совместимо с org), usage-панель + paywall. Фундамент монетизации.
* **Stage 13 — Multi-tenant security & admin foundation:** per-user rate-limit (NAT-фикс для вузов), бан рубит живую сессию, superuser-управление пользователями (promote/demote + ban/unban с self- и last-superuser-guard). См. [`design/multi-tenant-security.md`](design/multi-tenant-security.md).

### Дальше

* **Stage 14 — B2B foundation** (по [`design/multi-tenant-security.md`](design/multi-tenant-security.md) + [`design/monetization-and-b2b.md`](design/monetization-and-b2b.md)): `Organization`/`OrganizationMember`, `Workspace.organization_id`, роли teacher/student/viewer + `can(user, action, workspace)`, курсы, invite по коду, выбор активного workspace, per-org изоляция (кафедра → преподаватели → курсы → студенты).
* **Stage 15 — Billing:** платёжка (ЮKassa / Stripe) + вебхуки.
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
