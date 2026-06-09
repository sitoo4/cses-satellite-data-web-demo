#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.datasources.cses_hpm import format_utc_millis, parse_cses_utc_time_millis  # noqa: E402
from app.services.cses_hpm_statistics import (  # noqa: E402
    magnetic_statistics,
    position_statistics,
    product_type_status,
    quality_flag_statistics,
    sampling_statistics,
    segment_statistics,
    time_coverage_statistics,
)
from app.services.cses_hpm_uploads import (  # noqa: E402
    ALT_FIELD,
    LAT_FIELD,
    LON_FIELD,
    QUALITY_FIELDS,
    TIME_FIELD,
    VECTOR_FIELD,
    build_crop_options,
    build_plot_groups,
    build_segments,
    dedupe_rows_by_time,
    draw_magnetic_segments,
    format_beijing_millis,
    has_dataset,
    json_safe,
    read_optional_1d,
    rows_by_plot_groups,
    rows_by_segments,
    value_distribution,
    write_interactive_orbit_html,
)


POSITION_FIELDS = ("/GEO_LAT", "/GEO_LON", "/ALTITUDE", "/MAG_LAT", "/MAG_LON")
POSITION_DEFAULT_UNITS = {
    "/GEO_LAT": "deg",
    "/GEO_LON": "deg",
    "/ALTITUDE": "km",
    "/MAG_LAT": "deg",
    "/MAG_LON": "deg",
}
DEMO_SESSION_ID = "static-public-demo"
MAGNETIC_DOWNSAMPLE_SECONDS = 60
ORBIT_DOWNSAMPLE_SECONDS = 120
NOISE_SEED = 20260609
NOISE_STD_FRACTION = 0.005
DERIVED_FILES = (
    "demo_manifest.json",
    "demo_summary.json",
    "magnetic_sanitized_downsampled.json",
    "orbit_points_sanitized.json",
    "demo_statistics.json",
    "demo_statistics_summary.csv",
    "magnetic_overview.png",
    "orbit_demo.html",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build sanitized static CSES HPM demo files for GitHub Pages.")
    parser.add_argument("--input-file", action="append", required=True, help="Local CSES HPM H5 file used only to generate sanitized derived demo files.")
    parser.add_argument("--outdir", type=Path, default=REPO_ROOT / "frontend" / "public" / "demo_data")
    parser.add_argument("--magnetic-downsample-sec", type=int, default=MAGNETIC_DOWNSAMPLE_SECONDS)
    parser.add_argument("--orbit-downsample-sec", type=int, default=ORBIT_DOWNSAMPLE_SECONDS)
    args = parser.parse_args()

    input_files = [Path(item).expanduser().resolve() for item in args.input_file]
    for path in input_files:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in {".h5", ".hdf5"}:
            raise ValueError(f"not an H5 file: {path}")

    outdir = args.outdir.resolve()
    clean_output_dir(outdir)

    source_records: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for index, path in enumerate(input_files, start=1):
        source_id = f"demo_segment_{index:02d}"
        record, rows = read_demo_source(path, source_id)
        source_records.append(record)
        all_rows.extend(rows)

    all_rows.sort(key=lambda item: int(item["time_ms"]))
    deduped_rows, duplicate_time_removed_count = dedupe_rows_by_time(all_rows)
    if not deduped_rows:
        raise ValueError("no parseable rows found")

    segments = add_display_to_segments(build_segments(deduped_rows))
    plot_groups = sanitize_plot_groups(build_plot_groups(segments))
    magnetic_points = downsample_magnetic_points(deduped_rows, segments, args.magnetic_downsample_sec)
    orbit_points = downsample_orbit_points(deduped_rows, segments, args.orbit_downsample_sec)
    statistics = build_sanitized_statistics(source_records, deduped_rows, segments, duplicate_time_removed_count)
    artifacts = static_artifact_payloads()
    statistics["artifacts"] = {
        "statistics_json": artifacts["statistics_json"],
        "statistics_summary_csv": artifacts["statistics_summary_csv"],
        "manifest_json": artifacts["manifest_json"],
    }

    write_json(outdir / "magnetic_sanitized_downsampled.json", build_magnetic_payload(magnetic_points, segments, args.magnetic_downsample_sec))
    write_json(outdir / "orbit_points_sanitized.json", build_orbit_payload(orbit_points, segments, args.orbit_downsample_sec))
    draw_magnetic_segments(outdir / "magnetic_overview.png", magnetic_plot_groups_from_sanitized(magnetic_points, segments, plot_groups), "HPM_5")
    write_interactive_orbit_html(outdir / "orbit_demo.html", orbit_segments_from_sanitized(orbit_points, segments), segments, plot_groups)

    session = build_static_session(source_records, deduped_rows, segments, plot_groups, duplicate_time_removed_count, statistics)
    manifest = build_manifest(source_records, deduped_rows, segments, plot_groups, magnetic_points, orbit_points, args.magnetic_downsample_sec, args.orbit_downsample_sec)
    summary = {
        "static_demo": True,
        "mode": "github_pages_static_sanitized",
        "notice": "当前为 GitHub Pages 静态 demo，展示预生成脱敏派生数据，不支持上传或实时 H5 解析。",
        "privacy": manifest["privacy"],
        "session": session,
        "plots": {
            "magnetic": artifacts["magnetic_overview"],
            "orbit": artifacts["orbit_demo"],
        },
        "downloads": {
            "statistics_json": artifacts["statistics_json"],
            "statistics_summary_csv": artifacts["statistics_summary_csv"],
            "manifest_json": artifacts["manifest_json"],
        },
    }

    write_json(outdir / "demo_manifest.json", manifest)
    write_json(outdir / "demo_summary.json", summary)
    write_json(outdir / "demo_statistics.json", statistics)
    write_summary_csv(outdir / "demo_statistics_summary.csv", statistics)
    remove_macos_sidecar_files(outdir)

    print(f"Wrote sanitized static public demo files to {outdir}")
    for name in DERIVED_FILES:
        path = outdir / name
        print(f"- {name}: {path.stat().st_size} bytes")
    print(f"Magnetic demo points: {len(magnetic_points)}")
    print(f"Orbit demo points: {len(orbit_points)}")
    return 0


def clean_output_dir(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    for path in outdir.iterdir():
        if path.is_file():
            path.unlink()


def remove_macos_sidecar_files(outdir: Path) -> None:
    for path in outdir.glob("._*"):
        if path.is_file():
            path.unlink()


def read_demo_source(path: Path, source_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    with h5py.File(path, "r") as h5:
        time_ms = parse_cses_utc_time_millis(np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1))
        vector = np.asarray(h5[VECTOR_FIELD.strip("/")][:], dtype=float)
        positions = {field: read_optional_1d(h5, field) for field in POSITION_FIELDS}
        flags = {field: np.asarray(h5[field.strip("/")][:]).reshape(-1) for field in QUALITY_FIELDS if has_dataset(h5, field)}
        position_units = {field: dataset_unit(h5, field, POSITION_DEFAULT_UNITS.get(field)) for field in POSITION_FIELDS if has_dataset(h5, field)}
        magnetic_unit = dataset_unit(h5, VECTOR_FIELD, "nT")
        quality_summary = {
            field: {
                "label": quality_flag_field_label(field),
                "distribution": value_distribution(values),
                "value_counts": value_distribution(values),
                "value_percent": percent_distribution(value_distribution(values)),
                "sample_count": int(values.size),
            }
            for field, values in flags.items()
        }
        for idx, value_ms in enumerate(time_ms):
            if idx >= vector.shape[0]:
                continue
            vec = vector[idx, :3].astype(float)
            if not np.all(np.isfinite(vec)) or np.any(vec <= -999990):
                bx = by = bz = b_abs = None
            else:
                bx, by, bz = (float(vec[0]), float(vec[1]), float(vec[2]))
                b_abs = float(np.linalg.norm(vec))
            row: dict[str, Any] = {
                "time_ms": int(value_ms),
                "source_id": source_id,
                "filename": source_id,
                "hpm_product": "HPM_5",
                "magnetic_unit": magnetic_unit,
                "position_units": position_units,
                "Bx": bx,
                "By": by,
                "Bz": bz,
                "B_abs": b_abs,
            }
            for field, values in positions.items():
                row[field.strip("/")] = finite_or_none(values, idx)
            for field, values in flags.items():
                row[field] = scalar_or_none(values, idx)
            rows.append(row)

    rows.sort(key=lambda item: int(item["time_ms"]))
    record = {
        "upload_id": source_id,
        "filename": source_id,
        "display_name": source_id,
        "size_bytes": 0,
        "duplicate_of": None,
        "status": "ok",
        "hpm_product": "HPM_5",
        "sample_count": len(rows),
        "time_parseable": bool(rows),
        "start_time": format_utc_millis(int(rows[0]["time_ms"])) if rows else None,
        "end_time": format_utc_millis(int(rows[-1]["time_ms"])) if rows else None,
        "display_start_time": format_beijing_millis(int(rows[0]["time_ms"])) if rows else None,
        "display_end_time": format_beijing_millis(int(rows[-1]["time_ms"])) if rows else None,
        "has_vector_magnetic": True,
        "has_scalar_magnetic": False,
        "quality_flag_summary": quality_summary,
        "warnings": [],
        "errors": [],
    }
    return record, rows


def dataset_unit(h5: h5py.File, field: str, default: str | None = None) -> str | None:
    if not has_dataset(h5, field):
        return default
    attrs = h5[field.strip("/")].attrs
    for key in ("Units", "units", "Unit", "unit"):
        if key in attrs:
            return dataset_scalar(attrs[key])
    return default


def dataset_scalar(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.shape == ():
        return dataset_scalar(value.item())
    if isinstance(value, np.generic):
        return dataset_scalar(value.item())
    return str(value)


def finite_or_none(values: np.ndarray, index: int) -> float | None:
    if index >= values.size:
        return None
    value = float(values[index])
    if not math.isfinite(value) or value <= -9990:
        return None
    return value


def scalar_or_none(values: np.ndarray, index: int) -> Any:
    if index >= values.size:
        return None
    value = values[index]
    if isinstance(value, np.generic):
        return value.item()
    return value


def add_display_to_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for segment in segments:
        output.append(
            {
                **segment,
                "display_start": format_beijing_millis(int(segment["start_ms"])),
                "display_end": format_beijing_millis(int(segment["end_ms"])),
            }
        )
    return output


def sanitize_plot_groups(plot_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **group,
            "display_start": group.get("display_start"),
            "display_end": group.get("display_end"),
        }
        for group in plot_groups
    ]


def downsample_magnetic_points(rows: list[dict[str, Any]], segments: list[dict[str, Any]], interval_seconds: int) -> list[dict[str, Any]]:
    rng = np.random.default_rng(NOISE_SEED)
    stds = {
        key: np.nanstd([float(row[key]) for row in rows if isinstance(row.get(key), (int, float)) and math.isfinite(float(row[key]))])
        for key in ("Bx", "By", "Bz")
    }
    points: list[dict[str, Any]] = []
    for segment in segments:
        selected = rows_for_segment(rows, segment)
        if not selected:
            continue
        target = int(selected[0]["time_ms"])
        last_ms = int(selected[-1]["time_ms"])
        idx = 0
        while target <= last_ms and idx < len(selected):
            while idx + 1 < len(selected) and int(selected[idx]["time_ms"]) < target:
                idx += 1
            row = selected[idx]
            if not all(isinstance(row.get(key), (int, float)) and math.isfinite(float(row[key])) for key in ("Bx", "By", "Bz", "B_abs")):
                target += interval_seconds * 1000
                continue
            noisy = {}
            for key in ("Bx", "By", "Bz"):
                value = float(row[key])
                sigma = max(abs(value) * 0.001, float(stds[key]) * NOISE_STD_FRACTION)
                noisy[key] = value + float(rng.normal(0.0, sigma))
            b_abs = math.sqrt(noisy["Bx"] ** 2 + noisy["By"] ** 2 + noisy["Bz"] ** 2)
            points.append(
                {
                    "time_label": relative_label(int(row["time_ms"]), int(rows[0]["time_ms"])),
                    "display_time": format_beijing_millis(int(row["time_ms"])),
                    "segment_id": segment["segment_id"],
                    "source_id": row["source_id"],
                    "Bx_demo": round(noisy["Bx"], 1),
                    "By_demo": round(noisy["By"], 1),
                    "Bz_demo": round(noisy["Bz"], 1),
                    "B_abs_demo": round(b_abs, 1),
                }
            )
            target += interval_seconds * 1000
    return points


def downsample_orbit_points(rows: list[dict[str, Any]], segments: list[dict[str, Any]], interval_seconds: int) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for segment in segments:
        selected = rows_for_segment(rows, segment)
        if not selected:
            continue
        target = int(selected[0]["time_ms"])
        last_ms = int(selected[-1]["time_ms"])
        idx = 0
        while target <= last_ms and idx < len(selected):
            while idx + 1 < len(selected) and int(selected[idx]["time_ms"]) < target:
                idx += 1
            row = selected[idx]
            if not all(isinstance(row.get(key), (int, float)) and math.isfinite(float(row[key])) for key in ("GEO_LAT", "GEO_LON", "ALTITUDE")):
                target += interval_seconds * 1000
                continue
            points.append(
                {
                    "time_label": relative_label(int(row["time_ms"]), int(rows[0]["time_ms"])),
                    "display_time": format_beijing_millis(int(row["time_ms"])),
                    "segment_id": segment["segment_id"],
                    "source_id": row["source_id"],
                    "GEO_LAT": round(float(row["GEO_LAT"]), 2),
                    "GEO_LON": round(float(row["GEO_LON"]), 2),
                    "ALTITUDE": round(float(row["ALTITUDE"]), 1),
                    "MAG_LAT": round(float(row["MAG_LAT"]), 2) if isinstance(row.get("MAG_LAT"), (int, float)) and math.isfinite(float(row["MAG_LAT"])) else None,
                    "MAG_LON": round(float(row["MAG_LON"]), 2) if isinstance(row.get("MAG_LON"), (int, float)) and math.isfinite(float(row["MAG_LON"])) else None,
                }
            )
            target += interval_seconds * 1000
    return points


def rows_for_segment(rows: list[dict[str, Any]], segment: dict[str, Any]) -> list[dict[str, Any]]:
    start_ms = int(segment["start_ms"])
    end_ms = int(segment["end_ms"])
    return [row for row in rows if start_ms <= int(row["time_ms"]) <= end_ms]


def relative_label(value_ms: int, origin_ms: int) -> str:
    total = max(0, int(round((value_ms - origin_ms) / 1000)))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"T+{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_magnetic_payload(points: list[dict[str, Any]], segments: list[dict[str, Any]], interval_seconds: int) -> dict[str, Any]:
    return {
        "description": "Sanitized downsampled magnetic data for static visualization only.",
        "downsample_interval_seconds": interval_seconds,
        "rounding": {"magnetic_nT_decimal_places": 1},
        "noise": {"seed": NOISE_SEED, "std_fraction_of_component_std": NOISE_STD_FRACTION, "deterministic": True},
        "point_count": len(points),
        "segments": public_segment_ranges(segments, include_internal_ms=False),
        "points": points,
    }


def build_orbit_payload(points: list[dict[str, Any]], segments: list[dict[str, Any]], interval_seconds: int) -> dict[str, Any]:
    return {
        "description": "Sanitized downsampled orbit points for static visualization only.",
        "downsample_interval_seconds": interval_seconds,
        "rounding": {"lat_lon_decimal_places": 2, "altitude_km_decimal_places": 1},
        "point_count": len(points),
        "segments": public_segment_ranges(segments, include_internal_ms=False),
        "points": points,
    }


def magnetic_plot_groups_from_sanitized(points: list[dict[str, Any]], segments: list[dict[str, Any]], plot_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "time_ms": public_point_time_ms(point, segments),
            "values": [point["Bx_demo"], point["By_demo"], point["Bz_demo"]],
            "source_id": point.get("source_id"),
        }
        for point in points
    ]
    return rows_by_plot_groups(rows_by_segments(rows, segments), plot_groups)


def orbit_segments_from_sanitized(points: list[dict[str, Any]], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "time_ms": public_point_time_ms(point, segments),
            "lat": point["GEO_LAT"],
            "lon": point["GEO_LON"],
            "alt": point["ALTITUDE"],
            "source_id": point.get("source_id"),
        }
        for point in points
    ]
    return rows_by_segments(rows, segments)


