# BonchMind Pro — дизайн мультипользовательской архитектуры (Track B)

Статус: **черновик на согласование**. Кода по этому документу ещё нет — только план.
Цель: понять, как превратить текущее однопользовательское приложение (один общий
`docs/`, одна коллекция ChromaDB, без авторизации) в публичный сервис с
изолированными библиотеками пользователей, не сломав существующий RAG-пайплайн.

Контекст из текущего кода (важно для всех решений ниже):

- `config.DOCS_DIR` — единая папка `docs/`, индексируются только файлы верхнего
  уровня (`KnowledgeBase._iter_library_files` / `_is_library_file_path`).
- `KnowledgeBase` — один объект на процесс (`src/runtime.py`, singleton `_kb`),
  одна коллекция ChromaDB `textbot_docs` в `data/chromadb`.
- Метаданные чанка сейчас: `source_file` (basename), `source` (абсолютный путь),
  `section`, `chunk_id`. ID чанка = `md5(текст_чанка_с_контекстом_раздела)`,
  **дедупликация идёт по всей коллекции глобально** (`existing_ids = set(self._col.get()["ids"])`).
- `remove_book(file_name)` удаляет по `where={"source_file": target_name}` —
  то есть по basename, без привязки к владельцу.
- Прогресс операций (`_material_progress_state`) и блокировка
  (`_material_job_lock`) — **глобальные на процесс**, одновременно может идти
  только одна операция с библиотекой на весь сервер.
- API (`api_app.py`) полностью без авторизации, без понятия "пользователь" /
  "workspace". Все материалы видны всем.

Документ ниже отвечает на 14 пунктов из задания.

---

## 1. Модель пользователей

Минимальная сущность `User`:

| поле | тип | комментарий |
|---|---|---|
| `id` | UUID/int PK | первичный ключ |
| `email` | str, unique | логин |
| `password_hash` | str | bcrypt/argon2 |
| `display_name` | str | для UI |
| `is_active` | bool | бан/деактивация |
| `is_superuser` | bool | админ-доступ (поддержка, диагностика) |
| `created_at`, `updated_at` | datetime | |

На первом этапе **email подтверждать не обязательно** (можно включить позже —
поле `email_verified_at` зарезервировать сразу, чтобы не мигрировать таблицу
дважды).

Хранение: лёгкая SQL-БД (см. п.4) — отдельно от ChromaDB. ChromaDB остаётся
только хранилищем векторов/чанков, источник правды по пользователям/доступам —
SQL.

## 2. Модель workspace/project

Вводим сущность `Workspace` как единицу изоляции данных (документы, индекс,
лимиты). Делать сразу 1:1 "user = workspace" **не нужно** — лучше сразу завести
отдельную таблицу `Workspace` + `Membership`, но **на первом этапе
использовать политику "1 пользователь = 1 личный workspace, создаётся
автоматически при регистрации"**. Это даёт:

- единый ключ изоляции (`workspace_id`) во всех местах с первого дня;
- путь к команде/шарингу в будущем без переписывания схемы данных и API —
  просто добавляется возможность пригласить второго участника в существующий
  workspace.

Таблицы:

```
Workspace
  id, name, owner_user_id, plan ("free"/...), created_at

WorkspaceMember
  id, workspace_id, user_id, role ("owner"/"member"/"viewer"), created_at

Document
  id, workspace_id, owner_user_id, original_name, stored_path,
  size_bytes, content_hash, status ("processing"/"ready"/"error"/"hidden"),
  sections_count, error_message, created_at, updated_at
```

`Document` — это та самая "запись о материале", параллельная текущему
`MaterialInfo`. ChromaDB хранит только чанки и ссылается на `document_id`.

## 3. Роли и права доступа

Для первого этапа достаточно двух ролей внутри workspace:

- **owner** — может всё: загружать/удалять/переиндексировать документы,
  управлять составом workspace (когда появится шаринг), смотреть лимиты.
- **member** — может загружать/удалять свои документы, использовать
  чат/конспекты по всем документам workspace.

(`viewer` — зарезервировать в enum, не реализовывать UI/проверки до тех пор,
пока не появится реальный сценарий шаринга.)

Поскольку на первом этапе workspace == 1 пользователь, проверка прав
вырождается в "владелец workspace == текущий пользователь" — но код пишем
сразу через `require_workspace_role(user, workspace, min_role)`, чтобы не
переписывать middleware при появлении совместных workspace.

Отдельно — **superuser/admin** (на уровне `User.is_superuser`) для
служебных нужд: просмотр диагностики, лимитов, ручная поддержка пользователей.
Не выводить в публичный UI на первом этапе.

## 4. Авторизация: минимальный вариант на первом этапе

Рекомендация: **email + пароль + JWT**, без внешних провайдеров.

