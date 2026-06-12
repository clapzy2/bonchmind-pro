# BonchMind Frontend

Frontend BonchMind Pro на **Next.js**.

После Stage 6 это основной и единственный пользовательский интерфейс проекта. Старый Gradio UI удалён.

---

## Что работает

* регистрация, вход и выход;
* защита рабочей области от анонимных пользователей;
* личный workspace для каждого пользователя;
* загрузка, удаление и переиндексация материалов;
* генерация конспектов;
* экспорт конспекта в `.docx`;
* ассистент по загруженным материалам;
* отображение источников ответа;
* просмотр качества и диагностики последнего запуска.

---

## Запуск

### Backend

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

### Frontend

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

## Proxy до backend

`next.config.ts` проксирует запросы:

```text
/api/* -> http://127.0.0.1:8000/api/*
```

Backend URL можно переопределить:

```powershell
$env:BONCHMIND_API_URL="http://127.0.0.1:8000"
npm run dev
```

После изменения `next.config.ts` dev-сервер нужно перезапустить.

---

## Docker

Фронтенд собирается в standalone-образ (`output: "standalone"` в `next.config.ts`) и запускается в составе общего `docker-compose` из корня проекта — отдельно поднимать не нужно. Подробности в корневом `README.md` (раздел «Запуск через Docker»).

В Docker `BONCHMIND_API_URL` задаётся на этапе сборки (build arg), потому что Next вычисляет rewrites из `next.config.ts` во время `next build`. По умолчанию `http://backend:8000` — имя сервиса backend в compose.

---

## Аутентификация

Frontend использует FastAPI-сессию через HttpOnly cookie.

* `/register` — регистрация;
* `/login` — вход;
* `/` — защищённая рабочая область;
* кнопка «Выйти» очищает cookie и возвращает на `/login`.

Access token во frontend **не сохраняется**.
Все protected-запросы идут с:

```ts
credentials: "include"
```

При `401 Unauthorized` frontend редиректит пользователя на `/login`.

---

## Workspace

У каждого пользователя один personal workspace.

Frontend не выбирает workspace вручную. Backend сам подставляет workspace текущего пользователя:

```text
current_user.personal_workspace.id
```

Это обеспечивает изоляцию данных:

* Alice не видит материалы Bob;
* Bob не видит материалы Alice;
* Summary и Assistant работают только внутри workspace текущего пользователя.

---

## Проверки

Из папки `frontend/`:

```powershell
npm run typecheck
npm run lint
```

Перед merge ожидается:

```text
npm run typecheck -> clean
npm run lint -> clean
```

Также из корня проекта:

```powershell
pytest tests/ -q
```

---

## Manual smoke

Минимальная ручная проверка:

```text
1. / редиректит анонимного пользователя на /login.
2. Register/Login/Logout работают.
3. Материал загружается и появляется в списке без F5.
4. Summary работает по загруженному файлу.
5. Assistant отвечает по загруженному файлу.
6. Sources отображаются.
7. Bob не видит материалы Alice.
8. Alice не видит материалы Bob.
```

---

## Важно помнить

* Backend должен быть запущен до frontend.
* Первый ответ может быть медленным из-за прогрева моделей.
* Если используется Ollama, она должна быть запущена отдельно.
* Короткие `.txt` материалы могут отображаться как `plain_text`, это нормально.
* `plain_text` материал всё равно должен подходить для Summary и Assistant.
* После Stage 6 Gradio удалён: `main.py`, `run.py`, `gradio dependency`, `DEFAULT_WORKSPACE_ID`.
* После фикса Stage 6 Summary должен иметь fallback для коротких/plain-text файлов, чтобы не возвращать `Фрагменты: 0`, если выбранный файл реально проиндексирован.

---

## Known gaps

Не блокируют основную работу:

* загрузка нескольких файлов сразу;
* export diagnostics JSON через UI;
* полноценный раздел Settings;
* admin diagnostics UI;
* light theme.
