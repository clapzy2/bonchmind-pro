"""FastAPI entrypoint for BonchMind Pro.

Authentication gates every non-public endpoint (Stage 3a). ``workspace_id``
is plumbed from ``current_user.personal_workspace.id`` through
``app_services`` to ``KnowledgeBase`` and ``summary_engine`` (Stages 3b/4).
As of Stage 6e there is no implicit fallback: KB / summary methods require
``workspace_id`` at every call site, and the legacy ``DEFAULT_WORKSPACE_ID``
constant is gone.

Endpoint access tiers:

* **Public** (no auth required): ``/api/health``, ``/api/auth/register``,
  ``/api/auth/login``.
* **Authenticated** (any logged-in user): every endpoint that uses the
  ``get_current_workspace_id`` dependency (transitively requires auth) plus
  ``/api/auth/me`` and ``/api/auth/logout``.
* **Superuser-only** (``is_superuser=True``): ``/api/diagnostics/*`` and
  ``/api/admin/*`` (audit log + system stats).

``get_current_workspace_id`` resolves to ``current_user.personal_workspace.id``
on every request, so a session cookie is the *sole* source of truth for which
workspace a caller can see. Even if a future bug let a client pass an
arbitrary ``workspace_id`` in the URL, the dependency would still return the
authenticated user's own workspace.
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import config
from src import app_services as services
from src import audit_service
from src import auth_service
from src.auth_api import router as auth_router
from src.auth_service import get_current_user, require_superuser
from src.rate_limit import limiter
from src.db import get_db
from src.db_models import User
from src.api_models import (
    AdminStats,
    AuditEventOut,
    AuditLogResponse,
    ReconcileResponse,
    ChatRequest,
    ChatResponse,
    MaterialActionResponse,
    MaterialProgressResponse,
    MaterialsResponse,
    SectionsResponse,
    SummaryExportRequest,
    SummaryRequest,
    SummaryResponse,
    SystemStatus,
)


app = FastAPI(title="BonchMind Pro API", version="0.1.0")

# Rate limiting (Stage 9a): register the shared limiter + 429 handler. Per-route
# limits are applied with @limiter.limit on auth/chat/upload.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Stage 9a: warn loudly if a prod-like deployment (Postgres) serves the auth
# cookie without the Secure flag. Stays quiet for local dev/CI on SQLite.
if not config.AUTH_COOKIE_SECURE and config.DATABASE_URL.startswith("postgres"):
    logging.getLogger("bonchmind.security").warning(
        "AUTH_COOKIE_SECURE is false but DATABASE_URL looks like production "
        "(Postgres). Set AUTH_COOKIE_SECURE=true when serving over HTTPS so the "
        "auth cookie is not sent over plain HTTP."
    )

app.include_router(auth_router)


def get_current_workspace_id(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> str:
    """Resolve the authenticated user's personal workspace id.

    Transitively enforces authentication via ``get_current_user`` — endpoints
    that take this dependency get the auth gate for free, so we don't need
    ``dependencies=[Depends(get_current_user)]`` separately.
    """
    workspace = auth_service.get_personal_workspace(db, current_user)
    return workspace.id


WorkspaceId = Annotated[str, Depends(get_current_workspace_id)]
_ADMIN = [Depends(require_superuser)]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


_MAX_UPLOAD_BYTES = getattr(config, "MAX_UPLOAD_BYTES", 50 * 1024 * 1024)


async def _read_upload_within_limit(request: Request, file: UploadFile) -> bytes:
    """Read an upload without letting a huge file OOM the server (Stage 9a).

    Two layers: a fast Content-Length reject before touching the body, then a
    streamed read with a hard cap so a missing/lying Content-Length still can't
    buffer more than the limit. Oversized uploads raise 413; the per-file size
    check in the service layer stays as defence-in-depth.
    """
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="file_too_large")
        except ValueError:
            pass  # malformed header — fall through to the streamed cap

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB at a time
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


@app.get("/api/health")
def health():
    """Public liveness probe — used by uptime monitoring."""
    return {"status": "ok"}


@app.get("/api/system/status", response_model=SystemStatus)
def system_status(workspace_id: WorkspaceId):
    return services.get_system_status(workspace_id)


@app.get("/api/materials", response_model=MaterialsResponse)
def materials(workspace_id: WorkspaceId):
    return services.list_materials(workspace_id)


@app.post("/api/materials/upload", response_model=MaterialActionResponse)
@limiter.limit(config.RATE_LIMIT_UPLOAD)
async def material_upload(
    workspace_id: WorkspaceId,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    file: UploadFile = File(...),
):
    """Upload requires both ``workspace_id`` (where the file is indexed) and
    ``user.id`` (recorded as ``Document.owner_user_id``). ``workspace_id`` is
    transitively derived from ``current_user`` via ``get_current_workspace_id``,
    but we keep ``current_user`` as a separate dependency so the owner id is
    explicit at the call site."""
    content = await _read_upload_within_limit(request, file)
    result = services.start_upload_material_service(
        workspace_id, current_user.id, file.filename, content
    )
    audit_service.record(
        audit_service.ACTION_UPLOAD,
        user_id=current_user.id,
        workspace_id=workspace_id,
        target=file.filename or "",
        ip=_client_ip(request),
    )
    return result


@app.get("/api/materials/progress", response_model=MaterialProgressResponse)
def material_progress(workspace_id: WorkspaceId):
    return services.get_material_progress(workspace_id)


@app.post("/api/materials/cancel", response_model=MaterialActionResponse)
def material_cancel(workspace_id: WorkspaceId):
    """Request cancellation of the workspace's in-flight material job."""
    return services.cancel_material_service(workspace_id)