- Хранение пароля: `passlib[bcrypt]` (или `argon2-cffi`).
- Токены: `python-jose` / `pyjwt`, короткоживущий access-token (15-60 мин) +
  refresh-token (хранится в httpOnly cookie). Для первого этапа можно
  упростить до одного access-токена с TTL ~7 дней в httpOnly cookie — refresh
  добавить, когда появится реальная нагрузка.
- Эндпоинты: `POST /api/auth/register`, `POST /api/auth/login`,
  `POST /api/auth/logout`, `GET /api/auth/me`.
- Подтверждение email — не делаем на первом этапе (см. п.1), но поле в БД
  предусмотреть.
- Зависимость FastAPI `get_current_user` — читает токен из cookie/заголовка,
  достаёт `User`, кладёт в `request.state`. Все эндпоинты материалов/чата/
  конспектов становятся `Depends(get_current_user)` + `Depends(get_current_workspace)`.

Почему не сторонний провайдер (Clerk/Auth0/Supabase Auth/Firebase Auth) —
рассматривался, но:
- добавляет внешнюю зависимость и ещё один аккаунт/биллинг до того, как понятен
  спрос;
- self-hosted email+password+JWT — это ~150-250 строк кода, хорошо тестируется,
  не требует email-инфраструктуры на старте.

Если позже понадобится "вход через Google" — это добавляется как ещё один
способ входа в ту же таблицу `User` (поле `auth_provider`/`provider_id`),
архитектура не меняется.

**Что не делаем на первом этапе**: восстановление пароля по email (требует
SMTP), 2FA, OAuth. Зарезервировать поля, но не реализовывать.

## 5. Структура хранения файлов

```
docs/
  <workspace_id>/
    <document_id>__<original_filename>
```

Почему `<document_id>__<original_filename>`, а не просто `<original_filename>`:

- две загрузки с одинаковым именем файла в одном workspace не должны
  конфликтовать на диске;
- `document_id` даёт прямой и однозначный ключ для удаления/переиндексации
  без полагания на basename;
- `original_filename` сохраняется в имени для удобства ручной диагностики на
  диске (плюс хранится отдельно в `Document.original_name` для UI).

