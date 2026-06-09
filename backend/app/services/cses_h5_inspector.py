from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np


H5_SUFFIXES = {".h5", ".hdf5", ".he5"}
METADATA_KEYS = {
    "unit",
    "units",
    "fillvalue",
    "_fillvalue",
    "fill_value",
    "valid_range",
    "valid_min",
    "valid_max",
    "description",
    "long_name",
    "standard_name",
    "coordinates",
    "scale_factor",
    "add_offset",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_safe(value: Any, *, max_items: int = 64) -> Any:
    if isinstance(value, np.generic):
        return json_safe(value.item(), max_items=max_items)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        if value.shape == ():
            return json_safe(value.item(), max_items=max_items)
        flat = value.reshape(-1)
        out = [json_safe(item, max_items=max_items) for item in flat[:max_items]]
        if flat.size > max_items:
            out.append(f"... {flat.size - max_items} more")
        return out
    if isinstance(value, (list, tuple)):
        out = [json_safe(item, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            out.append(f"... {len(value) - max_items} more")
        return out
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return str(value)
    return str(value)


def attrs_summary(attrs: h5py.AttributeManager) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key in sorted(attrs.keys(), key=str):
        value = attrs[key]
        out[str(key)] = {
            "value": json_safe(value),
            "confidence": "confirmed",
        }
    return out


def metadata_attrs(attrs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, value in attrs.items():
        normalized = key.lower().replace(" ", "_")
        compact = normalized.replace("-", "_")
        if compact in METADATA_KEYS or any(token in compact for token in ("unit", "fill", "valid", "desc", "long_name")):
            out[key] = value
    return out


def dtype_text(dtype: np.dtype | str) -> str:
    return str(dtype)


def dataset_storage_info(dataset: h5py.Dataset) -> dict[str, Any]:
    return {
        "compression": dataset.compression,
        "compression_opts": json_safe(dataset.compression_opts),
        "chunks": list(dataset.chunks) if dataset.chunks else None,
        "maxshape": list(dataset.maxshape) if dataset.maxshape else None,
    }


def safe_dataset_slice(dataset: h5py.Dataset, start: int, stop: int) -> Any:
    if dataset.shape == ():
        return dataset[()]
    selectors: list[slice] = [slice(start, stop)]
    selectors.extend(slice(None) for _ in dataset.shape[1:])
    return dataset[tuple(selectors)]


def preview_dataset(dataset: h5py.Dataset, max_preview: int) -> dict[str, Any]:
    if max_preview <= 0:
        return {"head_count": 0, "tail_count": 0, "head": [], "tail": []}
    try:
        if dataset.shape == ():
            value = json_safe(dataset[()])
            return {"head_count": 1, "tail_count": 0, "head": [value], "tail": []}
        n = int(dataset.shape[0]) if dataset.shape else 0
        head_count = min(max_preview, n)
        tail_count = min(max_preview, max(0, n - head_count))
        head = json_safe(safe_dataset_slice(dataset, 0, head_count), max_items=max_preview * 12)
        tail = []
        if tail_count:
            tail = json_safe(safe_dataset_slice(dataset, n - tail_count, n), max_items=max_preview * 12)
        return {
            "head_count": head_count,
            "tail_count": tail_count,
            "head": head,
            "tail": tail,
        }
    except Exception as exc:  # pragma: no cover - depends on unusual HDF5 dtypes.
        return {
            "head_count": 0,
            "tail_count": 0,
            "head": [],
            "tail": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def row_element_count(shape: tuple[int, ...]) -> int:
    if len(shape) <= 1:
        return 1
    total = 1
    for size in shape[1:]:
        total *= int(size)
        if total > 100_000:
            break
    return total


def sampled_rows(dataset: h5py.Dataset, sample_size: int) -> np.ndarray | None:
    if sample_size <= 0:
        return None
    if dataset.shape == ():
        return np.asarray(dataset[()])
    if not dataset.shape:
        return None
    n_rows = int(dataset.shape[0])
    if n_rows == 0:
        return None
    per_row = row_element_count(tuple(int(v) for v in dataset.shape))
    if per_row <= 0 or per_row > sample_size:
        return None
    row_count = max(1, min(n_rows, sample_size // per_row))
    indices = np.unique(np.linspace(0, n_rows - 1, row_count, dtype=np.int64))
    pieces = []
    for idx in indices:
        pieces.append(safe_dataset_slice(dataset, int(idx), int(idx) + 1))
    return np.asarray(pieces)


def numeric_stats(dataset: h5py.Dataset, sample_size: int) -> dict[str, Any]:
    if not np.issubdtype(dataset.dtype, np.number):
        return {"kind": "non_numeric", "sampled": False}
    try:
        sample = sampled_rows(dataset, sample_size)
        if sample is None:
            return {"kind": "numeric", "sampled": False, "reason": "row too wide or empty"}
        values = np.asarray(sample, dtype=np.float64).reshape(-1)
        total = int(values.size)
        finite = values[np.isfinite(values)]
        out: dict[str, Any] = {
            "kind": "numeric",
            "sampled": True,
            "sample_elements": total,
            "finite_count": int(finite.size),
            "nan_count": int(np.isnan(values).sum()),
            "inf_count": int(np.isinf(values).sum()),
        }
        if finite.size:
            out.update(
                {
                    "min": float(np.min(finite)),
                    "max": float(np.max(finite)),
                    "mean": float(np.mean(finite)),
                    "median": float(np.median(finite)),
                    "std": float(np.std(finite)),
                }
            )
        return out
    except Exception as exc:  # pragma: no cover - depends on unusual HDF5 storage.
        return {"kind": "numeric", "sampled": False, "error": f"{type(exc).__name__}: {exc}"}


def dataset_summary(path: str, dataset: h5py.Dataset, max_preview: int, sample_size: int) -> dict[str, Any]:
    attrs = attrs_summary(dataset.attrs)
    return {
        "path": path,
        "name": dataset.name.split("/")[-1],
        "kind": "dataset",
        "shape": list(dataset.shape),
        "ndim": int(len(dataset.shape)),
        "size": int(dataset.size),
        "dtype": dtype_text(dataset.dtype),
        "attrs": attrs,
        "metadata_attrs": metadata_attrs(attrs),
        "storage": dataset_storage_info(dataset),
        "preview": preview_dataset(dataset, max_preview),
        "sample_stats": numeric_stats(dataset, sample_size),
    }


def group_summary(path: str, group: h5py.Group) -> dict[str, Any]:
    return {
        "path": path,
        "name": group.name.split("/")[-1] or "/",
        "kind": "group",
        "attrs": attrs_summary(group.attrs),
        "children": sorted(str(name) for name in group.keys()),
    }


def walk_h5(h5: h5py.File, max_preview: int, sample_size: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: list[dict[str, Any]] = [group_summary("/", h5)]
    datasets: list[dict[str, Any]] = []

    def visit(name: str, obj: h5py.Group | h5py.Dataset) -> None:
        path = "/" + name if not name.startswith("/") else name
        if isinstance(obj, h5py.Dataset):
            datasets.append(dataset_summary(path, obj, max_preview, sample_size))
        elif isinstance(obj, h5py.Group):
            groups.append(group_summary(path, obj))

    h5.visititems(visit)
    groups.sort(key=lambda item: item["path"])
    datasets.sort(key=lambda item: item["path"])
    return groups, datasets


def lower_blob(item: dict[str, Any]) -> str:
    attrs = item.get("attrs", {})
    attr_text = " ".join(f"{key} {entry.get('value', '')}" for key, entry in attrs.items())
    return f"{item.get('path', '')} {item.get('name', '')} {attr_text}".lower()


def confidence_candidate(item: dict[str, Any], evidence: list[str], score: int) -> dict[str, Any]:
    return {
        "path": item["path"],
        "shape": item["shape"],
        "dtype": item["dtype"],
        "confidence": "inferred",
        "score": score,
        "evidence": evidence,
    }


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def infer_candidates(datasets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "time": [],
        "magnetic_vector": [],
        "magnetic_scalar": [],
        "latitude": [],
        "longitude": [],
        "altitude": [],
        "orbit": [],
        "quality_flag": [],
    }
    for item in datasets:
        text = lower_blob(item)
        shape = item["shape"]
        ndim = item["ndim"]
        score = 0

        if has_any(text, (r"(^|[/_\-\s])(utc|time|epoch|timestamp)([/_\-\s]|$)", r"timestamp")) and ndim <= 2:
            evidence = ["name_or_attr_mentions_time"]
            if has_any(text, (r"seconds since", r"yyyy", r"utc")):
                evidence.append("time_units_or_description_present")
            buckets["time"].append(confidence_candidate(item, evidence, 80 + (20 if evidence[-1] != evidence[0] else 0)))

        if ndim >= 2 and shape and int(shape[-1]) == 3 and has_any(text, (r"\bb[_-]?", r"mag", r"magnetic", r"nec", r"gsm", r"gse")):
            evidence = ["last_dimension_is_3", "name_or_attr_mentions_magnetic_or_frame"]
            if has_any(text, (r"\bnt\b", r"nano.?tesla")):
                evidence.append("unit_mentions_nt")
            buckets["magnetic_vector"].append(confidence_candidate(item, evidence, 90 + (10 if "unit_mentions_nt" in evidence else 0)))

        if ndim <= 2 and has_any(text, (r"\bf\b", r"\bbtotal\b", r"\bb[_-]?scalar\b", r"magnetic field scalar", r"\bbabs\b")):
            evidence = ["name_or_attr_mentions_scalar_magnetic_field"]
            if has_any(text, (r"\bnt\b", r"nano.?tesla")):
                evidence.append("unit_mentions_nt")
            buckets["magnetic_scalar"].append(confidence_candidate(item, evidence, 70 + (10 if "unit_mentions_nt" in evidence else 0)))

        if ndim <= 2 and has_any(text, (r"\blat\b", r"latitude")):
            buckets["latitude"].append(confidence_candidate(item, ["name_or_attr_mentions_latitude"], 90))

        if ndim <= 2 and has_any(text, (r"\blon\b", r"longitude")):
            buckets["longitude"].append(confidence_candidate(item, ["name_or_attr_mentions_longitude"], 90))

        if ndim <= 2 and has_any(text, (r"\balt\b", r"altitude", r"height")):
            buckets["altitude"].append(confidence_candidate(item, ["name_or_attr_mentions_altitude"], 90))

        if has_any(text, (r"orbit", r"position", r"\bpos\b", r"geo", r"radius")):
            evidence = ["name_or_attr_mentions_orbit_or_position"]
            if ndim >= 2 and shape and int(shape[-1]) in (3, 6):
                evidence.append("last_dimension_is_position_like")
            buckets["orbit"].append(confidence_candidate(item, evidence, 60 + (20 if len(evidence) > 1 else 0)))

        if ndim <= 2 and has_any(text, (r"quality", r"(^|[/_\-\s])flag([/_\-\s]|$)", r"status", r"\bqa\b", r"\bqc\b")):
            score = 80
            if "uint" in item["dtype"].lower() or "int" in item["dtype"].lower():
                score += 10
            if "quality" in text:
                score += 10
            buckets["quality_flag"].append(confidence_candidate(item, ["name_or_attr_mentions_quality_flag_or_status"], score))

        if score:
            continue

    for key in buckets:
        buckets[key].sort(key=lambda item: (-item["score"], item["path"]))
    return buckets


def output_dir_for_file(path: Path, output_root: Path, input_root: Path | None = None) -> Path:
    resolved = path.resolve()
    if input_root is not None:
        try:
            rel = resolved.relative_to(input_root.resolve())
        except ValueError:
            rel = Path(resolved.name)
    else:
        rel = Path(resolved.name)
    if rel.suffix.lower() in H5_SUFFIXES:
        rel = rel.with_suffix("")
    return output_root / rel


def tree_text(file_summary: dict[str, Any], groups: list[dict[str, Any]], datasets: list[dict[str, Any]]) -> str:
    lines = [
        f"file: {file_summary['path']}",
        f"relative_path: {file_summary.get('relative_path', '')}",
        f"size_bytes: {file_summary['size_bytes']}",
        "",
        "groups:",
    ]
    for group in groups:
        lines.append(f"- {group['path']} children={len(group['children'])} attrs={len(group['attrs'])}")
    lines.append("")
    lines.append("datasets:")
    for dataset in datasets:
        lines.append(
            f"- {dataset['path']} shape={dataset['shape']} dtype={dataset['dtype']} "
            f"attrs={len(dataset['attrs'])} compression={dataset['storage']['compression']}"
        )
    return "\n".join(lines) + "\n"


def report_text(summary: dict[str, Any]) -> str:
    file_info = summary["file"]
    lines = [
        f"# H5 Inspection Report: {file_info['name']}",
        "",
        "## File",
        "",
        f"- path: `{file_info['path']}`",
        f"- relative_path: `{file_info.get('relative_path', '')}`",
        f"- size_bytes: `{file_info['size_bytes']}`",
        f"- inspected_utc: `{summary['inspected_utc']}`",
        "",
        "## Dataset Summary",
        "",
        f"- groups: `{len(summary['groups'])}`",
        f"- datasets: `{len(summary['datasets'])}`",
        "",
        "## Candidate Fields",
        "",
    ]
    for key, candidates in summary["candidates"].items():
        lines.append(f"### {key}")
        if not candidates:
            lines.append("")
            lines.append("- no candidate found")
            lines.append("")
            continue
        lines.append("")
        for candidate in candidates[:10]:
            evidence = ", ".join(candidate["evidence"])
            lines.append(
                f"- `{candidate['path']}` confidence=`{candidate['confidence']}` "
                f"score=`{candidate['score']}` evidence={evidence}"
            )
        lines.append("")
    lines.extend(
        [
            "## Datasets",
            "",
            "| Path | Shape | Dtype | Metadata attrs | Sample stats |",
            "|---|---:|---|---|---|",
        ]
    )
    for dataset in summary["datasets"]:
        meta_keys = ", ".join(dataset["metadata_attrs"].keys()) or ""
        stats = dataset.get("sample_stats", {})
        stat_text = ""
        if stats.get("sampled"):
            stat_text = f"finite={stats.get('finite_count')} min={stats.get('min', '')} max={stats.get('max', '')}"
        else:
            stat_text = stats.get("kind", "not_sampled")
        lines.append(f"| `{dataset['path']}` | `{dataset['shape']}` | `{dataset['dtype']}` | {meta_keys} | {stat_text} |")
    lines.append("")
    lines.append("All semantic candidate classifications in this report are inferred unless explicitly sourced from H5 attrs.")
    return "\n".join(lines) + "\n"


def file_summary(path: Path, input_root: Path | None) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        rel = str(resolved.relative_to(input_root.resolve())) if input_root else resolved.name
    except ValueError:
        rel = resolved.name
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "relative_path": rel,
        "name": resolved.name,
        "size_bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
        "sha256_first_1m": sha256_prefix(resolved),
    }


def sha256_prefix(path: Path, max_bytes: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    remaining = max_bytes
    with path.open("rb") as f:
        while remaining > 0:
            block = f.read(min(1024 * 1024, remaining))
            if not block:
                break
            h.update(block)
            remaining -= len(block)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def inspect_h5_file(
    path: Path | str,
    output_root: Path | str,
    *,
    input_root: Path | str | None = None,
    max_preview: int = 8,
    sample_size: int = 2048,
) -> dict[str, Any]:
    h5_path = Path(path)
    out_root = Path(output_root)
    root = Path(input_root) if input_root is not None else None
    out_dir = output_dir_for_file(h5_path, out_root, root)
    out_dir.mkdir(parents=True, exist_ok=True)

    info = file_summary(h5_path, root)
    with h5py.File(h5_path, "r") as h5:
        groups, datasets = walk_h5(h5, max_preview=max_preview, sample_size=sample_size)
        summary = {
            "inspected_utc": utc_now(),
            "file": info,
            "root_attrs": attrs_summary(h5.attrs),
            "groups": groups,
            "datasets": datasets,
            "candidates": infer_candidates(datasets),
        }

    tree_payload = {
        "file": info,
        "groups": groups,
        "datasets": [
            {
                "path": item["path"],
                "shape": item["shape"],
                "dtype": item["dtype"],
                "attrs": item["attrs"],
                "storage": item["storage"],
            }
            for item in datasets
        ],
    }
    write_json(out_dir / "h5_tree.json", tree_payload)
    (out_dir / "h5_tree.txt").write_text(tree_text(info, groups, datasets), encoding="utf-8")
    write_json(out_dir / "summary.json", summary)
    (out_dir / "report.md").write_text(report_text(summary), encoding="utf-8")
    return summary


def write_error_report(
    path: Path,
    output_root: Path,
    *,
    input_root: Path | None,
    error: BaseException,
) -> dict[str, Any]:
    out_dir = output_dir_for_file(path, output_root, input_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "inspected_utc": utc_now(),
        "file": file_summary(path, input_root),
        "error": {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
    }
    write_json(out_dir / "summary.json", payload)
    (out_dir / "report.md").write_text(
        f"# H5 Inspection Failed: {path.name}\n\n"
        f"- error_type: `{type(error).__name__}`\n"
        f"- message: `{str(error)}`\n",
        encoding="utf-8",
    )
    write_json(out_dir / "h5_tree.json", payload)
    (out_dir / "h5_tree.txt").write_text(f"failed: {type(error).__name__}: {error}\n", encoding="utf-8")
    return payload


def discover_h5_files(input_root: Path) -> list[Path]:
    files = [
        path
        for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in H5_SUFFIXES and not path.name.startswith("._")
    ]
    return sorted(files)


def inspect_h5_tree(
    input_root: Path | str,
    output_root: Path | str,
    *,
    max_preview: int = 8,
    sample_size: int = 2048,
    limit: int | None = None,
) -> dict[str, Any]:
    in_root = Path(input_root)
    out_root = Path(output_root)
    out_root.mkdir(parents=True, exist_ok=True)
    files = discover_h5_files(in_root)
    if limit is not None:
        files = files[:limit]

    results: list[dict[str, Any]] = []
    for path in files:
        try:
            summary = inspect_h5_file(path, out_root, input_root=in_root, max_preview=max_preview, sample_size=sample_size)
            results.append({"file": summary["file"], "status": "ok"})
        except Exception as exc:
            payload = write_error_report(path, out_root, input_root=in_root, error=exc)
            results.append({"file": payload["file"], "status": "error", "error": payload["error"]})

    index = {
        "inspected_utc": utc_now(),
        "input_root": str(in_root.resolve()),
        "output_root": str(out_root.resolve()),
        "file_count": len(files),
        "ok_count": sum(1 for item in results if item["status"] == "ok"),
        "error_count": sum(1 for item in results if item["status"] == "error"),
        "results": results,
    }
    write_json(out_root / "inspection_index.json", index)
    return index


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect CSES HPM H5/HDF5 files without full-array reads.")
    parser.add_argument("--input-root", default="/Users/foursoils/Downloads/HPM", help="Root containing CSES HPM H5 files.")
    parser.add_argument(
        "--output-root",
        default="/Volumes/Elements/satellite_data_web/outputs/cses_hpm_inspection",
        help="Directory for inspection reports.",
    )
    parser.add_argument("--max-preview", type=int, default=8, help="Head/tail rows to preview per dataset.")
    parser.add_argument("--sample-size", type=int, default=2048, help="Maximum sample elements per dataset for stats.")
    parser.add_argument("--limit", type=int, default=None, help="Optional file limit for debugging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    index = inspect_h5_tree(
        Path(args.input_root),
        Path(args.output_root),
        max_preview=args.max_preview,
        sample_size=args.sample_size,
        limit=args.limit,
    )
    print(json.dumps({k: index[k] for k in ("input_root", "output_root", "file_count", "ok_count", "error_count")}, ensure_ascii=False))
    return 0 if index["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
