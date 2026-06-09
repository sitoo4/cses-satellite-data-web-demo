from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np


def sanitize_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "artifact"


def bounded_sample_range(range_spec: dict[str, Any], *, default_limit: int = 200, max_samples: int = 10000) -> tuple[int, int]:
    if range_spec.get("mode") != "sample_index":
        raise ValueError("Only sample_index range is supported in Phase 6")
    start = max(0, int(range_spec.get("start_index", 0)))
    end = max(start, int(range_spec.get("end_index", start + default_limit)))
    if end - start > max_samples:
        raise ValueError(f"sample_index range is limited to {max_samples} samples")
    return start, end


def read_array_range(array: np.ndarray, start: int, end: int) -> np.ndarray:
    if array.shape == ():
        return np.asarray(array[()])
    selectors: list[slice] = [slice(start, min(end, int(array.shape[0])))]
    selectors.extend(slice(None) for _ in array.shape[1:])
    return np.asarray(array[tuple(selectors)])


def variable_columns(path: str, data: np.ndarray) -> list[str]:
    base = path.strip("/") or path
    if data.ndim <= 1:
        return [base]
    if data.ndim == 2:
        width = int(data.shape[1])
        if width == 1:
            return [base]
        return [f"{base}_{index}" for index in range(width)]
    return [f"{base}_json"]


def row_values(data: np.ndarray, row_index: int) -> list[Any]:
    if data.ndim <= 1:
        return [scalar_value(data[row_index])]
    if data.ndim == 2:
        row = data[row_index]
        if int(data.shape[1]) == 1:
            return [scalar_value(row[0])]
        return [scalar_value(item) for item in row]
    return [repr(data[row_index].tolist())]


