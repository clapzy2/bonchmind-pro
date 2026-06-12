# Stage 6 parity matrix — Gradio (`main.py`) ↔ Next.js (`frontend/`)

Snapshot taken on `0e0c8ffd` (post-Stage-5 main). This doc decides whether
the Next.js UI is ready for Stage 6 sub-steps **6c (deprecation)** and
**6d (remove Gradio)**.

## Verdict

**Next.js covers all the production scenarios.** No blocker gaps. The
small list of Gradio-only features in §3 is either (a) covered by the
shell / system status differently, (b) a dev-only maintenance tool that
does not belong in a user-facing UI, or (c) a low-value polish item
recorded as known-gap with a follow-up ticket.

A separate hard reason to retire Gradio: it bypasses Stage 3+ auth
entirely. `on_add_book` writes through `kb.add_book(...)` directly into
`config.DEFAULT_WORKSPACE_ID` without touching the `Document` table,
which conflicts with the multi-user invariants we built in Stages 3/4.
The longer Gradio stays, the more its uploads diverge from the
authenticated API's view of the world.

## 1. Tab-by-tab parity

| Gradio tab | Next.js equivalent | Status | Notes |
|---|---|---|---|
| 💬 **Ассистент** (chat, file filter, answer mode, history clear, DOCX export) | `AssistantWorkspace` (`assistant`) | ✅ covered | Auth-scoped, workspace-isolated, polished UI. |
| 📝 **Конспект** (file + section + topic + type, generate, DOCX export) | `SummaryWorkspace` (`summary`) | ✅ covered | Same backend `/api/summaries` + `/api/exports/summary`. Workspace-scoped end-to-end since Stage 4. |
| 📚 **Материалы** (upload multiple, reindex docs/, stats, clear KB) | `MaterialsWorkspace` (`materials`) | ⚠ mostly covered — see §2 | Auth + workspace isolation are *additions*, not parity gaps. Three Gradio-only operations recorded below. |
| 🧪 **Диагностика** (last-run trace, JSON export) | `QualityWorkspace` (`quality`) | ⚠ trace-display covered, JSON export missing | Last-run is shown rendered. Raw-JSON download is a known-gap (§3). |
| ⚙️ **Система** (about text, theme toggle) | `WorkspaceSectionView` (`settings`) | ⚠ placeholder | About copy is implicitly in the shell; theme toggle is dropped (Next.js is dark-by-design). Known-gap if we ever add light theme. |

## 2. Differences inside the "Материалы" tab

| Gradio op | Behaviour | Next.js status | Decision |
|---|---|---|---|
| Upload **multiple** files at once | `gr.File(file_count="multiple")` → loop `on_add_book` per file | Single-file `uploadMaterial` | **Known-gap, follow-up ticket.** Workaround: select files one-by-one in the picker. Low priority — most users upload incrementally. |
| **Stats** button | Prints `total_books`, `total_chunks`, file list, section count | `getSystemStatus` returns the same numbers; shell already shows total_books / total_chunks; materials list shows the file list | **Already covered by the shell.** No dedicated button needed. |
| **Reindex docs/ folder** (`on_index_books` → `kb.index_all_books()`) | Walks the on-disk `docs/` directory and re-indexes every file | `reindexLibrary()` → `POST /api/materials/reindex` re-indexes every Document the workspace owns | **Already covered.** The new behaviour is *better* — it only touches the caller's workspace, not someone else's files on the same disk. |
| **Clear KB** button (`on_clear_kb` → `kb.clear()`) | Wipes the *entire* Chroma collection across all workspaces | No equivalent | **Intentionally dropped.** This is a dev/maintenance hatchet, not a user UI feature. The proper per-user operation — delete each material — is already exposed. If a maintainer needs a full wipe they can run a one-off script against the DB. |

## 3. Known-gaps (recorded, not blockers)

These do **not** block Gradio removal. Each gets its own follow-up
ticket; the deletion of Gradio in 6d is gated on the items in §1 and §2,
not on these.

1. **Multi-file upload in Materials** — sequence-loop in `MaterialsWorkspace` would close it without backend changes. Priority: low.
2. **Diagnostics JSON export** — the backend already returns the trace in `SummaryResponse.trace` and the admin endpoint `/api/diagnostics/latest.json` exists. The UI just needs a "Скачать JSON" button on the Quality screen. Priority: low.
3. **Real Settings tab content** — currently a placeholder. Once a user-facing toggle actually exists (e.g. LLM mode picker, default summary type), this graduates from placeholder to real screen. Priority: low — no user toggles defined yet.
4. **Superuser diagnostics UI** — `/api/diagnostics/latest` + `/latest.json` stay accessible via raw HTTP for now (decision per user, Stage 6 plan). Adding a `is_superuser`-gated screen later is independent of Gradio retirement.

## 4. What Next.js gives that Gradio never did

For completeness — these are the reason we built Stage 1–5, and the
core reason Gradio has to go before they bite:

- Auth (login / register / logout / session via HttpOnly cookie).
- Workspace isolation enforced at the API layer; each user sees only
  their own materials / summary / chat / progress.
- `Document` table — per-user audit of files, status tracking
  (processing / ready / error), document-id-based delete + reindex.
- Progress polling that finishes correctly (post-Stage-5g) instead of
  Gradio's "Result" textbox that just dumps whatever the handler
  printed.
- Cross-workspace leak protection verified by `tests/test_two_users_isolation.py`
  end-to-end.

Keeping Gradio means keeping a back-door into `DEFAULT_WORKSPACE_ID`
that is *not* covered by the Stage 3+ test suite.

## 5. Conclusion for the rest of Stage 6

- **6b (close gaps)** — nothing to do. The §3 known-gaps are recorded and explicitly out of scope per user decision.
- **6c (deprecation notice)** — proceed: print a `DeprecationWarning` on `python main.py` start-up, update `README.md` and `frontend/README.md`.
- **6d (remove Gradio)** — proceed: delete `main.py`, drop the `gradio` dependency from `requirements.txt`, remove all `_get_kb` / `_get_llm` / `_llm` / `_kb` legacy plumbing in `app_services.generate_summary_service` that exists only to feed Gradio's `on_generate_summary`.
- **6e (drop `DEFAULT_WORKSPACE_ID`)** — proceed in mode (a): remove `config.DEFAULT_WORKSPACE_ID`; replace the kwarg defaults in `summary_engine.py` / `knowledge_base.py` with a required positional `workspace_id`; update any test that still calls KB without an explicit workspace.
- **6f (cleanup docs)** — close the Stage 3 backlog items "Drop `DEFAULT_WORKSPACE_ID`" and "Workspace-aware `summary_engine.py`" formally; update READMEs.
