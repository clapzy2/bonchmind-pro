"""FastAPI entrypoint for BonchMind Pro.

Stage 3a added authentication gates on every non-public endpoint.
Stage 3b plumbs ``workspace_id`` from ``current_user.personal_workspace.id``
through ``app_services`` to ``KnowledgeBase``, removing the
``config.DEFAULT_WORKSPACE_ID`` bridge from the authenticated API flow.

Endpoint access tiers:

* **Public** (no auth required): ``/api/health``, ``/api/auth/register``,
  ``/api/auth/login``.
* **Authenticated** (any logged-in user): every endpoint that uses the
  ``get_current_workspace_id`` dependency (transitively requires auth) plus
  ``/api/auth/me`` and ``/api/auth/logout``.
* **Superuser-only** (``is_superuser=True``): ``/api/diagnostics/*``.

``get_current_workspace_id`` resolves to ``current_user.personal_workspace.id``
on every request, so a session cookie is the *sole* source of truth for which
workspace a caller can see. Even if a future bug let a client pass an
arbitrary ``workspace_id`` in the URL, the dependency would still return the
authenticated user's own workspace.
"""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from src import app_services as services
from src import auth_service
from src.auth_api import router as auth_router
from src.auth_service import get_current_user, require_superuser
from src.db import get_db
from src.db_models import User
from src.api_models import (
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
async def material_upload(workspace_id: WorkspaceId, file: UploadFile = File(...)):
    content = await file.read()
    return services.start_upload_material_service(workspace_id, file.filename, content)


@app.get("/api/materials/progress", response_model=MaterialProgressResponse)
def material_progress(workspace_id: WorkspaceId):
    return services.get_material_progress(workspace_id)


@app.get(
    "/api/materials/{file_name}/sections",
    response_model=SectionsResponse,
)
def material_sections(workspace_id: WorkspaceId, file_name: str):
    return services.list_sections(workspace_id, file_filter=file_name)


@app.post("/api/materials/reindex", response_model=MaterialActionResponse)
def materials_reindex(workspace_id: WorkspaceId):
    return services.start_reindex_material_service(workspace_id)


@app.post(
    "/api/materials/{file_name}/reindex",
    response_model=MaterialActionResponse,
)
def material_reindex(workspace_id: WorkspaceId, file_name: str):
    return services.start_reindex_material_service(workspace_id, file_name=file_name)


@app.delete(
    "/api/materials/{file_name}",
    response_model=MaterialActionResponse,
)
def material_delete(workspace_id: WorkspaceId, file_name: str):
    return services.start_delete_material_service(workspace_id, file_name)


@app.post("/api/summaries", response_model=SummaryResponse)
def summaries(workspace_id: WorkspaceId, request: SummaryRequest):
    return services.generate_summary_service(workspace_id, request)


@app.post("/api/chat", response_model=ChatResponse)
def chat(workspace_id: WorkspaceId, request: ChatRequest):
    return services.chat_service(workspace_id, request)


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
