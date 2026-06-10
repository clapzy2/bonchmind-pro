"""FastAPI entrypoint for BonchMind Pro."""

from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from src import app_services as services
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/system/status", response_model=SystemStatus)
def system_status():
    return services.get_system_status()


@app.get("/api/materials", response_model=MaterialsResponse)
def materials():
    return services.list_materials()


@app.post("/api/materials/upload", response_model=MaterialActionResponse)
async def material_upload(file: UploadFile = File(...)):
    content = await file.read()
    return services.start_upload_material_service(file.filename, content)


@app.get("/api/materials/progress", response_model=MaterialProgressResponse)
def material_progress():
    return services.get_material_progress()


@app.get("/api/materials/{file_name}/sections", response_model=SectionsResponse)
def material_sections(file_name: str):
    return services.list_sections(file_filter=file_name)


@app.post("/api/materials/reindex", response_model=MaterialActionResponse)
def materials_reindex():
    return services.start_reindex_material_service()


@app.post("/api/materials/{file_name}/reindex", response_model=MaterialActionResponse)
def material_reindex(file_name: str):
    return services.start_reindex_material_service(file_name=file_name)


@app.delete("/api/materials/{file_name}", response_model=MaterialActionResponse)
def material_delete(file_name: str):
    return services.start_delete_material_service(file_name)


@app.post("/api/summaries", response_model=SummaryResponse)
def summaries(request: SummaryRequest):
    return services.generate_summary_service(request)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    return services.chat_service(request)


@app.post("/api/exports/summary")
def export_summary(request: SummaryExportRequest):
    path = services.export_summary_docx_service(request)
    if not path:
        return JSONResponse(status_code=400, content={"error": "empty_summary"})

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=Path(path).name,
    )


@app.get("/api/diagnostics/latest")
def diagnostics_latest():
    return {"text": services.get_latest_diagnostics_text()}


@app.get("/api/diagnostics/latest.json")
def diagnostics_latest_json():
    return services.get_latest_diagnostics_json() or {}
