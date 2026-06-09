from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from app.core.artifacts import ArtifactRegistry
from app.core.config import AppConfig
from app.datasources.cses_hpm import format_utc_millis, parse_cses_utc_time_millis
from app.services.cses_hpm_uploads import (
    ALT_FIELD,
    QUALITY_FIELDS,
    SCALAR_FIELD,
    TIME_FIELD,
    VECTOR_FIELD,
    build_segments,
    crop_bounds,
    crop_mask,
    dedupe_rows_by_time,
    format_beijing_millis,
    has_dataset,
    optional_value,
    read_optional_1d,
)
from app.services.table_export import request_digest


POSITION_FIELDS = ("/GEO_LAT", "/GEO_LON", "/ALTITUDE", "/MAG_LAT", "/MAG_LON")
POSITION_DEFAULT_UNITS = {
    "/GEO_LAT": "deg",
    "/GEO_LON": "deg",
    "/ALTITUDE": "km",
    "/MAG_LAT": "deg",
    "/MAG_LON": "deg",
}
LARGE_GAP_RULE = "max(5s, 2.5*median_cadence_seconds)"


def compute_cses_hpm_feature_statistics(
    *,
    session: dict[str, Any],
    config: AppConfig,
    artifacts: ArtifactRegistry,
    crop: dict[str, Any] | None = None,
) -> dict[str, Any]:
    crop = crop or {}
    crop_start, crop_end = crop_bounds(crop)
    generated_at = datetime.now(timezone.utc).isoformat()
    all_rows, raw_selected_count = collect_session_rows(session, crop_start, crop_end)
    final_rows, duplicate_time_removed_count = dedupe_rows_by_time(all_rows)
    if not final_rows:
        raise ValueError("当前裁剪范围内无有效数据")

    segments = build_segments(final_rows)
    products = sorted({str(row["hpm_product"]) for row in final_rows if row.get("hpm_product")})
    product_status = product_type_status(products)
    processing_summary = {
        "uploaded_file_count": len(session.get("per_file_records", [])),
        "unique_file_count": sum(1 for record in session.get("per_file_records", []) if record.get("status") == "ok" and not record.get("duplicate_of")),
        "duplicate_file_count": int(session.get("dedupe", {}).get("duplicate_file_count", 0)),
        "raw_sample_count": int(raw_selected_count),
        "merged_sample_count": len(final_rows),
        "duplicate_time_removed_count": int(duplicate_time_removed_count),
        "sorted_by_time": True,
        "dedup_by_time": True,
        "segment_count": len(segments),
        "crop_applied": bool(crop_start is not None or crop_end is not None),
        "crop_start": format_utc_millis(crop_start) if crop_start is not None else None,
        "crop_end": format_utc_millis(crop_end) if crop_end is not None else None,
        "final_sample_count": len(final_rows),
    }
    time_range = {
        "start_time": format_utc_millis(int(final_rows[0]["time_ms"])),
        "end_time": format_utc_millis(int(final_rows[-1]["time_ms"])),
        "display_start_time": format_beijing_millis(int(final_rows[0]["time_ms"])),
        "display_end_time": format_beijing_millis(int(final_rows[-1]["time_ms"])),
    }
    overall_statistics = {
        "time_coverage": time_coverage_statistics(final_rows, processing_summary, segments),
        "sampling": sampling_statistics(final_rows),
        "magnetic": magnetic_statistics(final_rows, product_status),
        "position": position_statistics(final_rows),
        "quality_flags": quality_flag_statistics(final_rows),
    }
    per_file_statistics = per_file_statistics_for_session(session, crop_start, crop_end)
    per_segment_statistics = [
        segment_statistics(segment, final_rows)
        for segment in segments
    ]
    quality_stats = quality_flag_statistics(final_rows)
    warnings: list[str] = []
    if product_status["status"] == "mixed":
        warnings.append("mixed_product_types_not_supported_for_overall_magnetic_stats")
    if overall_statistics["sampling"].get("gap_count", 0):
        warnings.append("存在 large gap，per_segment_statistics 已按连续时间段分别统计")
    errors: list[str] = []
    result = {
        "session_id": session["upload_session_id"],
        "product_type_status": product_status,
        "time_range": time_range,
        "processing_summary": processing_summary,
        "overall_statistics": overall_statistics,
        "per_file_statistics": per_file_statistics,
        "per_segment_statistics": per_segment_statistics,
        "quality_flag_statistics": quality_stats,
        "warnings": warnings,
        "errors": errors,
        "generated_at": generated_at,
    }
    output_payload = write_statistics_outputs(result, session, config, artifacts, crop)
    result.update(output_payload)
    return json_safe_statistics(result)


