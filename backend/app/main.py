from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api.routes_artifacts import router as artifacts_router
from app.api.routes_cses_hpm_uploads import router as cses_hpm_uploads_router
from app.api.routes_datasources import router as datasources_router
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.core.artifacts import ArtifactRegistry
from app.core.config import load_config
from app.core.jobs import JobRegistry
from app.datasources.registry import DataSourceRegistry
from app.services.cses_hpm_uploads import CsesHpmUploadService


def create_app(config_path: Path | str | None = None) -> FastAPI:
    config = load_config(config_path)
    app = FastAPI(title="Satellite Data Web API", version="0.1.0")
    app.state.config = config
    app.state.artifacts = ArtifactRegistry()
    app.state.jobs = JobRegistry()
    app.state.registry = DataSourceRegistry(config, app.state.artifacts)
    app.state.cses_hpm_uploads = CsesHpmUploadService(config, app.state.artifacts)
    app.include_router(health_router, prefix="/api")
    app.include_router(cses_hpm_uploads_router, prefix="/api")
    app.include_router(datasources_router, prefix="/api")
    app.include_router(artifacts_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    return app


app = create_app()
