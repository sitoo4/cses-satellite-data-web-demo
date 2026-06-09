from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DataSource(ABC):
    name: str
    label: str

    @abstractmethod
    def summary(self) -> dict[str, Any]:
        raise NotImplementedError

    def list_files(self, filters: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def metadata(self, file_id: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def variables(self, file_id: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def plot_catalog(self, file_id: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def subset(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def timeseries(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def plot(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def export(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def stats(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
