from __future__ import annotations

from typing import Any

from app.core.artifacts import ArtifactRegistry
from app.core.config import AppConfig
from app.datasources.base import DataSource
from app.datasources.cses_hpm import CsesHpmDataSource


class DataSourceRegistry:
    def __init__(self, config: AppConfig, artifacts: ArtifactRegistry) -> None:
        self._sources: dict[str, DataSource] = {
            "cses_hpm": CsesHpmDataSource(config, artifacts),
        }

    def list_summaries(self) -> list[dict[str, Any]]:
        return [source.summary() for source in self._sources.values()]

    def get(self, name: str) -> DataSource:
        if name not in self._sources:
            raise KeyError(name)
        return self._sources[name]