def collect_session_rows(session: dict[str, Any], crop_start: int | None, crop_end: int | None) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    raw_selected_count = 0
    records = [record for record in session.get("per_file_records", []) if record.get("status") == "ok" and record.get("time_parseable")]
    for record in records:
        file_rows, selected = collect_file_rows(record, crop_start, crop_end)
        raw_selected_count += selected
        rows.extend(file_rows)
    rows.sort(key=lambda item: int(item["time_ms"]))
    return rows, raw_selected_count


def collect_file_rows(record: dict[str, Any], crop_start: int | None, crop_end: int | None) -> tuple[list[dict[str, Any]], int]:
    path = Path(record["stored_path"])
    rows: list[dict[str, Any]] = []
    with h5py.File(path, "r") as h5:
        time_ms = parse_cses_utc_time_millis(np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1))
        mask = crop_mask(time_ms, crop_start, crop_end)
        indices = np.where(mask)[0]
        if not indices.size:
            return [], 0
        product = str(record.get("hpm_product") or "unknown")
        vector = np.asarray(h5[VECTOR_FIELD.strip("/")][:], dtype=float) if has_dataset(h5, VECTOR_FIELD) else None
        scalar = read_optional_1d(h5, SCALAR_FIELD) if has_dataset(h5, SCALAR_FIELD) else np.asarray([])
        positions = {field: read_optional_1d(h5, field) for field in POSITION_FIELDS}
        position_units = {field: dataset_unit(h5, field, POSITION_DEFAULT_UNITS.get(field)) for field in POSITION_FIELDS if has_dataset(h5, field)}
        flags = {field: np.asarray(h5[field.strip("/")][:]).reshape(-1) for field in QUALITY_FIELDS if has_dataset(h5, field)}
        vector_unit = dataset_unit(h5, VECTOR_FIELD, "nT") if has_dataset(h5, VECTOR_FIELD) else None
        scalar_unit = dataset_unit(h5, SCALAR_FIELD, "nT") if has_dataset(h5, SCALAR_FIELD) else None
        for idx in indices:
            row: dict[str, Any] = {
                "time_ms": int(time_ms[idx]),
                "upload_id": record.get("upload_id"),
                "filename": record.get("filename"),
                "hpm_product": product,
                "duplicate_file": bool(record.get("duplicate_of")),
                "magnetic_unit": vector_unit if product == "HPM_5" else scalar_unit,
                "position_units": position_units,
                "flags_present": sorted(flags),
            }
            if product == "HPM_5" and vector is not None and vector.ndim == 2 and idx < vector.shape[0] and vector.shape[1] >= 3:
                values = vector[idx, :3].astype(float)
                row["Bx"] = float(values[0])
                row["By"] = float(values[1])
                row["Bz"] = float(values[2])
                row["B_abs"] = float(np.linalg.norm(values))
            elif product == "HPM_6" and scalar.size:
                row["scalar_B"] = optional_value(scalar, int(idx))
            for field, values in positions.items():
                row[field.strip("/")] = optional_value(values, int(idx))
            for field, values in flags.items():
                row[field] = scalar_json_value(values[idx]) if idx < values.size else None
            rows.append(row)
    return rows, int(indices.size)


