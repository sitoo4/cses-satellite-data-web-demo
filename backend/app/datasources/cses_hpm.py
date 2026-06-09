from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from app.core.artifacts import ArtifactRegistry
from app.core.config import AppConfig
from app.datasources.base import DataSource
from app.services.plotting import (
    plot_cadence_overview,
    plot_cses_trajectory_overview,
    plot_magnetic_timeseries,
    plot_quality_overview,
    plot_scalar_timeseries,
    plot_trajectory_2d,
    plot_trajectory_3d,
    plot_vector_overview,
)
from app.services.table_export import (
    bounded_sample_range,
    build_export_manifest,
    export_extension,
    export_media_type,
    numeric_stats,
    numeric_stats_extended,
    request_digest,
    sanitize_id,
    stats_extension,
    stats_media_type,
    write_manifest,
    write_stats_artifact,
    write_table_export,
)


CSES_UNSUPPORTED_FEATURES = {
    "electric_field": "not available for CSES HPM magnetometer-only datasource",
    "solar_wind": "not available for CSES HPM magnetometer-only datasource",
    "spectrogram": "requires confirmed time semantics, cadence, magnetic variable, and quality masking",
}


def json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return value


class CsesHpmDataSource(DataSource):
    name = "cses_hpm"
    label = "CSES-01 HPM H5 files"
    datasource_type = "CSES-01 HPM magnetometer-only H5 datasource"

    def __init__(self, config: AppConfig, artifacts: ArtifactRegistry) -> None:
        self.config = config
        self.artifacts = artifacts

    @property
    def hpm_root(self) -> Path:
        return self.config.cses_hpm_root

    @property
    def inspection_root(self) -> Path:
        return self.config.cses_inspection_root

    def summary(self) -> dict[str, Any]:
        index = self._inspection_index()
        return {
            "name": self.name,
            "label": self.label,
            "status": "available" if self.hpm_root.exists() else "missing",
            "root_status": {
                "hpm_root": "confirmed" if self.hpm_root.exists() else "missing",
                "inspection_root": "confirmed" if self.inspection_root.exists() else "missing",
            },
            "capabilities": {
                "list_files": True,
                "metadata": True,
                "variables": True,
                "timeseries": True,
                "plot_existing": False,
                "plot_generate": True,
                "subset": True,
                "export_csv": True,
                "export_dat": True,
                "export_h5": True,
                "export_cdf": False,
                "stats": True,
            },
            "inspection": {
                "file_count": index.get("file_count", 0) if index else 0,
                "ok_count": index.get("ok_count", 0) if index else 0,
                "error_count": index.get("error_count", 0) if index else 0,
                "index_exists": bool(index),
            },
            "unsupported": [{"feature": feature, "reason": reason} for feature, reason in CSES_UNSUPPORTED_FEATURES.items()],
        }

    def list_files(self, filters: dict[str, Any]) -> dict[str, Any]:
        limit = filters.get("limit")
        index = self._inspection_index()
        files: list[dict[str, Any]] = []
        indexed: dict[str, dict[str, Any]] = {}
        if index:
            for item in index.get("results", []):
                file_info = item.get("file", {})
                rel = str(file_info.get("relative_path", ""))
                if rel:
                    indexed[rel] = item

        if indexed:
            iterable = sorted(indexed.items())
            for rel, item in iterable:
                if limit is not None and len(files) >= int(limit):
                    break
                source = self._safe_file_path(rel)
                summary = self._summary_path(rel)
                files.append(
                    {
                        "file_id": rel,
                        "name": Path(rel).name,
                        "source_path": str(source),
                        "size_bytes": item.get("file", {}).get("size_bytes", source.stat().st_size if source.exists() else 0),
                        "inspection": {
                            "status": item.get("status", "unknown"),
                            "summary_exists": summary.exists(),
                            "report_exists": (summary.parent / "report.md").exists(),
                        },
                    }
                )
        elif self.hpm_root.exists():
            paths = sorted(path for path in self.hpm_root.rglob("*.h5") if path.is_file() and not path.name.startswith("._"))
            for path in paths[: int(limit) if limit is not None else None]:
                rel = str(path.relative_to(self.hpm_root))
                files.append(
                    {
                        "file_id": rel,
                        "name": path.name,
                        "source_path": str(path),
                        "size_bytes": path.stat().st_size,
                        "inspection": {"status": "inspection_required", "summary_exists": False, "report_exists": False},
                    }
                )
        return {"datasource": self.name, "files": files}

    def metadata(self, file_id: str | None = None) -> dict[str, Any]:
        if not file_id:
            return self.summary()
        summary = self._load_summary(file_id)
        return {
            "datasource": self.name,
            "file": summary.get("file", {}),
            "dataset_count": len(summary.get("datasets", [])),
            "group_count": len(summary.get("groups", [])),
            "root_attrs": summary.get("root_attrs", {}),
            "datasets": [
                {
                    "path": item.get("path"),
                    "shape": item.get("shape"),
                    "dtype": item.get("dtype"),
                    "attrs": item.get("attrs", {}),
                    "metadata_attrs": item.get("metadata_attrs", {}),
                    "sample_stats": item.get("sample_stats", {}),
                }
                for item in summary.get("datasets", [])
            ],
            "candidates": summary.get("candidates", {}),
            "time_summary": self._metadata_time_summary(file_id, summary),
            "quality_summary": self._metadata_quality_summary(file_id, summary),
            "report_artifact": self._inspection_report_artifact(file_id),
        }

    def variables(self, file_id: str | None = None) -> dict[str, Any]:
        if not file_id:
            return {"datasource": self.name, "variables": [], "status": "file_id_required"}
        summary = self._load_summary(file_id)
        kind_by_path: dict[str, str] = {}
        candidate_by_path: dict[str, dict[str, Any]] = {}
        for kind, candidates in summary.get("candidates", {}).items():
            for candidate in candidates:
                path = candidate.get("path")
                if path and path not in kind_by_path:
                    kind_by_path[path] = kind
                    candidate_by_path[path] = candidate

        variables: list[dict[str, Any]] = []
        for item in summary.get("datasets", []):
            path = item.get("path")
            attrs = item.get("attrs", {})
            unit = attrs.get("Units") or attrs.get("units") or attrs.get("Unit") or attrs.get("unit")
            variables.append(
                {
                    "name": path,
                    "path": path,
                    "label": str(path).strip("/"),
                    "source": "h5",
                    "data_kind": kind_by_path.get(path, "dataset"),
                    "confidence": candidate_by_path.get(path, {}).get("confidence", "confirmed_from_dataset_metadata"),
                    "evidence": candidate_by_path.get(path, {}).get("evidence", []),
                    "shape": item.get("shape"),
                    "dtype": item.get("dtype"),
                    "unit": unit,
                    "attrs": attrs,
                }
            )
        return {"datasource": self.name, "file_id": file_id, "variables": variables}

    def plot_catalog(self, file_id: str | None = None) -> dict[str, Any]:
        summary = self._load_summary(file_id) if file_id else {"candidates": {}}
        magnetic = self._candidate_path(summary, "magnetic_vector") or "/B_FGM"
        scalar = self._candidate_path(summary, "magnetic_scalar")
        time_field = self._candidate_path(summary, "time") or "/UTC_TIME"
        flag = self._candidate_path(summary, "quality_flag") or "/FLAG_MT"
        lat = self._candidate_path(summary, "latitude") or "/GEO_LAT"
        lon = self._candidate_path(summary, "longitude") or "/GEO_LON"
        alt = self._candidate_path(summary, "altitude") or "/ALTITUDE"
        dataset_paths = {str(item.get("path")) for item in summary.get("datasets", [])}
        has = lambda path: (not file_id) or path in dataset_paths
        trajectory_enabled = has(lat) and has(lon) and has(alt)
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": file_id,
            "plots": [
                {
                    "plot_type": "cses_hpm_magnetic_overview",
                    "display_name": "HPM magnetic overview",
                    "description": "HPM vector magnetic field components and magnitude from inferred/confirmed H5 fields.",
                    "enabled": has(magnetic),
                    "disabled_reason": None if has(magnetic) else f"missing magnetic vector field {magnetic}",
                    "required_fields": [magnetic, time_field],
                    "confirmed_fields": [],
                    "inferred_fields": [magnetic],
                    "output_group": "cses_hpm",
                },
                {
                    "plot_type": "cses_hpm_quality_overview",
                    "display_name": "HPM quality overview",
                    "description": "Quality flag by sample/time and flag distribution.",
                    "enabled": has(flag),
                    "disabled_reason": None if has(flag) else f"missing quality flag field {flag}",
                    "required_fields": [flag],
                    "confirmed_fields": [],
                    "inferred_fields": [flag],
                    "output_group": "cses_hpm",
                },
                {
                    "plot_type": "cses_hpm_trajectory_overview",
                    "display_name": "HPM trajectory overview",
                    "description": "Geographic latitude, longitude, and altitude coverage from H5 fields.",
                    "enabled": trajectory_enabled,
                    "disabled_reason": None if trajectory_enabled else "requires geographic latitude, longitude, and altitude fields in the H5 file",
                    "required_fields": [lat, lon, alt],
                    "confirmed_fields": [],
                    "inferred_fields": [lat, lon, alt],
                    "output_group": "cses_hpm",
                },
                {
                    "plot_type": "cses_hpm_cadence_overview",
                    "display_name": "HPM cadence diagnostics",
                    "description": "Sampling interval sequence, histogram, duplicate count, and gap diagnostics for inferred time semantics.",
                    "enabled": has(time_field),
                    "disabled_reason": None if has(time_field) else f"missing time field {time_field}",
                    "required_fields": [time_field],
                    "confirmed_fields": [],
                    "inferred_fields": [time_field],
                    "output_group": "cses_hpm",
                },
                {
                    "plot_type": "cses_hpm_batch_statistics_overview",
                    "display_name": "HPM batch statistics",
                    "description": "Selected-file batch statistics using sorted and deduplicated candidate UTC_TIME rows.",
                    "enabled": True,
                    "disabled_reason": None,
                    "required_fields": [magnetic, time_field],
                    "confirmed_fields": [],
                    "inferred_fields": [magnetic, time_field, flag, lat, lon, alt] if scalar is None else [magnetic, scalar, time_field, flag, lat, lon, alt],
                    "output_group": "cses_hpm",
                },
                {
                    "plot_type": "cses_hpm_spectrogram_overview",
                    "display_name": "HPM spectrogram",
                    "description": "Disabled until HPM time semantics, cadence, magnetic variable, and quality masking are confirmed.",
                    "enabled": False,
                    "disabled_reason": CSES_UNSUPPORTED_FEATURES["spectrogram"],
                    "required_fields": [magnetic, time_field, flag],
                    "confirmed_fields": [],
                    "inferred_fields": [magnetic, time_field, flag],
                    "output_group": "cses_hpm",
                },
                {
                    "plot_type": "cses_hpm_electric_field_overview",
                    "display_name": "HPM electric field",
                    "description": "Disabled because the HPM datasource is magnetometer-only.",
                    "enabled": False,
                    "disabled_reason": CSES_UNSUPPORTED_FEATURES["electric_field"],
                    "required_fields": [],
                    "confirmed_fields": [],
                    "inferred_fields": [],
                    "output_group": "cses_hpm",
                },
                {
                    "plot_type": "cses_hpm_solar_wind_overview",
                    "display_name": "HPM solar wind",
                    "description": "Disabled because CSES HPM files do not contain OMNI/solar-wind context.",
                    "enabled": False,
                    "disabled_reason": CSES_UNSUPPORTED_FEATURES["solar_wind"],
                    "required_fields": [],
                    "confirmed_fields": [],
                    "inferred_fields": [],
                    "output_group": "cses_hpm",
                },
            ],
        }

    def subset(self, request: dict[str, Any]) -> dict[str, Any]:
        file_id = str(request.get("file_id") or "")
        variables = [str(item) for item in request.get("variables", [])]
        range_spec = request.get("range", {})
        source = self._safe_file_path(file_id)
        out_vars: list[dict[str, Any]] = []
        with h5py.File(source, "r") as h5:
            range_payload = self._resolve_range(h5, range_spec, default_limit=200, max_samples=10000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            preview_limit = max(0, int(request.get("preview_limit", end - start)))
            read_end = min(end, start + preview_limit)
            for variable in variables:
                dataset = h5[variable.lstrip("/")]
                data = self._read_dataset_range(dataset, start, read_end)
                out_vars.append(
                    {
                        "path": "/" + variable.strip("/"),
                        "shape": list(dataset.shape),
                        "dtype": str(dataset.dtype),
                        "data": json_safe(data),
                    }
                )
        response_range = {**range_payload, "preview_end_index": read_end, "sample_count": max(0, read_end - start)}
        return {
            "datasource": self.name,
            "file_id": file_id,
            "range": response_range,
            "variables": out_vars,
        }

    def timeseries(self, request: dict[str, Any]) -> dict[str, Any]:
        file_id = str(request.get("file_id") or "")
        variables = [str(item) for item in request.get("variables", [])]
        source = self._safe_file_path(file_id)
        out_vars: list[dict[str, Any]] = []
        with h5py.File(source, "r") as h5:
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=1000, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            for variable in variables:
                dataset = h5[variable.lstrip("/")]
                data = self._read_dataset_range(dataset, start, end)
                out_vars.append(
                    {
                        "path": "/" + variable.strip("/"),
                        "shape": list(dataset.shape),
                        "dtype": str(dataset.dtype),
                        "data": json_safe(data),
                    }
                )
            time_axis = self._timeseries_axis(h5, request, range_payload, start, end)
        return {
            "datasource": self.name,
            "file_id": file_id,
            "range": {**range_payload, "sample_count": max(0, end - start)},
            "time_axis": time_axis,
            "variables": out_vars,
        }

    def plot(self, request: dict[str, Any]) -> dict[str, Any]:
        plot_type = str(request.get("plot_type") or "")
        if plot_type in {"electric_field", "electric_timeseries", "electric_vector", "cses_hpm_electric_field_overview"}:
            return {
                "datasource": self.name,
                "status": "unsupported",
                "reason": CSES_UNSUPPORTED_FEATURES["electric_field"],
            }
        if plot_type in {"solar_wind", "cses_hpm_solar_wind_overview"}:
            return {
                "datasource": self.name,
                "status": "unsupported",
                "reason": CSES_UNSUPPORTED_FEATURES["solar_wind"],
            }
        if plot_type in {"spectrogram", "cses_hpm_spectrogram_overview"}:
            return {
                "datasource": self.name,
                "status": "unsupported",
                "reason": CSES_UNSUPPORTED_FEATURES["spectrogram"],
            }
        if plot_type == "batch_magnetic_timeseries":
            return self._batch_plot(request)
        if plot_type == "cses_hpm_magnetic_overview":
            return self._plot_hpm_magnetic_overview(request)
        if plot_type == "cses_hpm_quality_overview":
            return self._plot_hpm_quality_overview(request)
        if plot_type == "cses_hpm_trajectory_overview":
            return self._plot_hpm_trajectory_overview(request)
        if plot_type == "cses_hpm_cadence_overview":
            return self._plot_hpm_cadence_overview(request)
        if plot_type == "cses_hpm_batch_statistics_overview":
            return {
                "datasource": self.name,
                "plot_type": plot_type,
                "status": "statistics_endpoint",
                "reason": "Use POST /api/datasources/cses_hpm/stats with file_ids for batch statistics artifacts.",
            }
        if plot_type not in {"magnetic_timeseries", "scalar_timeseries", "trajectory_2d", "trajectory_3d"}:
            return {
                "datasource": self.name,
                "status": "unsupported",
                "reason": f"CSES plot type {plot_type!r} is not supported in this phase.",
            }

        file_id = str(request.get("file_id") or "")
        source = self._safe_file_path(file_id)
        digest = request_digest(
            {
                "file_id": file_id,
                "plot_type": plot_type,
                "range": request.get("range", {}),
                "variables": request.get("variables", []),
                "time_variable": request.get("time_variable"),
            }
        )
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        out_path = self._generated_plot_path(f"{stem}_{plot_type}_{digest}.png")

        with h5py.File(source, "r") as h5:
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=200, max_samples=5000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            if plot_type == "magnetic_timeseries":
                variable = str((request.get("variables") or ["/B_FGM"])[0])
                time_variable = str(request.get("time_variable") or "/UTC_TIME")
                b_data = self._read_dataset_range(h5[variable.lstrip("/")], start, end)
                x_data = self._read_dataset_range(h5[time_variable.lstrip("/")], start, end) if time_variable.lstrip("/") in h5 else np.asarray([])
                plot_magnetic_timeseries(out_path, x=x_data, b=b_data, title=f"CSES HPM {variable} {file_id}")
            elif plot_type == "scalar_timeseries":
                variable = str((request.get("variables") or ["/UTC_TIME"])[0])
                time_variable = str(request.get("time_variable") or "/UTC_TIME")
                dataset = h5[variable.lstrip("/")]
                y_data = self._read_dataset_range(dataset, start, end)
                x_data = self._read_dataset_range(h5[time_variable.lstrip("/")], start, end) if time_variable.lstrip("/") in h5 else np.asarray([])
                plot_scalar_timeseries(
                    out_path,
                    x=x_data,
                    y=y_data,
                    variable="/" + variable.strip("/"),
                    unit=self._unit_text(self._dataset_unit(dataset)),
                    title=f"CSES HPM {variable} {file_id}",
                )
            elif plot_type == "trajectory_2d":
                lat_variable = str(request.get("lat_variable") or "/GEO_LAT")
                lon_variable = str(request.get("lon_variable") or "/GEO_LON")
                unavailable = self._missing_trajectory_response(
                    plot_type=plot_type,
                    required_variables=[lat_variable, lon_variable],
                    available=h5,
                )
                if unavailable:
                    return unavailable
                lat = self._read_dataset_range(h5[lat_variable.lstrip("/")], start, end)
                lon = self._read_dataset_range(h5[lon_variable.lstrip("/")], start, end)
                plot_trajectory_2d(out_path, lat=lat, lon=lon, title=f"CSES HPM trajectory {file_id}")
            else:
                lat_variable = str(request.get("lat_variable") or "/GEO_LAT")
                lon_variable = str(request.get("lon_variable") or "/GEO_LON")
                alt_variable = str(request.get("alt_variable") or "/ALTITUDE")
                unavailable = self._missing_trajectory_response(
                    plot_type=plot_type,
                    required_variables=[lat_variable, lon_variable, alt_variable],
                    available=h5,
                )
                if unavailable:
                    return unavailable
                lat = self._read_dataset_range(h5[lat_variable.lstrip("/")], start, end)
                lon = self._read_dataset_range(h5[lon_variable.lstrip("/")], start, end)
                alt = self._read_dataset_range(h5[alt_variable.lstrip("/")], start, end)
                plot_trajectory_3d(out_path, lat=lat, lon=lon, alt=alt, title=f"CSES HPM 3D trajectory {file_id}")

        artifact = self.artifacts.register(
            f"{self.name}:plot:{stem}:{plot_type}:{digest}",
            out_path,
            media_type="image/png",
            label=f"CSES HPM {plot_type} {file_id}",
        )
        return {
            "datasource": self.name,
            "file_id": file_id,
            "plot_type": plot_type,
            "range": {**range_payload, "sample_count": max(0, end - start)},
            "artifact": artifact,
        }

    def _plot_hpm_magnetic_overview(self, request: dict[str, Any]) -> dict[str, Any]:
        file_id = str(request.get("file_id") or "")
        summary = self._load_summary(file_id)
        variable = self._candidate_path(summary, "magnetic_vector") or "/B_FGM"
        time_variable = self._candidate_path(summary, "time") or "/UTC_TIME"
        source = self._safe_file_path(file_id)
        digest = request_digest({"file_id": file_id, "plot_type": "cses_hpm_magnetic_overview", "range": request.get("range", {})})
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        out_path = self._generated_plot_path(f"{stem}_cses_hpm_magnetic_overview_{digest}.png")
        with h5py.File(source, "r") as h5:
            unavailable = self._missing_h5_fields_response(file_id, "cses_hpm_magnetic_overview", [variable], h5)
            if unavailable:
                return unavailable
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=1000, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            dataset = h5[variable.lstrip("/")]
            b_data = self._read_dataset_range(dataset, start, end)
            x_data = self._read_dataset_range(h5[time_variable.lstrip("/")], start, end) if time_variable.lstrip("/") in h5 else np.asarray([])
            unit = self._unit_text(self._dataset_unit(dataset))
        plot_vector_overview(
            out_path,
            x=x_data,
            data=b_data,
            title=f"CSES HPM magnetic overview {file_id} ({variable}, coordinate system unconfirmed)",
            component_labels=["B1", "B2", "B3"],
            ylabel=f"B{f' ({unit})' if unit else ''}",
            magnitude_label="|B_vector|",
        )
        artifact = self.artifacts.register(
            f"{self.name}:plot:{stem}:cses_hpm_magnetic_overview:{digest}",
            out_path,
            media_type="image/png",
            label=f"CSES HPM magnetic overview {file_id}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": file_id,
            "plot_type": "cses_hpm_magnetic_overview",
            "range": {**range_payload, "sample_count": max(0, end - start)},
            "fields": [{"path": variable, "unit": unit, "coordinate_system": "unconfirmed", "components": ["B1", "B2", "B3", "|B_vector|"]}],
            "time": {"field": time_variable, "confidence": "inferred"},
            "processing_log": [
                f"Read {variable} from HPM H5 using inspector-inferred magnetic_vector candidate.",
                "Coordinate system remains unconfirmed.",
                "Regenerated the formal Web PNG under outputs/generated_plots/cses_hpm.",
            ],
            "artifact": artifact,
        }

    def _plot_hpm_quality_overview(self, request: dict[str, Any]) -> dict[str, Any]:
        file_id = str(request.get("file_id") or "")
        summary = self._load_summary(file_id)
        flag_variable = self._candidate_path(summary, "quality_flag") or "/FLAG_MT"
        time_variable = self._candidate_path(summary, "time") or "/UTC_TIME"
        source = self._safe_file_path(file_id)
        digest = request_digest({"file_id": file_id, "plot_type": "cses_hpm_quality_overview", "range": request.get("range", {})})
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        out_path = self._generated_plot_path(f"{stem}_cses_hpm_quality_overview_{digest}.png")
        with h5py.File(source, "r") as h5:
            unavailable = self._missing_h5_fields_response(file_id, "cses_hpm_quality_overview", [flag_variable], h5)
            if unavailable:
                return unavailable
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=1000, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            flags = self._read_dataset_range(h5[flag_variable.lstrip("/")], start, end)
            x_data = self._read_dataset_range(h5[time_variable.lstrip("/")], start, end) if time_variable.lstrip("/") in h5 else np.asarray([])
            unit = self._unit_text(self._dataset_unit(h5[flag_variable.lstrip("/")]))
        distribution = plot_quality_overview(out_path, x=x_data, flags=flags, title=f"CSES HPM quality overview {file_id} ({flag_variable})")
        artifact = self.artifacts.register(
            f"{self.name}:plot:{stem}:cses_hpm_quality_overview:{digest}",
            out_path,
            media_type="image/png",
            label=f"CSES HPM quality overview {file_id}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": file_id,
            "plot_type": "cses_hpm_quality_overview",
            "range": {**range_payload, "sample_count": max(0, end - start)},
            "fields": [{"path": flag_variable, "unit": unit}],
            "time": {"field": time_variable, "confidence": "inferred" if time_variable else "sample_index"},
            "quality_distribution": distribution,
            "processing_log": [
                f"Read {flag_variable} from HPM H5 using inspector-inferred quality_flag candidate.",
                "Displayed flags for diagnostics only; no automatic masking was applied.",
            ],
            "artifact": artifact,
        }

    def _plot_hpm_trajectory_overview(self, request: dict[str, Any]) -> dict[str, Any]:
        file_id = str(request.get("file_id") or "")
        summary = self._load_summary(file_id)
        lat_variable = self._candidate_path(summary, "latitude") or "/GEO_LAT"
        lon_variable = self._candidate_path(summary, "longitude") or "/GEO_LON"
        alt_variable = self._candidate_path(summary, "altitude") or "/ALTITUDE"
        time_variable = self._candidate_path(summary, "time") or "/UTC_TIME"
        source = self._safe_file_path(file_id)
        digest = request_digest({"file_id": file_id, "plot_type": "cses_hpm_trajectory_overview", "range": request.get("range", {})})
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        out_path = self._generated_plot_path(f"{stem}_cses_hpm_trajectory_overview_{digest}.png")
        with h5py.File(source, "r") as h5:
            required = [lat_variable, lon_variable, alt_variable]
            unavailable = self._missing_h5_fields_response(file_id, "cses_hpm_trajectory_overview", required, h5)
            if unavailable:
                return unavailable
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=1000, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            lat = self._read_dataset_range(h5[lat_variable.lstrip("/")], start, end)
            lon = self._read_dataset_range(h5[lon_variable.lstrip("/")], start, end)
            alt = self._read_dataset_range(h5[alt_variable.lstrip("/")], start, end)
            x_data = self._read_dataset_range(h5[time_variable.lstrip("/")], start, end) if time_variable.lstrip("/") in h5 else np.asarray([])
            fields = [{"path": path, "unit": self._unit_text(self._dataset_unit(h5[path.lstrip("/")]))} for path in required]
        plot_cses_trajectory_overview(out_path, x=x_data, lat=lat, lon=lon, alt=alt, title=f"CSES HPM trajectory overview {file_id}")
        artifact = self.artifacts.register(
            f"{self.name}:plot:{stem}:cses_hpm_trajectory_overview:{digest}",
            out_path,
            media_type="image/png",
            label=f"CSES HPM trajectory overview {file_id}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": file_id,
            "plot_type": "cses_hpm_trajectory_overview",
            "range": {**range_payload, "sample_count": max(0, end - start)},
            "fields": fields,
            "time": {"field": time_variable, "confidence": "inferred"},
            "processing_log": [
                "Used H5 geographic lat/lon/alt fields directly.",
                "No Cluster L/MLT/MLAT conversion was applied.",
            ],
            "artifact": artifact,
        }

    def _plot_hpm_cadence_overview(self, request: dict[str, Any]) -> dict[str, Any]:
        file_id = str(request.get("file_id") or "")
        summary = self._load_summary(file_id)
        time_variable = self._candidate_path(summary, "time") or "/UTC_TIME"
        source = self._safe_file_path(file_id)
        digest = request_digest({"file_id": file_id, "plot_type": "cses_hpm_cadence_overview", "range": request.get("range", {})})
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        out_path = self._generated_plot_path(f"{stem}_cses_hpm_cadence_overview_{digest}.png")
        with h5py.File(source, "r") as h5:
            unavailable = self._missing_h5_fields_response(file_id, "cses_hpm_cadence_overview", [time_variable], h5)
            if unavailable:
                return unavailable
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=5000, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            time_data = self._read_dataset_range(h5[time_variable.lstrip("/")], start, end)
            parsed_ms = parse_cses_utc_time_millis(time_data)
            unit = self._unit_text(self._dataset_unit(h5[time_variable.lstrip("/")]))
        cadence = plot_cadence_overview(
            out_path,
            parsed_time_ms=parsed_ms,
            title=f"CSES HPM cadence overview {file_id}",
            annotation="inferred time semantics; use as diagnostics before spectrogram analysis",
        )
        artifact = self.artifacts.register(
            f"{self.name}:plot:{stem}:cses_hpm_cadence_overview:{digest}",
            out_path,
            media_type="image/png",
            label=f"CSES HPM cadence overview {file_id}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": file_id,
            "plot_type": "cses_hpm_cadence_overview",
            "range": {**range_payload, "sample_count": max(0, end - start)},
            "time": {"field": time_variable, "confidence": "inferred", "unit": unit},
            "cadence": cadence,
            "processing_log": [
                f"Parsed {time_variable} mechanically as CSES UTC_TIME.",
                "Marked inferred time semantics for cadence diagnostics.",
                "Spectrogram remains disabled until time semantics, cadence, magnetic variable, and quality masking are confirmed.",
            ],
            "artifact": artifact,
        }

    def stats(self, request: dict[str, Any]) -> dict[str, Any]:
        file_ids = [str(item) for item in request.get("file_ids", []) if str(item)]
        if file_ids:
            result = self._batch_stats(request, file_ids)
            return self._maybe_attach_stats_artifact(result, request, file_id="batch")
        file_id = str(request.get("file_id") or "")
        variables = [str(item) for item in request.get("variables", [])]
        source = self._safe_file_path(file_id)
        out_vars: list[dict[str, Any]] = []
        with h5py.File(source, "r") as h5:
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=200, max_samples=10000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            for variable in variables:
                dataset = h5[variable.lstrip("/")]
                data = self._read_dataset_range(dataset, start, end)
                out_vars.append(numeric_stats_extended("/" + variable.strip("/"), data))
        result = {
            "datasource": self.name,
            "file_id": file_id,
            "range": {**range_payload, "sample_count": max(0, end - start)},
            "variables": out_vars,
        }
        return self._maybe_attach_stats_artifact(result, request, file_id=file_id)

    def _batch_stats(self, request: dict[str, Any], file_ids: list[str]) -> dict[str, Any]:
        variables = [str(item) for item in request.get("variables", [])]
        time_variable = str(request.get("time_variable") or "/UTC_TIME")
        flag_variable = str(request.get("flag_variable") or "")
        position_variables = request.get("position_variables", {}) or {}
        start, end = bounded_sample_range(request.get("range", {}), default_limit=1000, max_samples=20000)
        batch = self._batch_rows(
            file_ids=file_ids,
            variables=variables,
            time_variable=time_variable,
            flag_variable=flag_variable,
            position_variables=position_variables,
            start=start,
            end=end,
        )
        deduped = batch["deduped"]

        out_vars: list[dict[str, Any]] = []
        for variable in variables:
            if deduped:
                data = np.asarray([row["variables"][variable] for row in deduped])
            else:
                data = np.asarray([])
            out_vars.append(numeric_stats_extended(variable, data))

        times = np.asarray([row["time"] for row in deduped], dtype=float) if deduped else np.asarray([], dtype=float)
        flag_distribution: dict[str, int] = {}
        if flag_variable:
            for row in deduped:
                key = str(row["flag"])
                flag_distribution[key] = flag_distribution.get(key, 0) + 1

        spatial: dict[str, dict[str, float | None]] = {}
        for key in position_variables:
            values = np.asarray([row["position"].get(str(key)) for row in deduped], dtype=float) if deduped else np.asarray([], dtype=float)
            finite = values[np.isfinite(values)]
            spatial[str(key)] = {
                "min": float(np.min(finite)) if finite.size else None,
                "max": float(np.max(finite)) if finite.size else None,
            }

        magnitudes: dict[str, Any] = {}
        for variable in variables:
            data = np.asarray([row["variables"][variable] for row in deduped]) if deduped else np.asarray([])
            if data.ndim == 2 and data.shape[1] == 3:
                magnitudes[f"{variable}|magnitude"] = numeric_stats_extended(f"{variable}|magnitude", np.linalg.norm(data.astype(float), axis=1))

        cadence_values = np.diff(times) if times.size > 1 else np.asarray([], dtype=float)
        return {
            "datasource": self.name,
            "mode": "batch",
            "file_ids": file_ids,
            "raw_sample_count": batch["raw_sample_count"],
            "sample_count": len(deduped),
            "duplicate_count": batch["duplicate_count"],
            "time_variable": time_variable,
            "time_range": {
                "start": self._scalar(deduped[0]["time"]) if deduped else None,
                "end": self._scalar(deduped[-1]["time"]) if deduped else None,
            },
            "cadence": {
                "count": int(cadence_values.size),
                "min": float(np.min(cadence_values)) if cadence_values.size else None,
                "max": float(np.max(cadence_values)) if cadence_values.size else None,
                "median": float(np.median(cadence_values)) if cadence_values.size else None,
            },
            "quality_flags": {flag_variable: {"distribution": flag_distribution}} if flag_variable else {},
            "spatial_coverage": spatial,
            "variables": out_vars,
            "vector_magnitude": magnitudes,
        }

    def _batch_plot(self, request: dict[str, Any]) -> dict[str, Any]:
        file_ids = [str(item) for item in request.get("file_ids", []) if str(item)]
        if len(file_ids) < 1:
            raise ValueError("batch_magnetic_timeseries requires file_ids")
        variables = [str(item) for item in request.get("variables", [])]
        variable = variables[0] if variables else "/B_FGM"
        time_variable = str(request.get("time_variable") or "/UTC_TIME")
        start, end = bounded_sample_range(request.get("range", {}), default_limit=1000, max_samples=20000)
        batch = self._batch_rows(
            file_ids=file_ids,
            variables=[variable],
            time_variable=time_variable,
            flag_variable="",
            position_variables={},
            start=start,
            end=end,
        )
        deduped = batch["deduped"]
        if deduped:
            x_data = np.asarray([row["time"] for row in deduped])
            b_data = np.asarray([row["variables"][variable] for row in deduped])
        else:
            x_data = np.asarray([])
            b_data = np.empty((0, 3), dtype=float)
        digest = request_digest({"kind": "batch_plot", "request": request})
        stem = sanitize_id("_".join(Path(file_id).name.replace(".", "_") for file_id in file_ids[:3]))
        out_path = self.config.outputs_root / "plots" / self.name / f"batch_{stem}_{digest}.png"
        plot_magnetic_timeseries(out_path, x=x_data, b=b_data, title=f"CSES HPM batch {variable} ({len(file_ids)} files)")
        artifact = self.artifacts.register(
            f"{self.name}:plot:batch:{digest}",
            out_path,
            media_type="image/png",
            label=f"CSES HPM batch {variable} plot",
        )
        return {
            "datasource": self.name,
            "mode": "batch",
            "plot_type": "batch_magnetic_timeseries",
            "file_ids": file_ids,
            "variable": variable,
            "time_variable": time_variable,
            "range": {"mode": "sample_index", "start_index": start, "end_index": end},
            "raw_sample_count": batch["raw_sample_count"],
            "sample_count": len(deduped),
            "duplicate_count": batch["duplicate_count"],
            "time_range": {
                "start": self._scalar(deduped[0]["time"]) if deduped else None,
                "end": self._scalar(deduped[-1]["time"]) if deduped else None,
            },
            "artifact": artifact,
        }

    def _batch_rows(
        self,
        *,
        file_ids: list[str],
        variables: list[str],
        time_variable: str,
        flag_variable: str,
        position_variables: dict[str, Any],
        start: int,
        end: int,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for file_id in file_ids:
            source = self._safe_file_path(file_id)
            with h5py.File(source, "r") as h5:
                time_data = self._read_dataset_range(h5[time_variable.lstrip("/")], start, end).reshape(-1)
                count = int(time_data.shape[0])
                row_data: dict[str, np.ndarray] = {
                    "time": time_data,
                }
                for variable in variables:
                    row_data[variable] = self._read_dataset_range(h5[variable.lstrip("/")], start, start + count)
                if flag_variable:
                    row_data[flag_variable] = self._read_dataset_range(h5[flag_variable.lstrip("/")], start, start + count).reshape(-1)
                for key, path in position_variables.items():
                    if path:
                        row_data[str(key)] = self._read_dataset_range(h5[str(path).lstrip("/")], start, start + count).reshape(-1)
                for index in range(count):
                    rows.append(
                        {
                            "file_id": file_id,
                            "time": self._scalar(row_data["time"][index]),
                            "variables": {variable: row_data[variable][index] for variable in variables},
                            "flag": self._scalar(row_data[flag_variable][index]) if flag_variable else None,
                            "position": {str(key): self._scalar(row_data[str(key)][index]) for key, path in position_variables.items() if path},
                        }
                    )

        rows.sort(key=lambda item: item["time"])
        deduped: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for row in rows:
            if row["time"] in seen:
                continue
            seen.add(row["time"])
            deduped.append(row)
        raw_sample_count = len(rows)
        return {
            "rows": rows,
            "deduped": deduped,
            "raw_sample_count": raw_sample_count,
            "duplicate_count": raw_sample_count - len(deduped),
        }

    def _missing_trajectory_response(
        self,
        *,
        plot_type: str,
        required_variables: list[str],
        available: h5py.File,
    ) -> dict[str, Any] | None:
        normalized = ["/" + variable.strip("/") for variable in required_variables]
        missing = [variable for variable in normalized if variable.lstrip("/") not in available]
        if not missing:
            return None
        if plot_type == "trajectory_2d":
            required_text = "/GEO_LAT and /GEO_LON"
        else:
            required_text = "/GEO_LAT, /GEO_LON, and /ALTITUDE"
        return {
            "datasource": self.name,
            "plot_type": plot_type,
            "status": "not_available",
            "missing_variables": missing,
            "reason": f"CSES {plot_type} requires {required_text} variables in the selected H5 file.",
        }

    def _maybe_attach_stats_artifact(self, result: dict[str, Any], request: dict[str, Any], *, file_id: str) -> dict[str, Any]:
        save_format = str(request.get("save_format") or "").lower()
        if not save_format:
            return result
        if save_format == "cdf":
            return {
                **result,
                "save_format": save_format,
                "status": "unsupported",
                "reserved": True,
                "reason": "Stats CDF output remains reserved; CDF remains reserved until a CDF writer and metadata mapping are verified.",
            }
        extension = stats_extension(save_format)
        digest = request_digest({"kind": "stats", "file_id": file_id, "request": request})
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        out_path = self.config.outputs_root / "stats" / self.name / f"{stem}_{digest}.{extension}"
        write_stats_artifact(out_path, save_format, result)
        artifact = self.artifacts.register(
            f"{self.name}:stats:{stem}:{digest}",
            out_path,
            media_type=stats_media_type(save_format),
            label=f"CSES HPM stats {file_id} {save_format.upper()}",
        )
        return {**result, "save_format": save_format, "stats_artifact": artifact}

    def export(self, request: dict[str, Any]) -> dict[str, Any]:
        export_format = str(request.get("format") or "csv").lower()
        if export_format not in {"csv", "dat", "h5"}:
            return {
                "datasource": self.name,
                "format": export_format,
                "status": "unsupported",
                "reserved": export_format == "cdf",
                "reason": "Phase 6 supports csv, dat, and h5 export for CSES HPM; CDF remains reserved.",
            }
        file_id = str(request.get("file_id") or "")
        variables = [str(item) for item in request.get("variables", [])]
        source = self._safe_file_path(file_id)
        export_vars: list[dict[str, Any]] = []
        with h5py.File(source, "r") as h5:
            range_payload = self._resolve_range(h5, request.get("range", {}), default_limit=200, max_samples=10000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            for variable in variables:
                dataset = h5[variable.lstrip("/")]
                export_vars.append(
                    {
                        "path": "/" + variable.strip("/"),
                        "data": self._read_dataset_range(dataset, start, end),
                        "unit": self._dataset_unit(dataset),
                    }
                )
        digest = request_digest({"file_id": file_id, "variables": variables, "range": request.get("range", {}), "format": export_format})
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        extension = export_extension(export_format)
        out_path = self.config.outputs_root / "exports" / self.name / f"{stem}_{digest}.{extension}"
        table_info = write_table_export(out_path, export_format, start, export_vars)
        sample_count = int(table_info.get("row_count", max(0, end - start)))
        manifest = build_export_manifest(
            datasource=self.name,
            file_id=file_id,
            original_file=str(source),
            variables=export_vars,
            range_spec=range_payload,
            export_format=export_format,
            sample_count=sample_count,
            artifact_path=out_path,
        )
        manifest_path = out_path.with_name(f"{out_path.stem}_manifest.json")
        write_manifest(manifest_path, manifest)
        artifact = self.artifacts.register(
            f"{self.name}:export:{stem}:{digest}",
            out_path,
            media_type=export_media_type(export_format),
            label=f"CSES HPM {export_format.upper()} export {file_id}",
        )
        manifest_artifact = self.artifacts.register(
            f"{self.name}:export_manifest:{stem}:{digest}",
            manifest_path,
            media_type="application/json",
            label=f"CSES HPM export manifest {file_id}",
        )
        return {
            "datasource": self.name,
            "file_id": file_id,
            "format": export_format,
            "range": {**range_payload, "sample_count": sample_count},
            "table": table_info,
            "artifact": artifact,
            "manifest": manifest,
            "manifest_artifact": manifest_artifact,
        }

    def _inspection_index(self) -> dict[str, Any] | None:
        path = self.inspection_root / "inspection_index.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _safe_file_path(self, file_id: str) -> Path:
        root = self.hpm_root.resolve()
        path = (root / file_id).resolve()
        if root != path and root not in path.parents:
            raise ValueError("file_id resolves outside CSES HPM root")
        return path

    def _summary_path(self, file_id: str) -> Path:
        rel = Path(file_id)
        if rel.suffix:
            rel = rel.with_suffix("")
        return self.inspection_root / rel / "summary.json"

    def _load_summary(self, file_id: str) -> dict[str, Any]:
        path = self._summary_path(file_id)
        if not path.exists():
            raise FileNotFoundError(f"inspection summary not found for {file_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _inspection_report_artifact(self, file_id: str) -> dict[str, Any] | None:
        report_path = self._summary_path(file_id).parent / "report.md"
        if not report_path.exists():
            return None
        stem = sanitize_id(Path(file_id).as_posix().replace(".", "_"))
        return self.artifacts.register(
            f"{self.name}:inspection_report:{stem}",
            report_path,
            media_type="text/markdown",
            label=f"CSES HPM inspection report {file_id}",
        )

    def _generated_plot_path(self, name: str) -> Path:
        return self.config.outputs_root / "generated_plots" / self.name / name

    def _missing_h5_fields_response(
        self,
        file_id: str,
        plot_type: str,
        required_fields: list[str],
        available: h5py.File,
    ) -> dict[str, Any] | None:
        missing = ["/" + field.strip("/") for field in required_fields if field.strip("/") not in available]
        if not missing:
            return None
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": file_id,
            "plot_type": plot_type,
            "status": "unavailable",
            "required_fields": required_fields,
            "missing_fields": missing,
            "reason": "missing field in selected CSES HPM H5 file",
        }

    def _metadata_time_summary(self, file_id: str, summary: dict[str, Any]) -> dict[str, Any]:
        time_variable = self._candidate_path(summary, "time") or "/UTC_TIME"
        source = self._safe_file_path(file_id)
        dataset_name = time_variable.lstrip("/")
        try:
            if not source.exists():
                return {
                    "status": "unavailable",
                    "time_variable": "/" + dataset_name,
                    "time_confidence": "inferred",
                    "reason": "source file not found",
                }
            with h5py.File(source, "r") as h5:
                if dataset_name not in h5:
                    return {
                        "status": "unavailable",
                        "time_variable": "/" + dataset_name,
                        "time_confidence": "inferred",
                        "reason": "time dataset not found",
                    }
                dataset = h5[dataset_name]
                if dataset.shape == ():
                    return {
                        "status": "unavailable",
                        "time_variable": "/" + dataset_name,
                        "time_confidence": "inferred",
                        "reason": "time dataset is scalar",
                    }
                sample_count = int(dataset.shape[0])
                if sample_count > 1_000_000:
                    return {
                        "status": "too_large",
                        "time_variable": "/" + dataset_name,
                        "time_confidence": "inferred",
                        "sample_count": sample_count,
                        "reason": "time summary is limited to 1000000 samples",
                    }
                parsed_ms = parse_cses_utc_time_millis(np.asarray(dataset[:]).reshape(-1))
                if parsed_ms.size == 0:
                    return {
                        "status": "unavailable",
                        "time_variable": "/" + dataset_name,
                        "time_confidence": "inferred",
                        "sample_count": 0,
                        "reason": "time dataset is empty",
                    }
                if parsed_ms.size > 1 and np.any(np.diff(parsed_ms) < 0):
                    return {
                        "status": "unparsed",
                        "time_variable": "/" + dataset_name,
                        "time_confidence": "inferred",
                        "sample_count": int(parsed_ms.size),
                        "reason": "time dataset is not monotonic",
                    }
                cadence = np.diff(parsed_ms)
                return {
                    "status": "parsed",
                    "time_variable": "/" + dataset_name,
                    "time_confidence": "inferred",
                    "time_units": json_safe(self._dataset_unit(dataset)),
                    "sample_count": int(parsed_ms.size),
                    "start": format_utc_millis(int(parsed_ms[0])),
                    "end": format_utc_millis(int(parsed_ms[-1])),
                    "cadence_ms": cadence_summary(cadence),
                }
        except Exception as exc:
            return {
                "status": "unparsed",
                "time_variable": "/" + dataset_name,
                "time_confidence": "inferred",
                "reason": f"{type(exc).__name__}: {exc}",
            }

    def _metadata_quality_summary(self, file_id: str, summary: dict[str, Any]) -> dict[str, Any]:
        flag_variable = self._candidate_path(summary, "quality_flag") or "/FLAG_MT"
        source = self._safe_file_path(file_id)
        dataset_name = flag_variable.lstrip("/")
        try:
            if not source.exists():
                return {
                    "status": "unavailable",
                    "flag_variable": "/" + dataset_name,
                    "flag_confidence": "inferred",
                    "reason": "source file not found",
                }
            with h5py.File(source, "r") as h5:
                if dataset_name not in h5:
                    return {
                        "status": "unavailable",
                        "flag_variable": "/" + dataset_name,
                        "flag_confidence": "inferred",
                        "reason": "quality flag dataset not found",
                    }
                dataset = h5[dataset_name]
                if dataset.shape == ():
                    return {
                        "status": "unavailable",
                        "flag_variable": "/" + dataset_name,
                        "flag_confidence": "inferred",
                        "reason": "quality flag dataset is scalar",
                    }
                sample_count = int(dataset.shape[0])
                if sample_count > 1_000_000:
                    return {
                        "status": "too_large",
                        "flag_variable": "/" + dataset_name,
                        "flag_confidence": "inferred",
                        "sample_count": sample_count,
                        "reason": "quality summary is limited to 1000000 samples",
                    }
                values = np.asarray(dataset[:]).reshape(-1)
                distribution: dict[str, int] = {}
                for value in values:
                    key = str(self._scalar(value))
                    distribution[key] = distribution.get(key, 0) + 1
                return {
                    "status": "parsed",
                    "flag_variable": "/" + dataset_name,
                    "flag_confidence": "inferred",
                    "sample_count": sample_count,
                    "distribution": dict(sorted(distribution.items(), key=lambda item: item[0])),
                }
        except Exception as exc:
            return {
                "status": "unparsed",
                "flag_variable": "/" + dataset_name,
                "flag_confidence": "inferred",
                "reason": f"{type(exc).__name__}: {exc}",
            }

    @staticmethod
    def _candidate_path(summary: dict[str, Any], kind: str) -> str | None:
        candidates = summary.get("candidates", {}).get(kind, [])
        if not isinstance(candidates, list):
            return None
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("path"):
                return str(candidate["path"])
        return None

    def _resolve_range(
        self,
        h5: h5py.File,
        range_spec: dict[str, Any],
        *,
        default_limit: int = 200,
        max_samples: int = 10000,
    ) -> dict[str, Any]:
        if range_spec.get("mode") != "time":
            start, end = bounded_sample_range(range_spec, default_limit=default_limit, max_samples=max_samples)
            return {
                "mode": "sample_index",
                "start_index": start,
                "end_index": end,
            }

        time_variable = str(range_spec.get("time_variable") or "/UTC_TIME")
        dataset_name = time_variable.lstrip("/")
        if dataset_name not in h5:
            raise ValueError(f"time_variable {time_variable!r} not found")
        time_dataset = h5[dataset_name]
        if time_dataset.shape == ():
            raise ValueError(f"time_variable {time_variable!r} must be a sample-aligned vector")
        sample_count = int(time_dataset.shape[0])
        if sample_count > 1_000_000:
            raise ValueError("CSES time range resolution is limited to 1000000 time samples")
        time_values = np.asarray(time_dataset[:]).reshape(-1)
        parsed_ms = parse_cses_utc_time_millis(time_values)
        if parsed_ms.size > 1 and np.any(np.diff(parsed_ms) < 0):
            raise ValueError("CSES UTC_TIME values must be monotonic for time range resolution")
        start_ms = parse_time_bound_millis(range_spec.get("start"), field="start")
        end_ms = parse_time_bound_millis(range_spec.get("end"), field="end")
        if end_ms < start_ms:
            raise ValueError("time range end must be greater than or equal to start")
        start_index = int(np.searchsorted(parsed_ms, start_ms, side="left"))
        end_index = int(np.searchsorted(parsed_ms, end_ms, side="left"))
        bounded_start = max(0, min(start_index, parsed_ms.size))
        bounded_end = max(bounded_start, min(end_index, parsed_ms.size))
        if bounded_end - bounded_start > max_samples:
            raise ValueError(f"time range is limited to {max_samples} samples")
        return {
            "mode": "time",
            "resolved_mode": "sample_index",
            "start": str(range_spec.get("start")),
            "end": str(range_spec.get("end")),
            "start_index": bounded_start,
            "end_index": bounded_end,
            "time_variable": "/" + dataset_name,
            "time_confidence": "inferred",
            "time_units": json_safe(self._dataset_unit(time_dataset)),
        }

    def _timeseries_axis(
        self,
        h5: h5py.File,
        request: dict[str, Any],
        range_payload: dict[str, Any],
        start: int,
        end: int,
    ) -> dict[str, Any]:
        time_variable = str(range_payload.get("time_variable") or request.get("time_variable") or "/UTC_TIME")
        dataset_name = time_variable.lstrip("/")
        if dataset_name not in h5:
            return {
                "kind": "sample_index",
                "confidence": "confirmed",
                "data": list(range(start, end)),
            }
        time_dataset = h5[dataset_name]
        try:
            time_data = self._read_dataset_range(time_dataset, start, end)
            parsed_ms = parse_cses_utc_time_millis(time_data)
        except (TypeError, ValueError):
            return {
                "kind": "sample_index",
                "confidence": "confirmed",
                "data": list(range(start, end)),
                "fallback_reason": f"time variable /{dataset_name} could not be parsed as CSES UTC_TIME",
            }
        return {
            "kind": "utc",
            "path": "/" + dataset_name,
            "confidence": "inferred",
            "unit": json_safe(self._dataset_unit(time_dataset)),
            "data": [format_utc_millis(int(value)) for value in parsed_ms],
        }

    @staticmethod
    def _read_dataset_range(dataset: h5py.Dataset, start: int, end: int) -> np.ndarray:
        if dataset.shape == ():
            return np.asarray(dataset[()])
        selectors: list[slice] = [slice(start, min(end, int(dataset.shape[0])))]
        selectors.extend(slice(None) for _ in dataset.shape[1:])
        return np.asarray(dataset[tuple(selectors)])

    @staticmethod
    def _dataset_unit(dataset: h5py.Dataset) -> Any:
        return dataset.attrs.get("Units") or dataset.attrs.get("units") or dataset.attrs.get("Unit") or dataset.attrs.get("unit")

    @staticmethod
    def _unit_text(value: Any) -> str | None:
        if value is None:
            return None
        safe = json_safe(value)
        if isinstance(safe, dict) and "value" in safe:
            return str(safe["value"])
        if isinstance(safe, list):
            return ", ".join(str(item) for item in safe)
        return str(safe)

    @staticmethod
    def _scalar(value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        return value


def parse_time_bound_millis(value: Any, *, field: str) -> int:
    if value is None:
        raise ValueError(f"time range {field} is required")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        raise ValueError(f"time range {field} is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(round(dt.timestamp() * 1000))


def format_utc_millis(value: int) -> str:
    dt = datetime.fromtimestamp(value / 1000, timezone.utc)
    if dt.microsecond:
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def cadence_summary(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {
        "count": int(arr.size),
        "min": int(np.min(arr)),
        "median": int(np.median(arr)),
        "max": int(np.max(arr)),
    }


def parse_cses_utc_time_millis(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values).reshape(-1)
    out = np.empty(arr.shape[0], dtype=np.int64)
    for index, value in enumerate(arr):
        text = cses_utc_time_text(value)
        if len(text) < 17:
            raise ValueError("CSES UTC_TIME values must use YYYYMMDDHHMMSSmmm compact timestamps")
        year = int(text[0:4])
        month = int(text[4:6])
        day = int(text[6:8])
        hour = int(text[8:10])
        minute = int(text[10:12])
        second = int(text[12:14])
        millis = int(text[14:17])
        dt = datetime(year, month, day, hour, minute, second, millis * 1000, tzinfo=timezone.utc)
        out[index] = int(round(dt.timestamp() * 1000))
    return out


def cses_utc_time_text(value: Any) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, np.bytes_):
        text = value.astype(str).item()
    elif isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            raise ValueError("CSES UTC_TIME values must be finite")
        text = str(int(round(float(value))))
    elif isinstance(value, (int, np.integer)):
        text = str(int(value))
    else:
        text = str(value)
    text = text.strip()
    if "." in text:
        whole, fraction = text.split(".", 1)
        text = whole + (fraction + "000")[:3]
    return "".join(character for character in text if character.isdigit())
