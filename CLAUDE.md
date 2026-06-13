# CLAUDE.md

Project-level guidance for Claude Code. Keep this short and factual — it is loaded into every conversation. For end-user docs see `README.md`.

## What this project is

**BonchMind Pro** — multi-user RAG over uploaded study materials.

- **Backend**: FastAPI (`api_app.py`) → service layer (`src/app_services.py`) → `KnowledgeBase` (ChromaDB) + `summary_engine` + `llm_engine`.
- **Frontend**: Next.js 16 + React 19 + Tailwind v4 in `frontend/` (single SPA, App Router).
- **Storage**: SQLite via SQLAlchemy + Alembic for users/workspaces/documents; ChromaDB for vectors; uploaded files on disk under `docs/`.
- **LLM**: OpenRouter API (`LLM_MODE=api`, default) or local Ollama (`LLM_MODE=ollama`).
- **Embeddings**: `BAAI/bge-m3`. **Reranker**: `BAAI/bge-reranker-v2-m3` (cross-encoder).

## Run

```powershell
# Backend (port 8000)
python -m alembic upgrade head
python run_api.py

# Frontend (port 3000, proxies /api/* → :8000)
cd frontend
npm install
npm run dev
```

Backend must be up before frontend.

## Required gates before any commit goes to main

All four must pass:

```powershell
pytest tests/ -q          # 187+ passing
cd frontend
npm run typecheck         # tsc --noEmit, clean
npm run lint              # eslint, clean
```

Plus CI green (`.github/workflows/ci.yml`: backend tests + alembic upgrade check + frontend typecheck + lint).

## Hard rules

- **`workspace_id` is keyword-only and required** across `src/knowledge_base.py` and `src/summary_engine.py`. There is no implicit fallback (Stage 6e removed `DEFAULT_WORKSPACE_ID`). Missing it raises a `TypeError`, by design.
- **Workspace comes from auth, never from the client.** `api_app.get_current_workspace_id` resolves `current_user.personal_workspace.id` from the JWT cookie (`bonchmind_auth`, HttpOnly + SameSite=Lax). Never accept a workspace id from a request body or URL.
- **No Gradio.** Removed in Stage 6 (`main.py`, `run.py`, `ingest.py`, `gradio` dependency, `DEFAULT_WORKSPACE_ID`). If you see a reference to any of them in code, it's an orphan — delete or inline it, don't reintroduce the dependency.
- **No access token in browser storage.** Auth is cookie-only; the frontend uses `credentials: "include"` and never reads or writes tokens to `localStorage`/`sessionStorage`.
- **Auth tiers** (set in `api_app.py`):
  - Public: `/api/health`, `/api/auth/register`, `/api/auth/login`.
  - Authenticated: everything that takes the `WorkspaceId` dependency.
  - Superuser-only: `/api/diagnostics/*` and `/api/admin/*` (via `require_superuser`). First superuser is promoted directly in the DB (`users.is_superuser`); there is no public promote API, by design.
- **`Document` table is the source of truth for ownership.** Uploaded files write a row with `workspace_id` + `owner_user_id`; KB chunks carry the same `workspace_id` in metadata. Both must stay in sync.

## Where things live

| Concern | File |
|--------|------|
| FastAPI routes + auth dependencies | `api_app.py` |
| Auth (JWT cookie, register/login/me/logout) | `src/auth_api.py`, `src/auth_service.py` |
| Service layer (called by routes) | `src/app_services.py` |
| RAG retrieval, indexing, workspace filter | `src/knowledge_base.py` |
| Summary pipeline | `src/summary_engine.py` |
| LLM client (API or Ollama) | `src/llm_engine.py` |
| Pydantic request/response models | `src/api_models.py` |
| SQLAlchemy models | `src/db_models.py` (`User`, `Workspace`, `WorkspaceMember`, `Document`) |
| Alembic migrations | `alembic/versions/` |
| Runtime config (env-driven) | `config.py` |
| Frontend shell + routing | `frontend/src/app/page.tsx`, `frontend/src/components/app-shell.tsx` |
| Frontend API client + auth helpers | `frontend/src/lib/api.ts`, `frontend/src/lib/handle-auth-error.ts` |
| Workspaces (UI screens) | `frontend/src/components/{assistant,summary,materials,admin}-workspace.tsx` |
| Audit log (write + read) | `src/audit_service.py` (`record`, `list_recent`); superuser admin endpoints in `api_app.py` |

## Test setup

- `tests/conftest.py` sets `DATABASE_URL` to a temp SQLite and seeds users/workspaces; tests are isolated per-run.
- `tests/test_knowledge_base_isolation.py` uses a `FakeEmbeddings` stub and disables the reranker — that's how to write KB tests without loading 2GB of models.
- Tests must explicitly pass `workspace_id` to every KB / summary call. There is no default.

## Env

`.env` (gitignored) — at minimum:

```env
LLM_MODE=api
API_KEY=<openrouter key>
API_MODEL=qwen/qwen3-32b
JWT_SECRET_KEY=<any long random string for dev>
```

For Ollama: `LLM_MODE=ollama` + a running local Ollama on `:11434`. `JWT_SECRET_KEY` defaults to a deliberately insecure dev string — production must override.

## Conventions worth knowing

- **Comments**: Russian or English, both fine. Existing code mixes both; match the surrounding file.
- **Frontend state** persists active tab + per-workspace preferences in `localStorage` (keys `bonchmind-active-section`, `bonchmind-summary-preferences`, etc.). F5 must not bounce the user back to a different tab.
- **Upload flow**: `POST /api/materials/upload` returns immediately; indexing runs in a background thread. Frontend polls `GET /api/materials/progress` until `active=false`. Don't clear `isUploading` until polling sees the job finish, or the progress bar dies at 1%.
- **Summary fallback**: `search_chunks_for_summary` has a defensive fallback (Stage 6g) — when semantic+lexical pools are empty but `kw_filter` matches workspace chunks, surface them. Mirrors chat behavior; intentionally skips the `_is_noise_summary_chunk` 250-char cutoff (it's a big-book quality heuristic, not a workspace check).

## Out of scope for now

- Multi-file upload, light theme, finer roles than `is_superuser` (per-workspace roles, promote/demote, ban, rate-limit tuning from the UI), mobile/responsive polish, English UI (i18n), pgvector. These are the consciously-deferred gaps documented in `README.md` — don't fix them unless a stage explicitly takes them on.
- Done since this file was first written: Docker/Postgres deploy (Stage 8), Settings/Quality tabs were removed rather than built (Stage 7d), security hardening + audit log (Stage 9a), and the superuser **Admin** screen — stats + audit log + diagnostics (Stage 9b, `frontend/src/components/admin-workspace.tsx`). `run-diagnostics.tsx` is now wired into the admin screen.
