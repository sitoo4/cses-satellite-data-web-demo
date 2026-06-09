from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    path: Path
    media_type: str
    label: str


class ArtifactRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Artifact] = {}

    def register(self, artifact_id: str, path: Path, *, media_type: str, label: str) -> dict:
        artifact = Artifact(artifact_id=artifact_id, path=path, media_type=media_type, label=label)
        self._items[artifact_id] = artifact
        return {
            "artifact_id": artifact_id,
            "label": label,
            "media_type": media_type,
            "path": str(path),
            "exists": path.exists(),
        }

    def get(self, artifact_id: str) -> Artifact:
        if artifact_id not in self._items:
            raise KeyError(artifact_id)
        return self._items[artifact_id]