`KnowledgeBase._is_library_file_path` нужно обновить: вместо "файл верхнего
уровня docs/" — "файл вида `docs/<workspace_id>/<document_id>__*`, где
`<workspace_id>` — валидный UUID-каталог". Обходы директорий (`..`, абсолютные
пути) проверять так же строго, как сейчас, плюс не пускать в индекс ничего вне
`docs/<workspace_id>/...` (актуально из-за `<document_id>__<original_filename>`,
где `original_filename` приходит от пользователя — санитизировать перед
конкатенацией: убрать `/`, `\`, `..`, ограничить длину).

## 6. Метаданные в ChromaDB

Текущие поля чанка: `source_file`, `source`, `section`, `chunk_id`.
Новые/изменённые поля:

| поле | смысл |
|---|---|
| `workspace_id` | **обязательный**, ключ изоляции для поиска |
| `document_id` | UUID документа (из таблицы `Document`), используется для удаления |
| `user_id` | кто загрузил (для аудита/будущей атрибуции в team workspace) |
| `source_file` | имя файла **для отображения** (как сейчас, `original_name`) |
| `source_path` | относительный путь `docs/<workspace_id>/<document_id>__name.ext` (вместо абсолютного `source`) |
| `section` | без изменений |
| `chunk_id` | без изменений |

Дополнительно: **ID чанка в ChromaDB должен включать `workspace_id`/`document_id`**,
а не быть `md5(chunk_text)` глобально. Иначе:

- если два пользователя загрузят один и тот же учебник, у вторых чанки будут
  иметь те же md5-id, что и у первых → `existing_ids` посчитает их дублями и
  **не добавит чанки второго пользователя** (тихая потеря данных — серьёзный баг
  при переходе на multi-tenant).

Новый ID: `md5(f"{workspace_id}:{document_id}:{chunk_text_with_section}")`.
Дедупликация (`existing_ids`) при индексации одного документа должна
проверяться **в рамках `document_id`**, а не по всей коллекции (см. п.10 —
это требует переиндексации существующих данных).

## 7. Фильтрация поиска по пользователю/workspace

Все методы `KnowledgeBase`, которые сейчас принимают `file_filter`/`section_filter`
(`search_with_sources`, `search_chunks_for_summary`, `get_file_chunks`,
`get_available_sections`, `get_sections_for_file`, `get_available_files`,
`stats`, `get_file_profile`, `remove_book`) должны **обязательно** принимать
`workspace_id` и подмешивать его в `where`.

`_build_where_filter` меняется на:

```python
def _build_where_filter(self, workspace_id, file_filter="all", section_filter=None):
    conditions = [{"workspace_id": workspace_id}]
    if file_filter and file_filter != "all":
        conditions.append({"document_id": file_filter})  # или source_file, см. ниже
    if section_filter:
        conditions.append({"section": section_filter})
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}
```

Принцип "defense in depth": **ни один вызов `self._col.query(...)` или
`self._col.get(...)` не должен выполняться без `where`, содержащего
`workspace_id`** — даже методы вроде `_raw_search`, `_lexical_candidates_for_summary`,
`get_available_files`, которые сейчас при `kw_filter=None`/без `where` читают
**всю коллекцию**. Это главный риск утечки чужих документов между
пользователями, поэтому стоит:

1. сделать `workspace_id` обязательным позиционным аргументом в публичных
   методах `KnowledgeBase` (а не опциональным с default), чтобы случайный вызов
   без него падал на этапе разработки/тестов, а не в проде;
2. добавить unit/integration тест "пользователь A не видит чанки workspace B"
   как часть приёмки этого трека.

## 8. Удаление документа (файл + чанки)

Сейчас `remove_book(file_name)` ищет по `source_file` (basename) — двусмысленно
в multi-tenant (разные workspace могут иметь файлы с одинаковым именем).

Новый поток `delete_document(workspace_id, document_id)`:

1. Проверить, что `Document(id=document_id, workspace_id=workspace_id)`
   существует и принадлежит workspace текущего пользователя (404/403 иначе).
2. `kb.remove_chunks(workspace_id=..., document_id=...)` →
   `self._col.delete(where={"$and": [{"workspace_id": ws}, {"document_id": doc_id}]})`.
3. Удалить файл по `Document.stored_path` (`docs/<workspace_id>/<document_id>__*`).
4. Удалить (или пометить `status="deleted"`) строку в таблице `Document`.
5. Всё в одной "транзакции" в широком смысле — порядок важен: сначала Chroma,
   потом файл, потом запись в БД, чтобы при сбое на полпути материал не исчез
   "наполовину" из выдачи, а остался виден с ошибкой и его можно было повторно
   удалить (идемпотентность операции — если файла/чанков уже нет, не падать).

## 9. Что делать со старой общей базой `docs/`

Сейчас в `docs/` (трекается в git, несмотря на `.gitignore`, видимо
осознанно) лежат демонстрационные файлы: `Krasnov...pdf`, `The_Little_Match_Girl.txt`,
`pir.txt`. Плюс у текущих локальных/демо-инсталляций может быть реальный
проиндексированный контент в `data/chromadb`.

Решение:

- Демонстрационные файлы из `docs/` переносим в `sample_docs/` (уже существует,
  есть `README.md`) как "образцы для онбординга". Они **не индексируются по
  умолчанию** — опционально предлагаются новому пользователю кнопкой
  "Загрузить пример материала" (копирует файл из `sample_docs/` в его
  `docs/<workspace_id>/...` и индексирует как обычный документ).
- Текущее содержимое `docs/*` (топ-уровень) и существующий индекс в
  `data/chromadb` рассматриваются как **legacy-данные единственного текущего
  пользователя** и переносятся в специальный `default`/`legacy` workspace,
  привязанный к первому созданному `User` (см. миграцию, п.10).
- После миграции `config.DOCS_DIR` верхнего уровня для новых данных не
  используется — структура строго `docs/<workspace_id>/...`. `docs/.gitkeep`
  можно оставить для совместимости с `.gitignore`-исключением, но новый код
  туда не пишет.

## 10. Нужна ли миграция или полная переиндексация

И то, и другое, но в разных объёмах:

- **Метаданные существующих чанков** (`workspace_id`, `document_id`, `user_id`,
  `source_path`) можно проставить **без переэмбеддинга** через
  `collection.update(ids=[...], metadatas=[...])` — ChromaDB поддерживает
  обновление метаданных без пересчёта эмбеддингов. Создаём один `legacy`
  workspace, один `Document` на каждый существующий `source_file`, проставляем
  всем его чанкам соответствующие `workspace_id`/`document_id`.
- **Полная переиндексация (с новыми ID чанков)** нужна, потому что текущий
  ID = `md5(текст_чанка)` без `workspace_id`/`document_id` — после миграции
  старые ID останутся "глобальными" и могут конфликтовать с новыми чанками
  других workspace, у которых тот же текст (см. п.6). Варианты:
  - (а) при миграции **пересчитать ID** для legacy-чанков по новой схеме —
    `collection.delete` старых id + `collection.add` тех же эмбеддингов/документов
    под новыми id (эмбеддинги можно переиспользовать через `collection.get(include=["embeddings", ...])`,
    переэмбеддинг не нужен);
  - (б) либо просто прогнать `index_all_books`-эквивалент по legacy-workspace
    заново (полный переэмбеддинг — дороже по времени, но проще по коду).

  Рекомендация: (а) — дешевле по CPU/времени, требует только скрипта
  миграции, не модели эмбеддингов.

- Файлы: переместить `docs/*.{ext}` (топ-уровень) в
  `docs/<legacy_workspace_id>/<document_id>__<filename>` с обновлением
  `Document.stored_path` и метаданных `source_path`.

Это разовый офлайн-скрипт (`scripts/migrate_to_workspaces.py`), запускается
один раз при деплое новой версии, идемпотентен (повторный запуск — no-op, если
метаданные уже промигрированы).

## 11. Какие API-эндпоинты нужно изменить

Новые:

- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`,
  `GET /api/auth/me`
- `GET /api/workspaces` (список workspace текущего пользователя — на первом
  этапе всегда один)
- (опционально, можно отложить) `POST /api/workspaces`, инвайты участников

Существующие — все требуют `Depends(get_current_user)` и неявный/явный
`workspace_id` (на первом этапе — единственный personal workspace
пользователя, бэкенд подставляет его сам, без параметра в URL):

| эндпоинт | изменение |
|---|---|
| `GET /api/system/status` | статистика — только по workspace пользователя |
| `GET /api/materials` | фильтр по `workspace_id`; `MaterialInfo` получает `id` (= `document_id`) |
| `POST /api/materials/upload` | сохраняет в `docs/<workspace_id>/...`, создаёт `Document`, проверяет лимиты (п.12) |
| `GET /api/materials/progress` | прогресс **по workspace**, не глобальный |
| `GET /api/materials/{document_id}/sections` | было `{file_name}` → теперь `document_id` |
| `POST /api/materials/reindex` | переиндексация всей библиотеки **workspace** |
| `POST /api/materials/{document_id}/reindex` | по `document_id` |
| `DELETE /api/materials/{document_id}` | см. п.8 |
| `POST /api/summaries` | поиск ограничен `workspace_id`; `selected_file` → `document_id` или оставить "Все материалы" |
| `POST /api/chat` | то же |
| `POST /api/exports/summary` | без изменений по сути, но имя файла может включать workspace-контекст |
| `GET /api/diagnostics/*` | ограничить `is_superuser` или вообще убрать из публичного API (сейчас отдаёт внутренние трейсы — не должно быть доступно всем пользователям) |

Важный нюанс: фронтенд сейчас оперирует `selected_file` как **именем файла**
(строка, в т.ч. "Все материалы"). Переход на `document_id` — это изменение
контракта, которое затронет `materials-workspace.tsx`, `summary-workspace.tsx`,
`assistant-workspace.tsx` (Track A). Стоит either: (a) держать `name` уникальным
в рамках workspace и продолжать адресовать по имени, добавив `document_id`
только для удаления/sections под капотом, либо (b) сразу перейти на
`document_id` везде. Рекомендация — **(a) на первом этапе** (имя файла уникально
в рамках одного workspace — это легко обеспечить при загрузке: при коллизии
имени добавлять суффикс), это резко уменьшает объём правок фронтенда. Полный
переход на `document_id` — отдельный этап, когда появится реальный сценарий с
переименованиями/множественными версиями файла.

## 12. Лимиты

Жёстко закодированные дефолты для `plan="free"` (хранить в `config.py` +
переопределяемо через `Workspace`/`User` в будущем для платных тарифов):

| лимит | значение (предложение) | где проверяется |
|---|---|---|
| Размер одного файла | 50 МБ (как сейчас, `MAX_UPLOAD_BYTES`) | `upload_material_service` |
| Кол-во документов в workspace | 30 | перед сохранением файла |
| Суммарный объём файлов в workspace | 500 МБ | перед сохранением файла |
| Параллельные операции индексации | 1 на workspace (не глобально, см. п.13/риски) | `_material_job_lock`, теперь per-workspace |
| Запросы к `/api/chat` и `/api/summaries` | напр. 30/час и 200/день на пользователя | rate-limit middleware/слой сервиса |
| Длина сообщения в чате | существующие ограничения промпта (без изменений) | — |

Лимиты на чат/конспекты важны в первую очередь из-за **стоимости вызовов LLM
(OpenRouter)** — без rate-limit один пользователь может исчерпать бюджет API.
Реализация простого rate-limit на первом этапе: счётчик в SQL (таблица
`UsageCounter` или просто поле `requests_today`/`reset_at` у `User`) —
без Redis, этого достаточно для небольшой нагрузки.

## 13. Порядок реализации по этапам

**Этап 0 (этот документ).** Согласование архитектуры, без изменений кода.

**Этап 1 — фундамент данных и auth.**
- Добавить SQL-слой (SQLAlchemy + SQLite на старте, путь к Postgres не
  закрывать), таблицы `User`, `Workspace`, `WorkspaceMember`, `Document`.
- Эндпоинты `/api/auth/*`, middleware `get_current_user`/`get_current_workspace`.
- Существующие эндпоинты пока **не трогаем функционально** — добавляем auth
  как отдельный слой, который можно временно сделать "мягким" (например,
  feature-flag `AUTH_ENABLED` для локальной разработки/тестов).

**Этап 2 — workspace-scoping в `KnowledgeBase` и хранилище файлов.**
- `workspace_id` обязательным аргументом во всех методах `KnowledgeBase`,
  связанных с поиском/индексацией/удалением.
- Новая схема путей `docs/<workspace_id>/<document_id>__name`, новая схема ID
  чанков и метаданных (п.5, п.6).
- Юнит-тесты на изоляцию (п.7).

**Этап 3 — миграция legacy-данных.**
- Скрипт миграции метаданных + перенос файлов в `legacy` workspace,
  привязанный к первому пользователю (п.9, п.10).

**Этап 4 — API + фронтенд.**
- Обновить `api_app.py`/`app_services.py` под workspace-контекст и auth
  (п.11).
- Прогресс операций — per-workspace.
- Фронтенд: страницы логина/регистрации, передача токена, без смены UX в
  остальном (имена файлов остаются ключом адресации, см. п.11).

**Этап 5 — лимиты и rate-limiting (п.12).**

**Этап 6 (опционально, отдельный трек) — шаринг workspace, роли, инвайты.**

Каждый этап — отдельные PR/коммиты с тестами, CI должен оставаться зелёным
после каждого этапа (в т.ч. через feature-flag, если функциональность ещё не
полностью готова к показу).

## 14. Риски и что не трогать на первом этапе

**Риски:**

- **Утечка данных между пользователями** — главный риск. Любой метод
  `KnowledgeBase`, забывший добавить `workspace_id` в `where`, отдаёт чужие
  документы. Митигировать через обязательный аргумент + тесты изоляции (п.7).
- **Дублирующиеся чанки разных пользователей** из-за глобальных md5-ID (п.6) —
  без исправления второй пользователь с тем же учебником "потеряет" свои чанки
  молча.
- **Общие тяжёлые модели в памяти** (`runtime.get_kb()`/`get_llm()` —
  embedding/reranker модели грузятся один раз на процесс). Это нормально и
  остаётся так — экономия памяти важнее изоляции на уровне процесса. Но
  **глобальная блокировка `_material_job_lock` на одну операцию для всего
  сервера** должна стать per-workspace, иначе один активный пользователь
  блокирует индексацию всем остальным.
- **Стоимость LLM-вызовов** при росте числа пользователей — нужны лимиты
  (п.12) до публичного анонса, не после.
- **Path traversal** при формировании `docs/<workspace_id>/<document_id>__<original_filename>` —
  обязательно санитизировать `original_filename`.
- **Старые intra-process тесты** (`tests/test_app_services.py`,
  `tests/test_api_app.py`) опираются на глобальный `runtime`/без авторизации —
  потребуют обновления по мере добавления auth-слоя (учитывать в Этапе 1,
  не откладывать на конец).

**Что сознательно НЕ делаем на первом этапе:**

- Отдельные коллекции ChromaDB на workspace (операционная сложность; одной
  коллекции с фильтром по `workspace_id` достаточно для ожидаемых объёмов).
- Полноценный RBAC/шаринг workspace между несколькими пользователями —
  модель данных это допускает (`WorkspaceMember`), но UI/проверки — только
  "owner == единственный участник".
- OAuth/SSO, восстановление пароля по email, 2FA.
- Переход адресации материалов на `document_id` во фронтенде (оставляем имя
  файла как ключ, уникальное в рамках workspace).
- Изменения в самом RAG-пайплайне (ранжирование, чанкинг, конспекты,
  HyDE) — только добавление параметра `workspace_id` в сигнатуры и `where`-фильтры.
- БД с самого начала через SQLAlchemy + Alembic-миграции, `DATABASE_URL`
  конфигурируем: SQLite (`sqlite:///./data/app.db`) для local/dev/CI,
  Postgres — для production. Миграции пишем так, чтобы одинаково работали на
  обоих диалектах (избегаем Postgres-специфичных типов без необходимости —
  `String`/`Integer`/`DateTime`/`Boolean`/UUID как `String(36)`).

---

## Принятые решения (по итогам согласования)

По открытым вопросам из предыдущей версии документа приняты следующие решения:

1. **Workspace на старте** — "1 пользователь = 1 личный workspace",
   создаётся автоматически при регистрации. Шаринг/роли — только в модели
   данных (`WorkspaceMember`), без UI/проверок на первом этапе.
2. **Auth** — email + пароль + JWT (httpOnly cookie). Без OAuth и без
   подтверждения email на первом этапе (поля под это зарезервированы).
3. **БД** — SQLAlchemy + Alembic с самого начала, `DATABASE_URL` конфигурируем.
   Production — Postgres, локальная разработка/CI — SQLite. Решение принято
   на старте, чтобы не переписывать модели/миграции позже.
4. **Лимиты MVP** — приняты значения из п.12 как есть: 50 МБ/файл,
   30 документов/workspace, 500 МБ/workspace, rate-limit на `/api/chat` и
   `/api/summaries`. Вынесены в `config.py` как именованные константы с
   возможностью переопределения через env — без отдельной таблицы "тарифов"
   на первом этапе.
5. **Legacy-данные** — демо-файлы (`Krasnov...`, `The_Little_Match_Girl.txt`,
   `pir.txt`) переносятся в `sample_docs/`. Текущий `data/chromadb` /
   `docs/*` рассматриваются как **dev-данные**: миграция в `legacy` workspace
   реализуется отдельным **dev-only** скриптом (для тех, кто хочет сохранить
   локальный индекс при апгрейде), но **не является частью прод-раскатки** —
   новые пользователи на проде стартуют с пустой личной библиотекой,
   `data/chromadb` для прод-окружения создаётся с нуля.

---

## 15. План реализации по этапам (детально)

Каждый этап — отдельная серия PR, после каждого этапа `main`/рабочая ветка
остаётся зелёной по CI (`npm run lint`, `npm run typecheck`, `pytest`).
Пути файлов — относительно корня репозитория.

### Этап 1 — фундамент: БД, модели, auth (без изменения текущих RAG-эндпоинтов)

**Цель:** добавить слой пользователей/workspace и auth-эндпоинты, ничего не
меняя в существующих `/api/materials`, `/api/chat`, `/api/summaries` и т.д.
Существующие тесты (`tests/test_api_app.py`, `tests/test_app_services.py`)
не трогаем — они должны остаться зелёными без изменений.

**Новые файлы:**

- `src/db.py` — SQLAlchemy `engine`, `SessionLocal`, `Base`, FastAPI-зависимость
  `get_db()`. Читает `config.DATABASE_URL`.
- `src/db_models.py` — ORM-модели:
  - `User` (id, email, password_hash, display_name, is_active, is_superuser,
    email_verified_at, created_at, updated_at)
  - `Workspace` (id, name, owner_user_id, plan, created_at)
  - `WorkspaceMember` (id, workspace_id, user_id, role, created_at)
  - `Document` (id, workspace_id, owner_user_id, original_name, stored_path,
    size_bytes, content_hash, status, sections_count, error_message,
    created_at, updated_at) — таблица создаётся уже сейчас, но не
    используется до Этапа 2/3.
- `src/security.py` — хэширование пароля (`passlib[bcrypt]`), создание/проверка
  JWT (`python-jose`).
- `src/auth_service.py` — `register_user`, `authenticate_user`,
  `create_personal_workspace(user)`, `get_current_user` (FastAPI dependency,
  читает JWT из httpOnly cookie).
- `src/auth_models.py` — Pydantic-схемы: `UserCreate`, `UserLogin`, `UserOut`,
  `WorkspaceOut`.
- `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial.py` —
  начальная миграция (таблицы выше).

**Изменённые файлы:**

- `config.py` — добавить `DATABASE_URL` (default `sqlite:///./data/app.db`),
  `JWT_SECRET_KEY` (из env, обязателен в проде), `JWT_ALGORITHM="HS256"`,
  `JWT_EXPIRE_MINUTES`.
- `requirements.txt` — добавить `sqlalchemy>=2.0`, `alembic>=1.13`,
  `passlib[bcrypt]>=1.7`, `python-jose[cryptography]>=3.3`,
  `psycopg[binary]>=3.1` (Postgres-драйвер для прод).
- `api_app.py` — подключить роутер `/api/auth/*`
  (`register`, `login`, `logout`, `me`).
- `.env.example` — добавить `DATABASE_URL`, `JWT_SECRET_KEY`.

**Новые тесты:**

- `tests/test_auth_service.py` — хэширование/проверка пароля, JWT
  encode/decode, `create_personal_workspace` создаёт ровно один workspace на
  пользователя.
- `tests/test_api_auth.py` — register → login → `/api/auth/me` → logout;
  дубликат email → 409; неверный пароль → 401; защищённый эндпоинт без
  токена → 401.

**Definition of done:** новая БД создаётся миграцией `alembic upgrade head`
(SQLite в CI/тестах через фикстуру с временной БД); существующие тесты не
изменены и зелёные; новые auth-тесты зелёные.

### Этап 2 — workspace-scoping в `KnowledgeBase` и хранилище файлов

**Цель:** сделать `workspace_id`/`document_id` обязательной частью индекса и
путей на диске, без подключения auth к публичным эндпоинтам (мост через
константу `DEFAULT_WORKSPACE_ID`, чтобы текущие endpoint/тесты продолжали
работать без логина — это временно, убирается в Этапе 3).

**Новые файлы:**

- `src/storage.py` — хелперы:
  - `workspace_docs_dir(workspace_id) -> str` (`docs/<workspace_id>/`)
  - `sanitize_filename(name) -> str` (убрать `/`, `\`, `..`, ограничить длину)
  - `document_stored_path(workspace_id, document_id, original_name) -> str`
  - `is_workspace_library_path(path) -> bool` (замена
    `KnowledgeBase._is_library_file_path`)

**Изменённые файлы:**

- `src/knowledge_base.py`:
  - все методы поиска/индексации/удаления/статистики получают обязательный
    первый аргумент `workspace_id` (`add_book`, `index_all_books`,
    `remove_book` → `remove_chunks(workspace_id, document_id)`, `stats`,
    `get_file_profile`, `get_sections_for_file`, `get_available_sections`,
    `get_available_files`, `search_with_sources`,
    `search_chunks_for_summary`, `get_file_chunks`, `find_section_in_query`,
    `clear`);
  - `_build_where_filter(workspace_id, file_filter, section_filter)` —
    всегда добавляет `{"workspace_id": workspace_id}` в `where`;
  - `_md5` для ID чанка → `_chunk_id(workspace_id, document_id, text)` =
    `md5(f"{workspace_id}:{document_id}:{text}")`;
  - дедупликация `existing_ids` — теперь через
    `self._col.get(where={"$and":[{"workspace_id":...},{"document_id":...}]})`,
    а не по всей коллекции;
  - `_iter_library_files`/`_is_library_file_path` → используют
    `src/storage.is_workspace_library_path` и обходят
    `docs/<workspace_id>/*` для конкретного `workspace_id`.
- `config.py` — добавить `DEFAULT_WORKSPACE_ID = "dev-default"` (временный
  мост для Этапа 2, удаляется в Этапе 3).

**Новые тесты:**

- `tests/test_knowledge_base_isolation.py`:
  - индексируем один и тот же текст в `workspace_a` и `workspace_b` →
    у обоих появляются свои чанки (нет потери из-за дедупликации);
  - поиск/`get_available_files`/`stats` с `workspace_id=a` не видят данные `b`;
  - `remove_chunks(a, document_id)` не затрагивает чанки `b`.
- Обновить `tests/test_app_services.py` — там, где тесты дергают `KnowledgeBase`
  напрямую через `FakeKB`, добавить `workspace_id` в сигнатуры фейков (даже
  если значение пока `config.DEFAULT_WORKSPACE_ID`).

**Definition of done:** `tests/test_api_app.py` остаётся зелёным без
изменений (т.к. `app_services` пока прозрачно подставляет
`DEFAULT_WORKSPACE_ID`); новые тесты изоляции зелёные.

### Этап 3 — подключение auth к материалам/чату/конспектам, `Document`-таблица

**Цель:** убрать `DEFAULT_WORKSPACE_ID`, все запросы идут от имени
авторизованного пользователя и его личного workspace. `Document` — источник
правды о списке материалов (вместо обхода файловой системы).

**Новые файлы:**

- `src/document_service.py` — CRUD над `Document` + синхронизация с
  `KnowledgeBase`: `create_document`, `mark_ready`, `mark_error`,
  `delete_document` (оркестрирует Chroma → файл → запись в БД, см. п.8),
  `list_documents(workspace_id)`.

**Изменённые файлы:**

- `src/app_services.py` — все сервисные функции (`list_materials`,
  `upload_material_service`, `delete_material_service`,
  `reindex_material_service`, `list_sections`, `generate_summary_service`,
  `chat_service`, `get_system_status`) получают `workspace_id`/`user_id` и
  передают их в `KnowledgeBase`/`document_service`. `_material_progress_state`
  и `_material_job_lock` → словари `{workspace_id: state}` /
  `{workspace_id: Lock()}`.
- `api_app.py` — все существующие эндпоинты получают
  `Depends(get_current_user)`; `workspace_id` берётся как
  `current_user.personal_workspace_id` (без параметра в URL на этом этапе).
  `GET /api/diagnostics/*` — ограничить `Depends(require_superuser)`.
- `src/api_models.py` — `MaterialInfo` получает поле `id` (= `document_id`,
  строка-UUID), используется только для `DELETE`/`reindex`/`sections`; имя
  (`name`) остаётся основным полем для адресации с фронтенда (см. п.11а).
- `config.py` — убрать `DEFAULT_WORKSPACE_ID`.

**Изменённые тесты:**

- `tests/test_api_app.py` — все запросы теперь через аутентифицированный
  `TestClient` (фикстура: создать пользователя, залогиниться, переиспользовать
  cookie/токен).
- `tests/test_app_services.py` — функции вызываются с `workspace_id`/`user_id`
  тестового пользователя.
- Новый `tests/test_material_progress_per_workspace.py` — прогресс/блокировка
  не пересекаются между двумя workspace.

**Definition of done:** все существующие сценарии (загрузка, удаление,
переиндексация, чат, конспект) проходят под авторизованным пользователем;
два пользователя видят только свои материалы (end-to-end тест через
`TestClient` с двумя пользователями).

### Этап 4 — миграция legacy-данных и уборка `docs/`

**Цель:** привести репозиторий и dev-окружения в соответствие новой схеме
путей, не теряя текущие демо/dev-материалы.

**Новые файлы:**

- `scripts/migrate_to_workspaces.py` — **dev-only** скрипт:
  1. создаёт (если нет) `legacy` workspace, привязанный к первому `User`
     в БД (или к указанному в аргументе email);
  2. для каждого `source_file` в текущей коллекции создаёт `Document`,
     проставляет всем его чанкам `workspace_id`/`document_id`/`user_id` через
     `collection.update(ids=..., metadatas=...)`, пересчитывает ID чанков
     (удалить старые id + добавить с новыми id, переиспользуя существующие
     эмбеддинги через `collection.get(include=["embeddings", ...])` —
     без переэмбеддинга);
  3. перемещает файлы `docs/*.{ext}` (верхний уровень) в
     `docs/<legacy_workspace_id>/<document_id>__<filename>`.
- Документация: `README.md` / `design/multi-user-architecture.md` — раздел
  "как поднять dev-окружение после обновления" со ссылкой на скрипт.

**Изменённые файлы:**

- Перенос `docs/Krasnov...pdf`, `docs/The_Little_Match_Girl.txt`, `docs/pir.txt`
  → `sample_docs/` (с обновлением `sample_docs/README.md`).
- `.gitignore` — без изменений (`docs/*` остаётся игнорируемым, `docs/.gitkeep`
  остаётся).

**Тесты:** `tests/test_migrate_to_workspaces.py` — на временной копии
`data/chromadb`/`docs/` с парой тестовых файлов проверяет, что после
миграции (а) старые ID отсутствуют, (б) новые чанки имеют корректные
`workspace_id`/`document_id`, (в) файлы перемещены, (г) повторный запуск —
no-op.

**Definition of done:** скрипт запускается локально на dev-данных без потери
материалов; прод стартует с чистой БД/индексом (без запуска скрипта).

### Этап 5 — фронтенд: вход/регистрация, workspace-контекст

**Цель:** UI для auth, без изменения остального UX (имена файлов остаются
ключом адресации — см. п.11а).

**Новые файлы (frontend):**

- `frontend/src/components/auth/login-form.tsx`,
  `frontend/src/components/auth/register-form.tsx`
- `frontend/src/lib/auth.ts` — обёртки над `/api/auth/*`, хранение состояния
  пользователя (cookie httpOnly — фронту достаточно знать "залогинен/нет" через
  `/api/auth/me`).
- `frontend/src/app/login/page.tsx`, `frontend/src/app/register/page.tsx` (или
  аналогичная структура роутов Next.js — уточнить по факту структуры `app/`).

**Изменённые файлы:**

- `frontend/src/components/app-shell.tsx` — редирект на `/login`, если
  `/api/auth/me` вернул 401.
- `frontend/src/lib/api.ts` — все `fetch` с `credentials: "include"`.

**Тесты:** `npm run lint`, `npm run typecheck` (как и сейчас); ручная проверка
через `/preview` (skill `run`), без отдельного e2e-фреймворка на этом этапе.

### Этап 6 — лимиты и rate-limiting

**Новые файлы:**

- `src/limits.py` — проверки: `check_upload_allowed(workspace_id, size_bytes)`,
  `check_rate_limit(user_id, action)`.

**Изменённые файлы:**

- `config.py` — константы:
  `MAX_DOCUMENTS_PER_WORKSPACE=30`, `MAX_WORKSPACE_BYTES=500*1024*1024`,
  `CHAT_RATE_LIMIT_PER_HOUR`, `SUMMARY_RATE_LIMIT_PER_DAY` (значения из п.12,
  переопределяемы через env).
- `src/db_models.py` — добавить на `User` поля-счётчики (или отдельную
  таблицу `UsageCounter`: `user_id`, `action`, `count`, `window_start`).
- `src/app_services.py` / `api_app.py` — вызовы `check_upload_allowed`/
  `check_rate_limit` перед `upload_material_service`, `chat_service`,
  `generate_summary_service`; превышение → понятная ошибка (400/429) в
  существующем формате `MaterialActionResponse`/`ChatResponse`-эквиваленте.

**Тесты:** `tests/test_limits.py` — превышение размера файла/количества
документов/частоты запросов возвращает ожидаемую ошибку, не ломая обычный
сценарий в пределах лимита.

---

Этапы 1-3 — обязательное ядро (auth + изоляция данных), этапы 4-6 можно вести
параллельно/в любом порядке после готовности Этапа 3. Шаринг workspace и роли
(п.13, "Этап 6" из предыдущей версии плана) — отдельный трек после публичного
MVP, не входит в этот план.
