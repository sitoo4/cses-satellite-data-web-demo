from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_APP_ROOT = Path("/Volumes/Elements/satellite_data_web")


@dataclass(frozen=True)
class AppConfig:
    app_root: Path
    cluster_raw_root: Path
    cluster_processed_root: Path
    cses_hpm_root: Path
    outputs_root: Path

    @property
    def cses_inspection_root(self) -> Path:
        return self.outputs_root / "cses_hpm_inspection"


def _path_value(payload: dict[str, Any], key: str, default: Path) -> Path:
    raw = os.environ.get(key.upper()) or payload.get(key) or str(default)
    return Path(str(raw)).expanduser()


def load_config(config_path: Path | str | None = None) -> AppConfig:
    app_root = DEFAULT_APP_ROOT
    payload: dict[str, Any] = {}
    path = Path(config_path) if config_path is not None else app_root / "local_config.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        app_root = path.parent.parent if path.parent.name == "backend" else path.parent
    return AppConfig(
        app_root=app_root,
        cluster_raw_root=_path_value(payload, "cluster_raw_root", Path("/Volumes/Elements/data/cluster")),
        cluster_processed_root=_path_value(payload, "cluster_processed_root", Path("/Volumes/Elements/data/idlpython_v2")),
        cses_hpm_root=_path_value(payload, "cses_hpm_root", Path("/Users/foursoils/Downloads/HPM")),
        outputs_root=_path_value(payload, "outputs_root", app_root / "outputs"),
    )
