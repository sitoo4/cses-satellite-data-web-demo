from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse


router = APIRouter()


@router.get("/artifacts/{artifact_id:path}")
def get_artifact(request: Request, artifact_id: str, download: bool = False):
    try:
        artifact = request.app.state.artifacts.get(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "artifact_not_found", "artifact_id": artifact_id}) from exc
    if not artifact.path.exists() or not artifact.path.is_file():
        raise HTTPException(status_code=404, detail={"code": "artifact_file_missing", "artifact_id": artifact_id})
    if download:
        response = FileResponse(artifact.path, media_type=artifact.media_type, filename=artifact.path.name)
        response.headers["Content-Disposition"] = f'attachment; filename="{artifact.path.name}"'
        return response
    if artifact.media_type in {"text/html", "image/png", "image/jpeg", "image/webp", "application/json", "text/markdown"}:
        return FileResponse(artifact.path, media_type=artifact.media_type)
    response = FileResponse(artifact.path, media_type=artifact.media_type, filename=artifact.path.name)
    response.headers["Content-Disposition"] = f'attachment; filename="{artifact.path.name}"'
    return response
