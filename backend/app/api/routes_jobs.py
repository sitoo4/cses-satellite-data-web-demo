from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request


router = APIRouter()


@router.get("/jobs/{job_id:path}")
def get_job(request: Request, job_id: str) -> dict:
    try:
        return request.app.state.jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "job_id": job_id}) from exc
