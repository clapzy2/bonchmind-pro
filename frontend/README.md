# BonchMind Frontend

Интерфейс BonchMind Pro на `Next.js` — основной (и единственный после Stage 6) frontend.

Сейчас это уже рабочий frontend для:
- генерации конспектов;
- диалога с ассистентом;
- управления библиотекой материалов;
- просмотра качества последнего запуска.

---

## Что уже работает

- подключение к FastAPI backend через `/api/...`;
- аутентификация (Stage 5): регистрация, вход, выход, защита `/`;
- экран `Конспект` с генерацией и экспортом `.docx`;
- экран `Ассистент` с режимами ответа;
- экран `Материалы` с загрузкой, удалением и переиндексацией;
- экран `Проверка качества`;
- продуктовый layout с левой навигацией, центральной рабочей областью и правой вспомогательной панелью;
- typecheck без ошибок.

---

## Что еще в работе

- дальнейшая полировка UX;
- доведение `Настроек` до полноценного раздела;
- разделение пользовательского и технического слоя;
- более аккуратные состояния ошибок и долгих операций;
- дальнейшее упрощение интерфейса для обычного пользователя.

---

## Запуск

### 1. Backend

Из корня проекта:

```powershell
python run_api.py
```

Проверка:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Ожидаемый ответ:

```text
status
------
ok
```

### 2. Frontend

Из папки `frontend/`:

```powershell
npm install
npm run dev
```

Открыть:

```text
http://127.0.0.1:3000
```

---

## Node.js

Нужен обычный локальный Node.js с `npm` в `PATH`.

Проверка:

```powershell
node -v
npm -v
```

---

## Proxy до backend

`next.config.ts` проксирует запросы:

```text
/api/* -> http://127.0.0.1:8000/api/*
```

При необходимости можно переопределить backend URL:

```powershell
$env:BONCHMIND_API_URL="http://127.0.0.1:8000"
npm run dev
```

---

## Проверка

```powershell
npm run typecheck
```

---

## Что важно помнить

- часть UX еще активно шлифуется;
- dev-сервер Next.js нужно перезапускать после изменений `next.config.ts`;
- первый ответ backend может быть медленнее из-за прогрева моделей;
- некоторые материалы могут индексироваться как `plain_text`, если у них нет нормальной структуры разделов.

---

## Аутентификация (Stage 5)

Frontend защищает все рабочие экраны через FastAPI-сессию из Stage 1:

- регистрация: `http://127.0.0.1:3000/register` (email + пароль ≥ 8 символов; имя необязательно). Сразу после регистрации backend ставит HttpOnly cookie, и frontend ведёт на `/` без второго входа.
- вход: `http://127.0.0.1:3000/login`.
- выход: кнопка «Выйти» в правом верхнем углу (`Topbar`). Чистит cookie на backend и редиректит на `/login`.
- `/` (рабочая область) защищён `<AuthProvider>` + `useAuth()` хуком: анонимный посетитель сразу уходит на `/login`, валидная сессия видит splash на момент загрузки и затем `AppShell` со своими материалами.
- `getMe()` пробрасывает `null` для анонимного состояния и не выбрасывает ошибку — это «нормальный» поток, не «упало».

Access-токен (`access_token` из ответа `/api/auth/{register,login}`) **намеренно** нигде во frontend не сохраняется. Авторизация целиком держится на HttpOnly cookie `bonchmind_auth`, которую backend сам ставит и читает. Все `fetch` используют `credentials: "include"`.

Что делать с 401 от защищённого endpoint-а:

- `api.ts` бросает `UnauthorizedError` (для login — `InvalidCredentialsError`, для register-conflict — `EmailConflictError`);
- Workspace-компоненты (Materials / Summary / Assistant) ловят `UnauthorizedError` через `handleAuthError(err, router)` и редиректят на `/login`;
- Splash + `AuthProvider` повторно зовут `getMe()`; если сессии нет, попадаем на `/login` ещё до рендера AppShell.

### Workspace модель

У каждого пользователя один personal workspace (Stage 1-инвариант, см. `design/multi-user-architecture.md`). Frontend **не делает выбор workspace вручную** — backend на каждый запрос подставляет `current_user.personal_workspace.id`, а Topbar показывает его имя как read-only текст рядом с пользователем.

### Legacy Gradio UI

Удалён в Stage 6d (`main.py`/`run.py` + `gradio` dependency убраны из репозитория). Причина — он обходил auth и писал всё в `config.DEFAULT_WORKSPACE_ID`, минуя `Document` table. Parity-check Gradio ↔ Next.js перед удалением — в `design/stage-6-parity.md`.
