from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter()


def get_datasource(request: Request, name: str):
    try:
        return request.app.state.registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "unknown_datasource", "name": name}) from exc


def register_completed_job(request: Request, *, name: str, kind: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    job = request.app.state.jobs.register_completed(kind=kind, datasource=name, request_payload=payload, result=result)
    return {**result, "job_id": job["job_id"]}


@router.get("/datasources")
def list_datasources(request: Request) -> dict[str, Any]:
    return {"datasources": request.app.state.registry.list_summaries()}


@router.get("/datasources/{name}/files")
def list_files(
    request: Request,
    name: str,
    limit: int | None = Query(default=None),
    year: str | None = Query(default=None),
) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        return source.list_files({"limit": limit, "year": year})
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.get("/datasources/{name}/metadata")
def metadata(request: Request, name: str, file_id: str | None = None) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        return source.metadata(file_id=file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "metadata_not_found", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_file_id", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.get("/datasources/{name}/variables")
def variables(request: Request, name: str, file_id: str | None = None) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        return source.variables(file_id=file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "metadata_not_found", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_file_id", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.get("/datasources/{name}/plot-catalog")
def plot_catalog(request: Request, name: str, file_id: str | None = None) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        return source.plot_catalog(file_id=file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "metadata_not_found", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_file_id", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.post("/datasources/{name}/subset")
def subset(request: Request, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        return source.subset(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": str(exc)}) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.post("/datasources/{name}/timeseries")
def timeseries(request: Request, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        return source.timeseries(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": str(exc)}) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.post("/datasources/{name}/plot")
def plot(request: Request, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        result = source.plot(payload)
        return register_completed_job(request, name=name, kind="plot", payload=payload, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "plot_not_found", "message": str(exc)}) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.post("/datasources/{name}/export")
def export(request: Request, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        result = source.export(payload)
        return register_completed_job(request, name=name, kind="export", payload=payload, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": str(exc)}) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc


@router.post("/datasources/{name}/stats")
def stats(request: Request, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = get_datasource(request, name)
    try:
        result = source.stats(payload)
        return register_completed_job(request, name=name, kind="stats", payload=payload, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": str(exc)}) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"code": "not_implemented", "name": name}) from exc
