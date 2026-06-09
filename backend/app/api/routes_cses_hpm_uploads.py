from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile


router = APIRouter()


def upload_service(request: Request):
    return request.app.state.cses_hpm_uploads


@router.post("/cses-hpm/uploads")
async def create_upload_session(request: Request, files: list[UploadFile] = File(...)) -> dict[str, Any]:
    try:
        uploads = [(file.filename or "upload.h5", await file.read()) for file in files]
        return upload_service(request).create_session(uploads)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_upload", "message": str(exc)}) from exc


@router.get("/cses-hpm/uploads/{session_id}")
def get_upload_session(request: Request, session_id: str) -> dict[str, Any]:
    try:
        return upload_service(request).get_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "upload_session_not_found", "message": session_id}) from exc


@router.post("/cses-hpm/uploads/{session_id}/plot")
def plot_upload_session(request: Request, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return upload_service(request).plot(session_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "upload_session_not_found", "message": session_id}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_plot_request", "message": str(exc)}) from exc


@router.post("/cses-hpm/uploads/{session_id}/export")
def export_upload_session(request: Request, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return upload_service(request).export(session_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "upload_session_not_found", "message": session_id}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_export_request", "message": str(exc)}) from exc


@router.post("/sessions/{session_id}/statistics")
def compute_upload_session_statistics(request: Request, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return upload_service(request).statistics(session_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "upload_session_not_found", "message": session_id}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_statistics_request", "message": str(exc)}) from exc