def product_type_status(products: list[str]) -> dict[str, Any]:
    if not products:
        return {"status": "unavailable", "products": [], "reason": "no_parseable_product"}
    if len(products) == 1:
        return {"status": "single", "products": products, "product_type": products[0]}
    return {"status": "mixed", "products": products, "reason": "mixed_product_types_not_supported_for_overall_magnetic_stats"}


def time_coverage_statistics(rows: list[dict[str, Any]], processing_summary: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    start_ms = int(rows[0]["time_ms"])
    end_ms = int(rows[-1]["time_ms"])
    return {
        "start_time": format_utc_millis(start_ms),
        "end_time": format_utc_millis(end_ms),
        "display_start_time": format_beijing_millis(start_ms),
        "display_end_time": format_beijing_millis(end_ms),
        "duration_seconds": safe_float((end_ms - start_ms) / 1000),
        "sample_count": len(rows),
        "valid_time_count": len(rows),
        "duplicate_time_removed_count": int(processing_summary["duplicate_time_removed_count"]),
        "segment_count": len(segments),
    }


def sampling_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = np.asarray([int(row["time_ms"]) for row in rows], dtype=np.float64)
    diffs = np.diff(times) / 1000.0
    positive = diffs[diffs > 0]
    if positive.size:
        median = float(np.median(positive))
        threshold = max(5.0, 2.5 * median)
        large_indices = np.where(positive > threshold)[0]
        large_ranges = [
            {
                "start": format_utc_millis(int(times[index])),
                "end": format_utc_millis(int(times[index + 1])),
                "display_start": format_beijing_millis(int(times[index])),
                "display_end": format_beijing_millis(int(times[index + 1])),
                "gap_seconds": safe_float(positive[index]),
            }
            for index in large_indices
        ]
        return {
            "cadence_median_seconds": safe_float(median),
            "cadence_min_seconds": safe_float(np.min(positive)),
            "cadence_max_seconds": safe_float(np.max(positive)),
            "cadence_mean_seconds": safe_float(np.mean(positive)),
            "cadence_std_seconds": safe_float(np.std(positive)),
            "gap_count": int(large_indices.size),
            "large_gap_threshold_seconds": safe_float(threshold),
            "large_gap_threshold_rule": LARGE_GAP_RULE,
            "large_gap_ranges": large_ranges,
        }
    return {
        "cadence_median_seconds": None,
        "cadence_min_seconds": None,
        "cadence_max_seconds": None,
        "cadence_mean_seconds": None,
        "cadence_std_seconds": None,
        "gap_count": 0,
        "large_gap_threshold_seconds": 5.0,
        "large_gap_threshold_rule": LARGE_GAP_RULE,
        "large_gap_ranges": [],
    }


def magnetic_statistics(rows: list[dict[str, Any]], product_status: dict[str, Any]) -> dict[str, Any]:
    if product_status.get("status") == "mixed":
        return {
            "status": "unavailable",
            "reason": "mixed_product_types_not_supported_for_overall_magnetic_stats",
            "variables": {},
        }
    product = product_status.get("product_type")
    if product == "HPM_6":
        return {"status": "ok", "product_type": product, "variables": {"scalar_B": extended_numeric_stats([row.get("scalar_B") for row in rows], unit=unit_from_rows(rows, "magnetic_unit", "nT"))}}
    if product == "HPM_5":
        unit = unit_from_rows(rows, "magnetic_unit", "nT")
        return {
            "status": "ok",
            "product_type": product,
            "variables": {
                "Bx": extended_numeric_stats([row.get("Bx") for row in rows], unit=unit),
                "By": extended_numeric_stats([row.get("By") for row in rows], unit=unit),
                "Bz": extended_numeric_stats([row.get("Bz") for row in rows], unit=unit),
                "B_abs": extended_numeric_stats([row.get("B_abs") for row in rows], unit=unit),
            },
        }
    return {"status": "unavailable", "reason": "unsupported_or_missing_product_type", "variables": {}}


def position_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for field in POSITION_FIELDS:
        name = field.strip("/")
        values = [row.get(name) for row in rows]
        present = any(value is not None for value in values)
        if present:
            unit = position_unit_from_rows(rows, field)
            variables[name] = basic_numeric_stats(values, unit=unit)
        else:
            variables[name] = {"status": "missing", "unit": POSITION_DEFAULT_UNITS.get(field)}
    return {"status": "ok", "variables": variables}


def quality_flag_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in QUALITY_FIELDS:
        values = [row.get(field) for row in rows if field in row]
        if not values:
            result[field] = {"status": "missing", "value_counts": {}, "value_percent": {}, "total_count": 0}
            continue
        counts: dict[str, int] = {}
        for value in values:
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
        total = sum(counts.values())
        result[field] = {
            "status": "ok",
            "value_counts": dict(sorted(counts.items())),
            "value_percent": {key: safe_float(count / total * 100.0) for key, count in sorted(counts.items())},
            "total_count": total,
        }
    return result


def per_file_statistics_for_session(session: dict[str, Any], crop_start: int | None, crop_end: int | None) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for record in session.get("per_file_records", []):
        if record.get("status") != "ok" or not record.get("time_parseable"):
            stats.append({"upload_id": record.get("upload_id"), "filename": record.get("filename"), "status": "unavailable", "reason": "file_not_parseable"})
            continue
        rows, raw_count = collect_file_rows(record, crop_start, crop_end)
        deduped, duplicate_time_removed_count = dedupe_rows_by_time(rows)
        if not deduped:
            stats.append({"upload_id": record.get("upload_id"), "filename": record.get("filename"), "status": "empty_after_crop"})
            continue
        segments = build_segments(deduped)
        processing = {
            "duplicate_time_removed_count": duplicate_time_removed_count,
            "final_sample_count": len(deduped),
        }
        product_status = product_type_status(sorted({str(row["hpm_product"]) for row in deduped if row.get("hpm_product")}))
        stats.append(
            {
                "upload_id": record.get("upload_id"),
                "filename": record.get("filename"),
                "duplicate_of": record.get("duplicate_of"),
                "status": "ok",
                "hpm_product": record.get("hpm_product"),
                "raw_sample_count": raw_count,
                "time_coverage": time_coverage_statistics(deduped, processing, segments),
                "sampling": sampling_statistics(deduped),
                "magnetic": magnetic_statistics(deduped, product_status),
                "position": position_statistics(deduped),
                "quality_flags": quality_flag_statistics(deduped),
            }
        )
    return stats


def segment_statistics(segment: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    start_ms = int(segment["start_ms"])
    end_ms = int(segment["end_ms"])
    segment_rows = [row for row in rows if start_ms <= int(row["time_ms"]) <= end_ms]
    product_status = product_type_status(sorted({str(row["hpm_product"]) for row in segment_rows if row.get("hpm_product")}))
    processing = {"duplicate_time_removed_count": 0, "final_sample_count": len(segment_rows)}
    return {
        "segment_id": segment["segment_id"],
        "time_coverage": time_coverage_statistics(segment_rows, processing, [segment]),
        "sampling": sampling_statistics(segment_rows),
        "magnetic": magnetic_statistics(segment_rows, product_status),
        "position": position_statistics(segment_rows),
        "quality_flags": quality_flag_statistics(segment_rows),
    }


def basic_numeric_stats(values: list[Any], *, unit: str | None = None) -> dict[str, Any]:
    arr = numeric_array(values)
    finite = arr[np.isfinite(arr)]
    nan_count = int(arr.size - finite.size)
    if not finite.size:
        return {
            "status": "empty",
            "finite_count": 0,
            "nan_count": nan_count,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None,
            "q25": None,
            "q75": None,
            "unit": unit,
        }
    return {
        "status": "ok",
        "finite_count": int(finite.size),
        "nan_count": nan_count,
        "min": safe_float(np.min(finite)),
        "max": safe_float(np.max(finite)),
        "mean": safe_float(np.mean(finite)),
        "median": safe_float(np.median(finite)),
        "std": safe_float(np.std(finite)),
        "q25": safe_float(np.percentile(finite, 25)),
        "q75": safe_float(np.percentile(finite, 75)),
        "unit": unit,
    }


def extended_numeric_stats(values: list[Any], *, unit: str | None = None) -> dict[str, Any]:
    base = basic_numeric_stats(values, unit=unit)
    if base.get("status") != "ok":
        return {**base, "iqr": None, "rms": None, "peak_to_peak": None}
    arr = numeric_array(values)
    finite = arr[np.isfinite(arr)]
    return {
        **base,
        "iqr": safe_float(float(base["q75"]) - float(base["q25"])),
        "rms": safe_float(np.sqrt(np.mean(finite * finite))),
        "peak_to_peak": safe_float(np.max(finite) - np.min(finite)),
    }


def numeric_array(values: list[Any]) -> np.ndarray:
    output: list[float] = []
    for value in values:
        if value is None:
            output.append(np.nan)
        else:
            try:
                output.append(float(value))
            except (TypeError, ValueError):
                output.append(np.nan)
    return np.asarray(output, dtype=float)


def dataset_unit(h5: h5py.File, field: str, default: str | None = None) -> str | None:
    if not has_dataset(h5, field):
        return default
    attrs = h5[field.strip("/")].attrs
    for key in ("Units", "units", "Unit", "unit"):
        if key in attrs:
            return str(scalar_json_value(attrs[key]))
    return default


def unit_from_rows(rows: list[dict[str, Any]], key: str, default: str | None = None) -> str | None:
    for row in rows:
        value = row.get(key)
        if value:
            return str(value)
    return default


def position_unit_from_rows(rows: list[dict[str, Any]], field: str) -> str | None:
    for row in rows:
        units = row.get("position_units") or {}
        if field in units:
            return units[field]
    return POSITION_DEFAULT_UNITS.get(field)


def write_statistics_outputs(
    result: dict[str, Any],
    session: dict[str, Any],
    config: AppConfig,
    artifacts: ArtifactRegistry,
    crop: dict[str, Any],
) -> dict[str, Any]:
    digest = request_digest(
        {
            "session_id": session["upload_session_id"],
            "crop": crop,
            "generated_at": result["generated_at"],
            "final_sample_count": result["processing_summary"]["final_sample_count"],
        }
    )
    out_dir = config.outputs_root / "statistics" / "cses_hpm" / session["upload_session_id"] / digest
    out_dir.mkdir(parents=True, exist_ok=True)
    stats_path = out_dir / "statistics.json"
    summary_path = out_dir / "statistics_summary.csv"
    manifest_path = out_dir / "manifest.json"
    manifest = {
        "session_id": session["upload_session_id"],
        "uploaded_files": [
            {
                "upload_id": record.get("upload_id"),
                "filename": record.get("filename"),
                "stored_path": record.get("stored_path"),
                "duplicate_of": record.get("duplicate_of"),
                "hpm_product": record.get("hpm_product"),
            }
            for record in session.get("per_file_records", [])
        ],
        "crop_range": crop,
        "sort_and_dedupe": {
            "sorted_by_time": True,
            "dedup_by_time": True,
            "duplicate_file_count": result["processing_summary"]["duplicate_file_count"],
            "duplicate_time_removed_count": result["processing_summary"]["duplicate_time_removed_count"],
        },
        "segments": [
            {
                "segment_id": item["segment_id"],
                "start_time": item["time_coverage"]["start_time"],
                "end_time": item["time_coverage"]["end_time"],
                "sample_count": item["time_coverage"]["sample_count"],
            }
            for item in result["per_segment_statistics"]
        ],
        "statistics_variables": statistics_variables(result),
        "large_gap_threshold_rule": LARGE_GAP_RULE,
        "outputs": {
            "statistics_json": str(stats_path),
            "statistics_summary_csv": str(summary_path),
            "manifest_json": str(manifest_path),
        },
        "generated_at": result["generated_at"],
    }
    result_for_file = {**result, "manifest": manifest}
    stats_path.write_text(json.dumps(json_safe_statistics(result_for_file), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    write_summary_csv(summary_path, result)
    manifest_path.write_text(json.dumps(json_safe_statistics(manifest), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    stats_artifact = artifacts.register(
        f"cses_hpm_upload:statistics:{session['upload_session_id']}:{digest}:json",
        stats_path,
        media_type="application/json",
        label="CSES HPM feature statistics JSON",
    )
    summary_artifact = artifacts.register(
        f"cses_hpm_upload:statistics:{session['upload_session_id']}:{digest}:summary_csv",
        summary_path,
        media_type="text/csv",
        label="CSES HPM feature statistics summary CSV",
    )
    manifest_artifact = artifacts.register(
        f"cses_hpm_upload:statistics:{session['upload_session_id']}:{digest}:manifest",
        manifest_path,
        media_type="application/json",
        label="CSES HPM feature statistics manifest",
    )
    return {
        "manifest": manifest,
        "artifacts": {
            "statistics_json": stats_artifact,
            "statistics_summary_csv": summary_artifact,
            "manifest_json": manifest_artifact,
        },
    }


def write_summary_csv(path: Path, result: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    append_variable_rows(rows, "overall", "", "", result.get("overall_statistics", {}).get("magnetic", {}).get("variables", {}))
    append_variable_rows(rows, "overall", "", "", result.get("overall_statistics", {}).get("position", {}).get("variables", {}))
    for item in result.get("per_file_statistics", []):
        append_variable_rows(rows, "per_file", item.get("segment_id", ""), item.get("filename", ""), item.get("magnetic", {}).get("variables", {}))
        append_variable_rows(rows, "per_file", item.get("segment_id", ""), item.get("filename", ""), item.get("position", {}).get("variables", {}))
    for item in result.get("per_segment_statistics", []):
        append_variable_rows(rows, "per_segment", item.get("segment_id", ""), "", item.get("magnetic", {}).get("variables", {}))
        append_variable_rows(rows, "per_segment", item.get("segment_id", ""), "", item.get("position", {}).get("variables", {}))
    fieldnames = ["scope", "segment_id", "file", "variable", "count", "min", "max", "mean", "median", "std", "q25", "q75", "iqr", "unit"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_variable_rows(rows: list[dict[str, Any]], scope: str, segment_id: str, filename: str, variables: dict[str, Any]) -> None:
    for variable, stats in variables.items():
        if not isinstance(stats, dict) or stats.get("status") == "missing":
            continue
        rows.append(
            {
                "scope": scope,
                "segment_id": segment_id,
                "file": filename,
                "variable": variable,
                "count": stats.get("finite_count"),
                "min": stats.get("min"),
                "max": stats.get("max"),
                "mean": stats.get("mean"),
                "median": stats.get("median"),
                "std": stats.get("std"),
                "q25": stats.get("q25"),
                "q75": stats.get("q75"),
                "iqr": stats.get("iqr"),
                "unit": stats.get("unit"),
            }
        )


def statistics_variables(result: dict[str, Any]) -> list[str]:
    variables: set[str] = set()
    for category in ("magnetic", "position"):
        variables.update((result.get("overall_statistics", {}).get(category, {}).get("variables") or {}).keys())
    return sorted(variables)


def scalar_json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        if value.shape == ():
            return scalar_json_value(value.item())
        return [scalar_json_value(item) for item in value.reshape(-1).tolist()]
    if isinstance(value, np.generic):
        return scalar_json_value(value.item())
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def json_safe_statistics(value: Any) -> Any:
    if isinstance(value, np.generic):
        return json_safe_statistics(value.item())
    if isinstance(value, np.ndarray):
        return json_safe_statistics(value.tolist())
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [json_safe_statistics(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe_statistics(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_statistics(item) for key, item in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