def scalar_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def write_csv(path: Path, start_index: int, variables: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = 0
    if variables:
        first = variables[0]["data"]
        sample_count = int(first.shape[0]) if first.shape != () else 1

    headers = ["sample_index"]
    for variable in variables:
        headers.extend(variable_columns(variable["path"], variable["data"]))

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for offset in range(sample_count):
            row: list[Any] = [start_index + offset]
            for variable in variables:
                row.extend(row_values(variable["data"], offset))
            writer.writerow(row)
    return {"row_count": sample_count, "column_count": len(headers)}


def write_dat(path: Path, start_index: int, variables: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = variable_sample_count(variables)
    headers = ["sample_index"]
    for variable in variables:
        headers.extend(variable_columns(variable["path"], variable["data"]))

    with path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(headers) + "\n")
        for offset in range(sample_count):
            row: list[str] = [str(start_index + offset)]
            for variable in variables:
                row.extend(str(item) for item in row_values(variable["data"], offset))
            handle.write("\t".join(row) + "\n")
    return {"row_count": sample_count, "column_count": len(headers)}


def write_h5(path: Path, start_index: int, variables: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = variable_sample_count(variables)
    with h5py.File(path, "w") as h5:
        h5.attrs["generated_by"] = "satellite_data_web"
        h5.attrs["start_sample_index"] = start_index
        h5.attrs["sample_count"] = sample_count
        h5.create_dataset("sample_index", data=np.arange(start_index, start_index + sample_count, dtype=np.int64))
        group = h5.create_group("variables")
        for variable in variables:
            dataset_name = sanitize_id(str(variable["path"]).strip("/") or "variable")
            dataset = group.create_dataset(dataset_name, data=np.asarray(variable["data"]))
            dataset.attrs["original_path"] = str(variable["path"])
            if variable.get("unit") is not None:
                dataset.attrs["unit"] = str(json_safe_manifest(variable["unit"]))
    return {"row_count": sample_count, "column_count": 1 + sum(len(variable_columns(variable["path"], variable["data"])) for variable in variables)}


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe_manifest(manifest), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_export_manifest(
    *,
    datasource: str,
    file_id: str,
    original_file: str,
    variables: list[dict[str, Any]],
    range_spec: dict[str, Any],
    export_format: str,
    sample_count: int,
    artifact_path: Path,
) -> dict[str, Any]:
    return {
        "datasource": datasource,
        "file_id": file_id,
        "original_file": original_file,
        "variables": [
            {
                "path": str(variable["path"]),
                "unit": variable.get("unit"),
                "shape": list(np.asarray(variable["data"]).shape),
                "dtype": str(np.asarray(variable["data"]).dtype),
            }
            for variable in variables
        ],
        "range": range_spec,
        "sample_count": sample_count,
        "format": export_format,
        "export_format": export_format,
        "artifact_path": str(artifact_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "processing": {
            "range_mode": range_spec.get("mode"),
            "bounded_read": True,
            "source_data_copied": False,
        },
    }


def variable_sample_count(variables: list[dict[str, Any]]) -> int:
    if not variables:
        return 0
    first = variables[0]["data"]
    return int(first.shape[0]) if first.shape != () else 1


def export_extension(export_format: str) -> str:
    if export_format == "csv":
        return "csv"
    if export_format == "dat":
        return "dat"
    if export_format == "h5":
        return "h5"
    raise ValueError("Supported export formats are csv, dat, and h5")


def export_media_type(export_format: str) -> str:
    if export_format == "csv":
        return "text/csv"
    if export_format == "dat":
        return "text/plain"
    if export_format == "h5":
        return "application/x-hdf5"
    raise ValueError("Supported export formats are csv, dat, and h5")


def write_table_export(path: Path, export_format: str, start_index: int, variables: list[dict[str, Any]]) -> dict[str, Any]:
    if export_format == "csv":
        return write_csv(path, start_index, variables)
    if export_format == "dat":
        return write_dat(path, start_index, variables)
    if export_format == "h5":
        return write_h5(path, start_index, variables)
    raise ValueError("Supported export formats are csv, dat, and h5")


def stats_extension(save_format: str) -> str:
    if save_format == "json":
        return "json"
    if save_format == "csv":
        return "csv"
    if save_format == "dat":
        return "dat"
    if save_format == "h5":
        return "h5"
    raise ValueError("Supported stats save formats are json, csv, dat, and h5")


def stats_media_type(save_format: str) -> str:
    if save_format == "json":
        return "application/json"
    if save_format == "csv":
        return "text/csv"
    if save_format == "dat":
        return "text/plain"
    if save_format == "h5":
        return "application/x-hdf5"
    raise ValueError("Supported stats save formats are json, csv, dat, and h5")


def write_stats_artifact(path: Path, save_format: str, stats_payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if save_format == "json":
        write_manifest(path, stats_payload)
        return
    if save_format == "csv":
        write_stats_csv(path, stats_payload)
        return
    if save_format == "dat":
        write_stats_dat(path, stats_payload)
        return
    if save_format == "h5":
        write_stats_h5(path, stats_payload)
        return
    raise ValueError("Supported stats save formats are json, csv, dat, and h5")


def write_stats_csv(path: Path, stats_payload: dict[str, Any]) -> None:
    rows = stats_rows(stats_payload)
    headers = ["variable", "component", "count", "finite_count", "min", "max", "mean", "median", "std", "missing_ratio"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in headers})


def write_stats_dat(path: Path, stats_payload: dict[str, Any]) -> None:
    rows = stats_rows(stats_payload)
    headers = ["variable", "component", "count", "finite_count", "min", "max", "mean", "median", "std", "missing_ratio"]
    with path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(headers) + "\n")
        for row in rows:
            handle.write("\t".join("" if row.get(key) is None else str(row.get(key)) for key in headers) + "\n")


def write_stats_h5(path: Path, stats_payload: dict[str, Any]) -> None:
    safe_payload = json_safe_manifest(stats_payload)
    with h5py.File(path, "w") as h5:
        h5.attrs["generated_by"] = "satellite_data_web"
        h5.attrs["datasource"] = str(safe_payload.get("datasource", ""))
        h5.attrs["format"] = "stats_summary"
        h5.attrs["payload_json"] = json.dumps(safe_payload, ensure_ascii=False)
        group = h5.create_group("variables")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in stats_rows(stats_payload):
            grouped.setdefault(str(row["variable"]), []).append(row)
        for variable, rows in grouped.items():
            variable_group = group.create_group(sanitize_id(variable))
            variable_group.attrs["path"] = variable
            variable_group.create_dataset("component", data=np.asarray([int(row.get("component", 0) or 0) for row in rows], dtype=np.int64))
            for field in ["count", "finite_count"]:
                variable_group.create_dataset(field, data=np.asarray([_int_or_zero(row.get(field)) for row in rows], dtype=np.int64))
            for field in ["min", "max", "mean", "median", "std", "missing_ratio"]:
                variable_group.create_dataset(field, data=np.asarray([_float_or_nan(row.get(field)) for row in rows], dtype=np.float64))


def stats_rows(stats_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variable in stats_payload.get("variables", []) or []:
        for item in variable.get("stats", []) or []:
            rows.append(_stats_row(str(variable.get("path", "")), item))
    for variable, magnitude in (stats_payload.get("vector_magnitude", {}) or {}).items():
        if not isinstance(magnitude, dict):
            continue
        for item in magnitude.get("stats", []) or []:
            rows.append(_stats_row(str(variable), item))
    return rows


def _stats_row(variable: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "variable": variable,
        "component": item.get("component"),
        "count": item.get("count"),
        "finite_count": item.get("finite_count"),
        "min": item.get("min"),
        "max": item.get("max"),
        "mean": item.get("mean"),
        "median": item.get("median"),
        "std": item.get("std"),
        "missing_ratio": item.get("missing_ratio"),
    }


def _float_or_nan(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def numeric_stats(path: str, data: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(data)
    if arr.shape == ():
        arr = arr.reshape(1)
    if arr.ndim == 1:
        components = [arr]
    elif arr.ndim == 2:
        components = [arr[:, index] for index in range(arr.shape[1])]
    else:
        return {
            "path": path,
            "shape": list(arr.shape),
            "component_count": 0,
            "stats": [],
            "status": "unsupported_ndim",
        }
    return {
        "path": path,
        "shape": list(arr.shape),
        "component_count": len(components),
        "stats": [_component_stats(component, index) for index, component in enumerate(components)],
    }


def _component_stats(values: np.ndarray, component_index: int) -> dict[str, Any]:
    numeric = np.asarray(values, dtype=float)
    finite = numeric[np.isfinite(numeric)]
    if finite.size == 0:
        return {
            "component": component_index,
            "count": int(numeric.size),
            "finite_count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
        }
    return {
        "component": component_index,
        "count": int(numeric.size),
        "finite_count": int(finite.size),
        "min": _json_number(float(np.min(finite))),
        "max": _json_number(float(np.max(finite))),
        "mean": _json_number(float(np.mean(finite))),
        "std": _json_number(float(np.std(finite))),
    }


def numeric_stats_extended(path: str, data: np.ndarray) -> dict[str, Any]:
    result = numeric_stats(path, data)
    for item in result.get("stats", []):
        values = _component_values(np.asarray(data), int(item.get("component", 0)))
        finite = values[np.isfinite(values)]
        if finite.size:
            item["median"] = _json_number(float(np.median(finite)))
            item["missing_ratio"] = _json_number(float(1.0 - finite.size / values.size)) if values.size else None
        else:
            item["median"] = None
            item["missing_ratio"] = 1.0 if values.size else None
    return result


def _component_values(data: np.ndarray, component_index: int) -> np.ndarray:
    arr = np.asarray(data)
    if arr.shape == ():
        return arr.reshape(1).astype(float)
    if arr.ndim == 1:
        return arr.astype(float)
    if arr.ndim == 2:
        return arr[:, component_index].astype(float)
    return np.asarray([], dtype=float)


def _json_number(value: float) -> float:
    if math.isfinite(value):
        return value
    return float("nan")


def request_digest(payload: dict[str, Any]) -> str:
    raw = repr(sorted(payload.items())).encode("utf-8", errors="replace")
    return hashlib.sha1(raw).hexdigest()[:12]


def json_safe_manifest(value: Any) -> Any:
    if isinstance(value, np.generic):
        return json_safe_manifest(value.item())
    if isinstance(value, np.ndarray):
        return json_safe_manifest(value.tolist())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): json_safe_manifest(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe_manifest(item) for item in value]
    return value