def public_point_time_ms(point: dict[str, Any], segments: list[dict[str, Any]]) -> int:
    segment = next((item for item in segments if item["segment_id"] == point["segment_id"]), None)
    if not segment:
        return 0
    h, m, s = [int(part) for part in point["time_label"].replace("T+", "").split(":")]
    offset_ms = ((h * 3600) + (m * 60) + s) * 1000
    origin_ms = int(segments[0]["start_ms"])
    return origin_ms + offset_ms


def build_sanitized_statistics(
    source_records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    duplicate_time_removed_count: int,
) -> dict[str, Any]:
    product_status = product_type_status(["HPM_5"])
    processing_summary = {
        "uploaded_file_count": len(source_records),
        "unique_file_count": len(source_records),
        "duplicate_file_count": 0,
        "raw_sample_count": len(rows) + duplicate_time_removed_count,
        "merged_sample_count": len(rows),
        "duplicate_time_removed_count": int(duplicate_time_removed_count),
        "sorted_by_time": True,
        "dedup_by_time": True,
        "segment_count": len(segments),
        "crop_applied": False,
        "crop_start": None,
        "crop_end": None,
        "final_sample_count": len(rows),
    }
    result = {
        "session_id": DEMO_SESSION_ID,
        "product_type_status": product_status,
        "time_range": rounded_time_range(rows),
        "processing_summary": processing_summary,
        "overall_statistics": round_statistics(
            {
                "time_coverage": time_coverage_statistics(rows, processing_summary, segments),
                "sampling": sampling_statistics(rows),
                "magnetic": magnetic_statistics(rows, product_status),
                "position": position_statistics(rows),
                "quality_flags": quality_flag_statistics(rows),
            }
        ),
        "per_file_statistics": round_statistics(per_source_statistics(source_records, rows)),
        "per_segment_statistics": round_statistics([segment_statistics(segment, rows) for segment in segments]),
        "quality_flag_statistics": flag_statistics_with_labels(quality_flag_statistics(rows)),
        "warnings": [
            "static_demo_sanitized_downsampled_visualization_only",
            "not_formal_scientific_product",
            "raw_h5_not_included",
            "full_resolution_time_series_not_included",
        ],
        "errors": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return json_safe_payload(result)


def rounded_time_range(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "start_time": format_utc_millis(int(rows[0]["time_ms"])),
        "end_time": format_utc_millis(int(rows[-1]["time_ms"])),
        "display_start_time": format_beijing_millis(int(rows[0]["time_ms"])),
        "display_end_time": format_beijing_millis(int(rows[-1]["time_ms"])),
    }


def per_source_statistics(source_records: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for record in source_records:
        source_rows = [row for row in rows if row.get("source_id") == record["upload_id"]]
        if not source_rows:
            output.append({"upload_id": record["upload_id"], "filename": record["filename"], "status": "empty"})
            continue
        segments = build_segments(source_rows)
        processing = {"duplicate_time_removed_count": 0, "final_sample_count": len(source_rows)}
        output.append(
            {
                "upload_id": record["upload_id"],
                "filename": record["filename"],
                "status": "ok",
                "hpm_product": "HPM_5",
                "raw_sample_count": len(source_rows),
                "time_coverage": time_coverage_statistics(source_rows, processing, segments),
                "sampling": sampling_statistics(source_rows),
                "magnetic": magnetic_statistics(source_rows, product_type_status(["HPM_5"])),
                "position": position_statistics(source_rows),
                "quality_flags": flag_statistics_with_labels(quality_flag_statistics(source_rows)),
            }
        )
    return output


def round_statistics(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: round_statistics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [round_statistics(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 3)
    return value


def flag_statistics_with_labels(stats: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field, summary in stats.items():
        value_percent = summary.get("value_percent")
        output[field] = {
            **summary,
            "value_percent": {str(key): round(float(value), 3) for key, value in value_percent.items()} if isinstance(value_percent, dict) else value_percent,
            "label": quality_flag_field_label(field),
            "value_labels": quality_flag_value_labels(field),
        }
    return output


def quality_flag_field_label(field: str) -> str:
    labels = {
        "/FLAG_MT": "磁力矩器干扰标志",
        "/FLAG_SHW": "地影/日照状态",
        "/FLAG_TBB": "TBB 开关状态",
        "/FLAG_N3": "N3 标志",
    }
    return labels.get(field, field)


def quality_flag_value_labels(field: str) -> dict[str, str]:
    labels = {
        "/FLAG_MT": {"0": "该标志未触发", "1": "磁力矩器干扰标记"},
        "/FLAG_SHW": {"0": "该标志未触发", "1": "该标志触发"},
        "/FLAG_TBB": {"0": "该标志未触发", "1": "该标志触发"},
        "/FLAG_N3": {"0": "未标记", "1": "已标记"},
    }
    return labels.get(field, {})


def percent_distribution(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if not total:
        return {}
    return {key: round(count / total * 100, 3) for key, count in sorted(counts.items())}


def build_static_session(
    source_records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    plot_groups: list[dict[str, Any]],
    duplicate_time_removed_count: int,
    statistics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "upload_session_id": DEMO_SESSION_ID,
        "mode": "batch",
        "created_at": statistics["generated_at"],
        "per_file_records": source_records,
        "sorted_files": [
            {
                "upload_id": record["upload_id"],
                "filename": record["filename"],
                "hpm_product": record["hpm_product"],
                "start": record["start_time"],
                "end": record["end_time"],
                "display_start": record["display_start_time"],
                "display_end": record["display_end_time"],
            }
            for record in source_records
        ],
        "merged_time_range": {
            "start": format_utc_millis(int(rows[0]["time_ms"])),
            "end": format_utc_millis(int(rows[-1]["time_ms"])),
        },
        "display_time_zone": "Asia/Shanghai",
        "display_time_range": {
            "start": format_beijing_millis(int(rows[0]["time_ms"])),
            "end": format_beijing_millis(int(rows[-1]["time_ms"])),
        },
        "crop_options": build_crop_options(rows),
        "segments": public_segment_ranges(segments, include_internal_ms=False),
        "plot_groups": plot_groups,
        "sample_count": len(rows),
        "raw_sample_count": len(rows) + duplicate_time_removed_count,
        "dedupe": {"duplicate_file_count": 0, "duplicate_sample_count": duplicate_time_removed_count},
        "data_products": ["HPM_5"],
        "time_parseable": True,
        "crop_enabled": False,
        "quality_flag_summary": {
            field: {"distribution": summary.get("value_counts", {}), "sample_count": summary.get("total_count", 0), "label": summary.get("label"), "value_labels": summary.get("value_labels", {})}
            for field, summary in statistics.get("quality_flag_statistics", {}).items()
        },
        "run_log": [],
    }


def public_segment_ranges(segments: list[dict[str, Any]], *, include_internal_ms: bool = True) -> list[dict[str, Any]]:
    output = []
    for segment in segments:
        item = {
            "segment_id": segment["segment_id"],
            "source_id": segment.get("source_id"),
            "start": segment["start"],
            "end": segment["end"],
            "display_start": segment.get("display_start"),
            "display_end": segment.get("display_end"),
            "sample_count": int(segment["sample_count"]),
        }
        if include_internal_ms:
            item["start_ms"] = int(segment["start_ms"])
            item["end_ms"] = int(segment["end_ms"])
        output.append(item)
    return output


def static_artifact_payloads() -> dict[str, dict[str, Any]]:
    return {
        "magnetic_overview": {
            "artifact_id": "static-magnetic-overview",
            "label": "CSES HPM demo magnetic overview",
            "media_type": "image/png",
            "url": "demo_data/magnetic_overview.png",
            "download_url": "demo_data/magnetic_overview.png",
            "exists": True,
        },
        "orbit_demo": {
            "artifact_id": "static-orbit-demo",
            "label": "CSES HPM demo interactive orbit",
            "media_type": "text/html",
            "url": "demo_data/orbit_demo.html",
            "download_url": "demo_data/orbit_demo.html",
            "exists": True,
        },
        "statistics_json": {
            "artifact_id": "static-demo-statistics-json",
            "label": "CSES HPM demo statistics JSON",
            "media_type": "application/json",
            "url": "demo_data/demo_statistics.json",
            "download_url": "demo_data/demo_statistics.json",
            "exists": True,
        },
        "statistics_summary_csv": {
            "artifact_id": "static-demo-statistics-summary-csv",
            "label": "CSES HPM demo statistics CSV",
            "media_type": "text/csv",
            "url": "demo_data/demo_statistics_summary.csv",
            "download_url": "demo_data/demo_statistics_summary.csv",
            "exists": True,
        },
        "manifest_json": {
            "artifact_id": "static-demo-manifest-json",
            "label": "CSES HPM demo manifest JSON",
            "media_type": "application/json",
            "url": "demo_data/demo_manifest.json",
            "download_url": "demo_data/demo_manifest.json",
            "exists": True,
        },
    }


def build_manifest(
    source_records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    plot_groups: list[dict[str, Any]],
    magnetic_points: list[dict[str, Any]],
    orbit_points: list[dict[str, Any]],
    magnetic_interval_seconds: int,
    orbit_interval_seconds: int,
) -> dict[str, Any]:
    return {
        "name": "CSES HPM GitHub Pages sanitized static demo",
        "mode": "static_public_demo_sanitized",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "description": "Derived locally from six CSES-01 HPM_5 H5 files. Raw H5 files are not included.",
            "file_count": len(source_records),
            "source_labels": [record["upload_id"] for record in source_records],
            "raw_h5_included": False,
            "raw_h5_download_enabled": False,
            "real_filenames_included": False,
            "local_paths_included": False,
        },
        "sanitization": {
            "file_display_names": [record["upload_id"] for record in source_records],
            "time": "Full 1 Hz UTC_TIME arrays are not included. Demo visualization files use downsampled display labels.",
            "magnetic_downsample_interval_seconds": magnetic_interval_seconds,
            "orbit_downsample_interval_seconds": orbit_interval_seconds,
            "magnetic_rounding_decimal_places": 1,
            "orbit_lat_lon_rounding_decimal_places": 2,
            "orbit_altitude_rounding_decimal_places": 1,
            "magnetic_noise": {
                "seed": NOISE_SEED,
                "std_fraction_of_component_std": NOISE_STD_FRACTION,
                "deterministic": True,
            },
            "quality_flags": "Only value_counts and value_percent are included; no per-sample flag arrays are exported.",
            "statistics": "Aggregate descriptive statistics only; no point arrays inside statistics JSON.",
        },
        "privacy": {
            "contains_original_h5": False,
            "contains_local_absolute_paths": False,
            "contains_file_hashes": False,
            "contains_full_h5_reconstruction": False,
            "contains_full_resolution_time_series": False,
            "contains_real_h5_filenames": False,
        },
        "data_summary": {
            "product_type": "HPM_5",
            "raw_sample_count_after_time_dedupe": len(rows),
            "magnetic_demo_point_count": len(magnetic_points),
            "orbit_demo_point_count": len(orbit_points),
            "time_range_utc": {
                "start": format_utc_millis(int(rows[0]["time_ms"])),
                "end": format_utc_millis(int(rows[-1]["time_ms"])),
            },
            "time_range_beijing": {
                "start": format_beijing_millis(int(rows[0]["time_ms"])),
                "end": format_beijing_millis(int(rows[-1]["time_ms"])),
            },
            "segment_count": len(segments),
            "plot_group_count": len(plot_groups),
        },
        "derived_files": list(DERIVED_FILES),
        "limitations": [
            "Static GitHub Pages demo only.",
            "No backend API is used.",
            "No upload or browser-side H5 parsing is enabled.",
            "No full-resolution point series are included.",
            "Spectrogram/Pc5 products are not included.",
            "Statistics are descriptive demo summaries, not formal science conclusions.",
        ],
    }


def write_summary_csv(path: Path, result: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    append_variable_rows(rows, "overall", "", "", result.get("overall_statistics", {}).get("magnetic", {}).get("variables", {}))
    append_variable_rows(rows, "overall", "", "", result.get("overall_statistics", {}).get("position", {}).get("variables", {}))
    for item in result.get("per_file_statistics", []):
        append_variable_rows(rows, "per_file", "", item.get("filename", ""), item.get("magnetic", {}).get("variables", {}))
        append_variable_rows(rows, "per_file", "", item.get("filename", ""), item.get("position", {}).get("variables", {}))
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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(json_safe_payload(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def json_safe_payload(value: Any) -> Any:
    return json_safe(value)


if __name__ == "__main__":
    raise SystemExit(main())