@app.get(
    "/api/materials/{file_name}/sections",
    response_model=SectionsResponse,
)
def material_sections(workspace_id: WorkspaceId, file_name: str):
    return services.list_sections(workspace_id, file_filter=file_name)


@app.post("/api/materials/reindex", response_model=MaterialActionResponse)
def materials_reindex(
    workspace_id: WorkspaceId,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
):
    result = services.start_reindex_material_service(workspace_id)
    audit_service.record(
        audit_service.ACTION_REINDEX,
        user_id=current_user.id,
        workspace_id=workspace_id,
        target="*",
        ip=_client_ip(request),
    )
    return result


@app.post(
    "/api/materials/{file_name}/reindex",
    response_model=MaterialActionResponse,
)
def material_reindex(
    workspace_id: WorkspaceId,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    file_name: str,
):
    result = services.start_reindex_material_service(workspace_id, file_name=file_name)
    audit_service.record(
        audit_service.ACTION_REINDEX,
        user_id=current_user.id,
        workspace_id=workspace_id,
        target=file_name,
        ip=_client_ip(request),
    )
    return result


@app.delete(
    "/api/materials/{file_name}",
    response_model=MaterialActionResponse,
)
def material_delete(
    workspace_id: WorkspaceId,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    file_name: str,
):
    result = services.start_delete_material_service(workspace_id, file_name)
    audit_service.record(
        audit_service.ACTION_DELETE,
        user_id=current_user.id,
        workspace_id=workspace_id,
        target=file_name,
        ip=_client_ip(request),
    )
    return result


@app.post("/api/summaries", response_model=SummaryResponse)
def summaries(workspace_id: WorkspaceId, request: SummaryRequest):
    return services.generate_summary_service(workspace_id, request)


@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit(config.RATE_LIMIT_CHAT)
def chat(workspace_id: WorkspaceId, request: Request, payload: ChatRequest):
    return services.chat_service(workspace_id, payload)


@app.post("/api/exports/summary")
def export_summary(workspace_id: WorkspaceId, request: SummaryExportRequest):
    # Stage 3b: workspace_id is accepted at the endpoint to keep the auth
    # gate in place even though DOCX assembly is workspace-agnostic.
    del workspace_id
    path = services.export_summary_docx_service(request)
    if not path:
        return JSONResponse(status_code=400, content={"error": "empty_summary"})

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=Path(path).name,
    )


@app.get("/api/diagnostics/latest", dependencies=_ADMIN)
def diagnostics_latest():
    return {"text": services.get_latest_diagnostics_text()}


@app.get("/api/diagnostics/latest.json", dependencies=_ADMIN)
def diagnostics_latest_json():
    return services.get_latest_diagnostics_json() or {}


# ---------------------------------------------------------------------------
# Admin (superuser-only). Audit log + system stats for the admin screen
# (Stage 9b). Both gated by ``_ADMIN`` (``require_superuser``): a regular
# authenticated user gets 403, an anonymous caller gets 401.
# ---------------------------------------------------------------------------


@app.get("/api/admin/audit", response_model=AuditLogResponse, dependencies=_ADMIN)
def admin_audit(limit: int = 50):
    """Most recent audit events, newest first. ``limit`` is clamped server-side
    (see ``audit_service.list_recent``); no pagination yet (Stage 9b scope)."""
    events = audit_service.list_recent(limit)
    return AuditLogResponse(events=[AuditEventOut.model_validate(e) for e in events])


@app.get("/api/admin/stats", response_model=AdminStats, dependencies=_ADMIN)
def admin_stats():
    """Instance-wide counts (users / workspaces / documents / audit events)."""
    return services.get_admin_stats()


@app.post("/api/admin/reconcile", response_model=ReconcileResponse, dependencies=_ADMIN)
def admin_reconcile(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Scrub orphan KB chunks instance-wide (Stage 9c).

    Reconciles ChromaDB against the ``Document`` table for every workspace,
    removing chunks whose ``document_id`` has no backing row. Instance-wide by
    design (like `/api/admin/stats`), so it never takes a workspace id from the
    client. Idempotent."""
    result = services.reconcile_database_service()
    audit_service.record(
        audit_service.ACTION_RECONCILE,
        user_id=current_user.id,
        target="*",
        ip=_client_ip(request),
    )
    return result
