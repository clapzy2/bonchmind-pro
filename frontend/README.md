# BonchMind Pro Frontend

Next.js prototype for the future BonchMind Pro product interface.

## What This Is

This is the first React/Next.js app shell:

- left materials sidebar;
- top backend/model status bar;
- central summary workspace;
- right source and diagnostics panel.

It uses the FastAPI backend through `/api/...` rewrites.

## Requirements

- Node.js with npm available in PATH.
- BonchMind FastAPI backend running on `http://127.0.0.1:8000`.

The Codex bundled Node runtime can read JavaScript files, but it does not provide a normal `npm` command in this workspace. Install regular Node.js locally if `npm -v` does not work in PowerShell.

## Run Backend

From the project root:

```powershell
python run_api.py
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected:

```text
status
------
ok
```

## Run Frontend

From `frontend/`:

```powershell
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

## API Proxy

`next.config.ts` proxies frontend calls:

```text
/api/* -> http://127.0.0.1:8000/api/*
```

Override backend URL:

```powershell
$env:BONCHMIND_API_URL="http://127.0.0.1:8000"
npm run dev
```

## Current Scope

Included:

- product dashboard layout;
- API health/status/materials integration;
- offline fallback state.

Not included yet:

- posting summary generation from React;
- streaming progress;
- source cards from real diagnostics;
- upload/indexing UI.
