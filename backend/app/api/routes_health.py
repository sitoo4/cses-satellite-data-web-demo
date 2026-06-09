from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    config = request.app.state.config
    return {
        "status": "ok",
        "paths": {
            "cluster_raw_root": {"path": str(config.cluster_raw_root), "exists": config.cluster_raw_root.exists()},
            "cluster_processed_root": {
                "path": str(config.cluster_processed_root),
                "exists": config.cluster_processed_root.exists(),
            },
            "cses_hpm_root": {"path": str(config.cses_hpm_root), "exists": config.cses_hpm_root.exists()},
            "outputs_root": {"path": str(config.outputs_root), "exists": config.outputs_root.exists()},
        },
    }
