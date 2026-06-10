"""FastAPI entrypoint for BonchMind Pro.

Stage 3a wires authentication into every non-public endpoint via FastAPI
dependencies. Endpoint access tiers:

* **Public** (no auth required): ``/api/health``, ``/api/auth/register``,
  ``/api/auth/login``.
* **Authenticated** (any logged-in user): everything else in this module —
  materials CRUD, chat, summaries, exports, system status, ``/api/auth/me``,
  ``/api/auth/logout``.
* **Superuser-only** (``is_superuser=True``): ``/api/diagnostics/*`` — leaks
  internal RAG state, not for end-users.

In Stage 3a the auth gate is added as a "marker" dependency (we don't pass
``current_user`` to the service layer yet); Stage 3b will plumb
``workspace_id`` through to ``app_services``.
"""

from pathlib import Path

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from src import app_services as services
from src.auth_api import router as auth_router
from src.auth_service import get_current_user, require_superuser
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


# Reusable dependency lists so each endpoint signature stays terse and the
# access tier is immediately obvious at the route definition.
_AUTH = [Depends(get_current_user)]
_ADMIN = [Depends(require_superuser)]


@app.get("/api/health")
def health():
    """Public liveness probe — used by uptime monitoring."""
    return {"status": "ok"}


@app.get("/api/system/status", response_model=SystemStatus, dependencies=_AUTH)
def system_status():
    return services.get_system_status()


@app.get("/api/materials", response_model=MaterialsResponse, dependencies=_AUTH)
def materials():
    return services.list_materials()


@app.post(
    "/api/materials/upload",
    response_model=MaterialActionResponse,
    dependencies=_AUTH,
)
async def material_upload(file: UploadFile = File(...)):
    content = await file.read()
    return services.start_upload_material_service(file.filename, content)


@app.get(
    "/api/materials/progress",
    response_model=MaterialProgressResponse,
    dependencies=_AUTH,
)
def material_progress():
    return services.get_material_progress()


@app.get(
    "/api/materials/{file_name}/sections",
    response_model=SectionsResponse,
    dependencies=_AUTH,
)
def material_sections(file_name: str):
    return services.list_sections(file_filter=file_name)


@app.post(
    "/api/materials/reindex",
    response_model=MaterialActionResponse,
    dependencies=_AUTH,
)
def materials_reindex():
    return services.start_reindex_material_service()


@app.post(
    "/api/materials/{file_name}/reindex",
    response_model=MaterialActionResponse,
    dependencies=_AUTH,
)
def material_reindex(file_name: str):
    return services.start_reindex_material_service(file_name=file_name)


@app.delete(
    "/api/materials/{file_name}",
    response_model=MaterialActionResponse,
    dependencies=_AUTH,
)
def material_delete(file_name: str):
    return services.start_delete_material_service(file_name)


@app.post("/api/summaries", response_model=SummaryResponse, dependencies=_AUTH)
def summaries(request: SummaryRequest):
    return services.generate_summary_service(request)


@app.post("/api/chat", response_model=ChatResponse, dependencies=_AUTH)
def chat(request: ChatRequest):
    return services.chat_service(request)


@app.post("/api/exports/summary", dependencies=_AUTH)
def export_summary(request: SummaryExportRequest):
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
