from __future__ import annotations

import base64
import csv
import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from app.core.artifacts import ArtifactRegistry
from app.core.config import AppConfig
from app.datasources.cses_hpm import format_utc_millis, parse_cses_utc_time_millis, parse_time_bound_millis
from app.services.table_export import request_digest, sanitize_id


QUALITY_FIELDS = ("/FLAG_MT", "/FLAG_SHW", "/FLAG_TBB", "/FLAG_N3")
TIME_FIELD = "/UTC_TIME"
VECTOR_FIELD = "/B_FGM"
SCALAR_FIELD = "/A211"
LAT_FIELD = "/GEO_LAT"
LON_FIELD = "/GEO_LON"
ALT_FIELD = "/ALTITUDE"
DEFAULT_GAP_FACTOR = 5.0
PLOT_GROUP_GAP_MS = 60 * 60 * 1000
ORBIT_LINK_GAP_MS = 30 * 60 * 1000
EARTH_RADIUS_KM = 6371.2
SEGMENT_COLORS = ["#d94b3d", "#f08a2f", "#b81f2d", "#e85b8a", "#ffb26b", "#a0172f", "#f06f5f"]
SEGMENT_COLOR_FAMILIES = [
    ["#d94b3d", "#e05f4f", "#e77768", "#f09184"],
    ["#f08a2f", "#f39a45", "#f5aa5c", "#f7bb74"],
    ["#b81f2d", "#ca3341", "#dc4a58", "#ea6370"],
    ["#d83b73", "#e05286", "#e86a98", "#f083aa"],
]
BEIJING_TZ = timezone(timedelta(hours=8))


@lru_cache(maxsize=1)
def earth_texture_data_url() -> str:
    texture_path = Path(__file__).resolve().parents[1] / "assets" / "earth_day_1024.jpg"
    try:
        texture_bytes = texture_path.read_bytes()
    except OSError:
        return ""
    encoded = base64.b64encode(texture_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


@dataclass(frozen=True)
class UploadFileRecord:
    upload_id: str
    filename: str
    stored_path: Path
    sha256: str
    size_bytes: int
    duplicate_of: str | None
    status: str
    hpm_product: str
    sample_count: int
    time_parseable: bool
    start_ms: int | None
    end_ms: int | None
    has_vector_magnetic: bool
    has_scalar_magnetic: bool
    quality_flag_summary: dict[str, Any]
    warnings: list[str]
    errors: list[str]


class CsesHpmUploadService:
    def __init__(self, config: AppConfig, artifacts: ArtifactRegistry) -> None:
        self.config = config
        self.artifacts = artifacts

    @property
    def upload_root(self) -> Path:
        return self.config.outputs_root / "uploads" / "cses_hpm"

    @property
    def plot_root(self) -> Path:
        return self.config.outputs_root / "generated_plots" / "cses_hpm"

    @property
    def export_root(self) -> Path:
        return self.config.outputs_root / "exports" / "cses_hpm"

    @property
    def log_root(self) -> Path:
        return self.config.outputs_root / "logs" / "cses_hpm"

    def create_session(self, uploads: list[tuple[str, bytes]]) -> dict[str, Any]:
        if not uploads:
            raise ValueError("请先上传 H5 文件")
        session_id = uuid.uuid4().hex[:16]
        session_dir = self.upload_root / session_id
        raw_dir = session_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        records: list[UploadFileRecord] = []
        seen_hashes: dict[str, str] = {}
        run_log = [f"创建上传会话 {session_id}", f"接收 {len(uploads)} 个 H5 文件"]
        for index, (filename, content) in enumerate(uploads):
            safe_name = sanitize_id(Path(filename).name) or f"upload_{index}"
            if not safe_name.lower().endswith("_h5") and not safe_name.lower().endswith(".h5"):
                safe_name = f"{safe_name}.h5"
            stored_path = raw_dir / f"{index + 1:03d}_{safe_name.replace('_h5', '.h5')}"
            stored_path.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            duplicate_of = seen_hashes.get(digest)
            if duplicate_of is None:
                seen_hashes[digest] = Path(filename).name
            record = self._inspect_uploaded_file(
                upload_id=f"file_{index + 1:03d}",
                filename=Path(filename).name,
                stored_path=stored_path,
                sha256=digest,
                duplicate_of=duplicate_of,
            )
            records.append(record)
            if record.status == "ok":
                run_log.append(f"{record.filename}: 解析成功，{record.hpm_product}，样本 {record.sample_count}")
            else:
                run_log.append(f"{record.filename}: 解析失败，{'; '.join(record.errors)}")

        session = self._build_session_payload(session_id, session_dir, records, run_log)
        self._write_session(session_dir, session)
        return session

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._load_session(session_id)

    def plot(self, session_id: str, request: dict[str, Any]) -> dict[str, Any]:
        session = self._load_session(session_id)
        plot_type = str(request.get("plot_type") or "magnetic")
        crop = request.get("crop_range") or {}
        if plot_type == "spectrogram":
            return {
                "upload_session_id": session_id,
                "plot_type": plot_type,
                "status": "disabled",
                "reason": "频谱图暂未启用：当前 HPM 数据的时频分析规则尚未确认",
            }
        if plot_type == "magnetic":
            return self._plot_magnetic(session, crop)
        if plot_type == "orbit":
            return self._plot_orbit(session, crop)
        return {
            "upload_session_id": session_id,
            "plot_type": plot_type,
            "status": "unsupported",
            "reason": f"不支持的图像类型: {plot_type}",
        }

    def export(self, session_id: str, request: dict[str, Any]) -> dict[str, Any]:
        session = self._load_session(session_id)
        export_format = str(request.get("format") or "csv").lower()
        if export_format == "cdf":
            return {
                "upload_session_id": session_id,
                "format": export_format,
                "status": "unsupported",
                "reason": "CDF 导出暂未启用：需要稳定 CDF writer 和 metadata 映射确认",
            }
        if export_format not in {"csv", "dat", "h5"}:
            raise ValueError(f"unsupported export format: {export_format}")
        crop = request.get("crop_range") or {}
        rows, selected_segments = self._merged_rows_for_session(session, crop)
        if not rows:
            raise ValueError("选择范围内没有可导出的数据")
        digest = request_digest({"session_id": session_id, "format": export_format, "crop": crop, "count": len(rows)})
        out_dir = self.export_root / session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"cses_hpm_export_{digest}.{export_format}"
        if export_format in {"csv", "dat"}:
            delimiter = "," if export_format == "csv" else "\t"
            with out_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter=delimiter)
                writer.writeheader()
                writer.writerows(rows)
        else:
            with h5py.File(out_path, "w") as h5:
                for key in rows[0]:
                    values = [row[key] for row in rows]
                    try:
                        h5.create_dataset(key, data=np.asarray(values, dtype=float))
                    except ValueError:
                        h5.create_dataset(key, data=np.asarray(values, dtype="S"))
        manifest = {
            "upload_session_id": session_id,
            "uploaded_files": [record["filename"] for record in session["per_file_records"]],
            "crop_range": crop,
            "sort_and_dedupe": session["dedupe"],
            "segments": selected_segments,
            "format": export_format,
            "output_path": str(out_path),
            "row_count": len(rows),
            "variables": list(rows[0].keys()),
        }
        manifest_path = out_path.with_name(f"{out_path.stem}_manifest.json")
        manifest_path.write_text(json.dumps(json_safe(manifest), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        artifact = self.artifacts.register(
            f"cses_hpm_upload:export:{session_id}:{digest}",
            out_path,
            media_type={"csv": "text/csv", "dat": "text/plain", "h5": "application/x-hdf5"}[export_format],
            label=f"CSES HPM upload export {export_format.upper()}",
        )
        manifest_artifact = self.artifacts.register(
            f"cses_hpm_upload:export_manifest:{session_id}:{digest}",
            manifest_path,
            media_type="application/json",
            label="CSES HPM upload export manifest",
        )
        return {
            "upload_session_id": session_id,
            "format": export_format,
            "status": "ok",
            "row_count": len(rows),
            "segments": selected_segments,
            "artifact": artifact,
            "manifest": manifest,
            "manifest_artifact": manifest_artifact,
        }

    def statistics(self, session_id: str, request: dict[str, Any]) -> dict[str, Any]:
        session = self._load_session(session_id)
        crop = request.get("crop_range") or {}
        from app.services.cses_hpm_statistics import compute_cses_hpm_feature_statistics

        result = compute_cses_hpm_feature_statistics(
            session=session,
            config=self.config,
            artifacts=self.artifacts,
            crop=crop,
        )
        processing = result["processing_summary"]
        product_status = result["product_type_status"]
        output_path = result.get("artifacts", {}).get("statistics_json", {}).get("path", "")
        run_log_entry = (
            "统计分析完成: "
            f"session {session_id}，"
            f"裁剪={'是' if processing.get('crop_applied') else '否'}，"
            f"最终样本 {processing.get('final_sample_count')}，"
            f"segments {processing.get('segment_count')}，"
            f"重复时间样本去除 {processing.get('duplicate_time_removed_count')}，"
            f"产品状态 {product_status.get('status')}，"
            f"输出 {output_path}"
        )
        session.setdefault("run_log", []).append(run_log_entry)
        self._write_session(Path(session["session_dir"]), session)
        return {**result, "run_log_entry": run_log_entry}

    def _inspect_uploaded_file(
        self,
        *,
        upload_id: str,
        filename: str,
        stored_path: Path,
        sha256: str,
        duplicate_of: str | None,
    ) -> UploadFileRecord:
        errors: list[str] = []
        warnings: list[str] = []
        hpm_product = product_from_filename(filename)
        sample_count = 0
        time_parseable = False
        start_ms: int | None = None
        end_ms: int | None = None
        has_vector = False
        has_scalar = False
        quality: dict[str, Any] = {}
        try:
            with h5py.File(stored_path, "r") as h5:
                has_vector = has_dataset(h5, VECTOR_FIELD) and np.asarray(h5[VECTOR_FIELD.strip("/")].shape).size > 0
                has_scalar = has_dataset(h5, SCALAR_FIELD)
                if hpm_product == "unknown":
                    if has_vector:
                        hpm_product = "HPM_5"
                    elif has_scalar:
                        hpm_product = "HPM_6"
                if not has_dataset(h5, TIME_FIELD):
                    errors.append("missing /UTC_TIME")
                else:
                    raw_time = np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1)
                    sample_count = int(raw_time.size)
                    parsed = parse_cses_utc_time_millis(raw_time)
                    if parsed.size:
                        time_parseable = True
                        start_ms = int(np.nanmin(parsed))
                        end_ms = int(np.nanmax(parsed))
                    else:
                        errors.append("/UTC_TIME empty")
                for field in QUALITY_FIELDS:
                    if has_dataset(h5, field):
                        values = np.asarray(h5[field.strip("/")][:]).reshape(-1)
                        quality[field] = {"distribution": value_distribution(values), "sample_count": int(values.size)}
                if hpm_product == "HPM_5" and not has_vector:
                    warnings.append("HPM_5 文件缺少 /B_FGM")
                if hpm_product == "HPM_6" and not has_scalar:
                    warnings.append("HPM_6 文件缺少 /A211")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        return UploadFileRecord(
            upload_id=upload_id,
            filename=filename,
            stored_path=stored_path,
            sha256=sha256,
            size_bytes=stored_path.stat().st_size,
            duplicate_of=duplicate_of,
            status="ok" if not errors else "error",
            hpm_product=hpm_product,
            sample_count=sample_count,
            time_parseable=time_parseable,
            start_ms=start_ms,
            end_ms=end_ms,
            has_vector_magnetic=has_vector,
            has_scalar_magnetic=has_scalar,
            quality_flag_summary=quality,
            warnings=warnings,
            errors=errors,
        )

    def _build_session_payload(
        self,
        session_id: str,
        session_dir: Path,
        records: list[UploadFileRecord],
        run_log: list[str],
    ) -> dict[str, Any]:
        ok_records = [record for record in records if record.status == "ok" and record.time_parseable]
        sorted_records = sorted(ok_records, key=lambda item: (item.start_ms if item.start_ms is not None else math.inf, item.filename))
        rows = self._collect_time_rows(sorted_records)
        deduped_rows, duplicate_sample_count = dedupe_rows_by_time(rows)
        segments = build_segments(deduped_rows)
        plot_groups = build_plot_groups(segments)
        duplicate_file_count = sum(1 for record in records if record.duplicate_of)
        run_log.append("时间排序完成")
        if duplicate_file_count:
            run_log.append(f"重复文件去除: {duplicate_file_count} 个")
        if duplicate_sample_count:
            run_log.append(f"重复时间样本去除: {duplicate_sample_count} 个")
        run_log.append(f"分段数量: {len(segments)}")
        run_log.append(f"绘图分组数量: {len(plot_groups)}")
        products = sorted({record.hpm_product for record in ok_records})
        if len(products) > 1:
            run_log.append(f"warning: 数据类型混合 {', '.join(products)}")
        session = {
            "upload_session_id": session_id,
            "mode": "single" if len(records) == 1 else "batch",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session_dir": str(session_dir),
            "per_file_records": [record_to_payload(record) for record in records],
            "sorted_files": [
                {
                    "upload_id": record.upload_id,
                    "filename": record.filename,
                    "hpm_product": record.hpm_product,
                    "start": format_utc_millis(record.start_ms) if record.start_ms is not None else None,
                    "end": format_utc_millis(record.end_ms) if record.end_ms is not None else None,
                    "display_start": format_beijing_millis(record.start_ms) if record.start_ms is not None else None,
                    "display_end": format_beijing_millis(record.end_ms) if record.end_ms is not None else None,
                }
                for record in sorted_records
            ],
            "merged_time_range": {
                "start": format_utc_millis(deduped_rows[0]["time_ms"]) if deduped_rows else None,
                "end": format_utc_millis(deduped_rows[-1]["time_ms"]) if deduped_rows else None,
            },
            "display_time_zone": "Asia/Shanghai",
            "display_time_range": {
                "start": format_beijing_millis(deduped_rows[0]["time_ms"]) if deduped_rows else None,
                "end": format_beijing_millis(deduped_rows[-1]["time_ms"]) if deduped_rows else None,
            },
            "crop_options": build_crop_options(deduped_rows),
            "segments": segments,
            "plot_groups": plot_groups,
            "sample_count": len(deduped_rows),
            "raw_sample_count": len(rows),
            "dedupe": {
                "duplicate_file_count": duplicate_file_count,
                "duplicate_sample_count": duplicate_sample_count,
            },
            "data_products": products,
            "time_parseable": bool(deduped_rows),
            "crop_enabled": bool(deduped_rows),
            "quality_flag_summary": merge_quality_summaries(records),
            "run_log": run_log,
        }
        return session

    def _collect_time_rows(self, records: list[UploadFileRecord]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in records:
            if record.duplicate_of:
                with h5py.File(record.stored_path, "r") as h5:
                    raw_time = np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1)
                    for value in parse_cses_utc_time_millis(raw_time):
                        rows.append({"time_ms": int(value), "upload_id": record.upload_id, "filename": record.filename})
                continue
            with h5py.File(record.stored_path, "r") as h5:
                raw_time = np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1)
                for value in parse_cses_utc_time_millis(raw_time):
                    rows.append({"time_ms": int(value), "upload_id": record.upload_id, "filename": record.filename})
        rows.sort(key=lambda item: item["time_ms"])
        return rows

    def _merged_rows_for_session(self, session: dict[str, Any], crop: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records = [record for record in session["per_file_records"] if record.get("status") == "ok" and not record.get("duplicate_of")]
        products = sorted({record["hpm_product"] for record in records})
        if len(products) > 1:
            raise ValueError("混合 HPM_5/HPM_6 暂不支持统一导出")
        crop_start, crop_end = crop_bounds(crop)
        rows: list[dict[str, Any]] = []
        for record in records:
            path = Path(record["stored_path"])
            product = record["hpm_product"]
            with h5py.File(path, "r") as h5:
                time_ms = parse_cses_utc_time_millis(np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1))
                mask = crop_mask(time_ms, crop_start, crop_end)
                if not np.any(mask):
                    continue
                lat = read_optional_1d(h5, LAT_FIELD)
                lon = read_optional_1d(h5, LON_FIELD)
                alt = read_optional_1d(h5, ALT_FIELD)
                if product == "HPM_6":
                    scalar = np.asarray(h5[SCALAR_FIELD.strip("/")][:], dtype=float).reshape(-1)
                    for idx in np.where(mask)[0]:
                        rows.append(
                            {
                                "time_utc": format_utc_millis(int(time_ms[idx])),
                                "source_file": record["filename"],
                                "A211": float(scalar[idx]),
                                "lat": optional_value(lat, idx),
                                "lon": optional_value(lon, idx),
                                "alt": optional_value(alt, idx),
                            }
                        )
                else:
                    b = np.asarray(h5[VECTOR_FIELD.strip("/")][:], dtype=float)
                    for idx in np.where(mask)[0]:
                        rows.append(
                            {
                                "time_utc": format_utc_millis(int(time_ms[idx])),
                                "source_file": record["filename"],
                                "B_FGM_0": float(b[idx, 0]),
                                "B_FGM_1": float(b[idx, 1]),
                                "B_FGM_2": float(b[idx, 2]),
                                "B_abs": float(np.linalg.norm(b[idx, :3])),
                                "lat": optional_value(lat, idx),
                                "lon": optional_value(lon, idx),
                                "alt": optional_value(alt, idx),
                            }
                        )
        rows.sort(key=lambda item: item["time_utc"])
        row_time = [parse_time_bound_millis(row["time_utc"], field="row") for row in rows]
        selected_segments = build_segments([{"time_ms": value} for value in row_time])
        return rows, selected_segments

    def _plot_magnetic(self, session: dict[str, Any], crop: dict[str, Any]) -> dict[str, Any]:
        records = [record for record in session["per_file_records"] if record.get("status") == "ok" and not record.get("duplicate_of")]
        products = sorted({record["hpm_product"] for record in records})
        if len(products) > 1:
            return {
                "upload_session_id": session["upload_session_id"],
                "plot_type": "magnetic",
                "status": "unavailable",
                "reason": "混合 HPM_5/HPM_6 批量暂不支持统一磁场绘图",
            }
        if not products:
            return unavailable_plot(session, "magnetic", "没有可解析的 HPM 文件")
        rows, selected_segments = self._magnetic_segment_arrays(records, crop)
        if not rows:
            return unavailable_plot(session, "magnetic", "选择范围内没有数据")
        plot_groups = build_plot_groups(selected_segments)
        digest = request_digest({"session": session["upload_session_id"], "plot": "magnetic", "crop": crop, "groups": plot_groups})
        out_path = self.plot_root / session["upload_session_id"] / f"magnetic_{digest}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        draw_magnetic_segments(out_path, rows, products[0])
        artifact = self.artifacts.register(
            f"cses_hpm_upload:plot:{session['upload_session_id']}:magnetic:{digest}",
            out_path,
            media_type="image/png",
            label="CSES HPM magnetic diagnostic",
        )
        return {
            "upload_session_id": session["upload_session_id"],
            "plot_type": "magnetic",
            "status": "ok",
            "segments": selected_segments,
            "plot_groups": plot_groups,
            "artifact": artifact,
        }

    def _plot_orbit(self, session: dict[str, Any], crop: dict[str, Any]) -> dict[str, Any]:
        rows, selected_segments = self._orbit_segment_arrays(session, crop)
        if not rows:
            return unavailable_plot(session, "orbit", "选择范围内没有轨道数据")
        plot_groups = build_plot_groups(selected_segments)
        digest = request_digest({"session": session["upload_session_id"], "plot": "orbit", "crop": crop, "groups": plot_groups})
        out_path = self.plot_root / session["upload_session_id"] / f"orbit_{digest}.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_interactive_orbit_html(out_path, rows, selected_segments, plot_groups)
        artifact = self.artifacts.register(
            f"cses_hpm_upload:plot:{session['upload_session_id']}:orbit:{digest}",
            out_path,
            media_type="text/html",
            label="CSES HPM interactive orbit",
        )
        return {
            "upload_session_id": session["upload_session_id"],
            "plot_type": "orbit",
            "status": "ok",
            "segments": selected_segments,
            "plot_groups": plot_groups,
            "artifact": artifact,
        }

    def _magnetic_segment_arrays(self, records: list[dict[str, Any]], crop: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        product = records[0]["hpm_product"] if records else "unknown"
        crop_start, crop_end = crop_bounds(crop)
        points: list[dict[str, Any]] = []
        for record in records:
            path = Path(record["stored_path"])
            with h5py.File(path, "r") as h5:
                time_ms = parse_cses_utc_time_millis(np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1))
                mask = crop_mask(time_ms, crop_start, crop_end)
                if not np.any(mask):
                    continue
                if product == "HPM_6":
                    values = np.asarray(h5[SCALAR_FIELD.strip("/")][:], dtype=float).reshape(-1)
                    for idx in np.where(mask)[0]:
                        points.append({"time_ms": int(time_ms[idx]), "values": [float(values[idx])], "filename": record["filename"]})
                else:
                    values = np.asarray(h5[VECTOR_FIELD.strip("/")][:], dtype=float)
                    for idx in np.where(mask)[0]:
                        vector = values[idx, :3].astype(float)
                        points.append({"time_ms": int(time_ms[idx]), "values": vector.tolist(), "filename": record["filename"]})
        points.sort(key=lambda item: item["time_ms"])
        deduped, _ = dedupe_rows_by_time(points)
        segments = build_segments(deduped)
        grouped_segments = rows_by_segments(deduped, segments)
        grouped_plots = rows_by_plot_groups(grouped_segments, build_plot_groups(segments))
        return grouped_plots, segments

    def _orbit_segment_arrays(self, session: dict[str, Any], crop: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        crop_start, crop_end = crop_bounds(crop)
        points: list[dict[str, Any]] = []
        records = [record for record in session["per_file_records"] if record.get("status") == "ok" and not record.get("duplicate_of")]
        for record in records:
            path = Path(record["stored_path"])
            with h5py.File(path, "r") as h5:
                if not all(has_dataset(h5, field) for field in (TIME_FIELD, LAT_FIELD, LON_FIELD, ALT_FIELD)):
                    continue
                time_ms = parse_cses_utc_time_millis(np.asarray(h5[TIME_FIELD.strip("/")][:]).reshape(-1))
                mask = crop_mask(time_ms, crop_start, crop_end)
                lat = read_optional_1d(h5, LAT_FIELD)
                lon = read_optional_1d(h5, LON_FIELD)
                alt = read_optional_1d(h5, ALT_FIELD)
                for idx in np.where(mask)[0]:
                    points.append(
                        {
                            "time_ms": int(time_ms[idx]),
                            "lat": float(lat[idx]),
                            "lon": float(lon[idx]),
                            "alt": float(alt[idx]),
                            "filename": record["filename"],
                        }
                    )
        points.sort(key=lambda item: item["time_ms"])
        deduped, _ = dedupe_rows_by_time(points)
        segments = build_segments(deduped)
        grouped = rows_by_segments(deduped, segments)
        return grouped, segments

    def _write_session(self, session_dir: Path, session: dict[str, Any]) -> None:
        session_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_root / f"{session['upload_session_id']}.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        session["log_path"] = str(log_path)
        (session_dir / "session.json").write_text(json.dumps(json_safe(session), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log_payload = {
            "upload_session_id": session["upload_session_id"],
            "created_at": session["created_at"],
            "mode": session["mode"],
            "merged_time_range": session["merged_time_range"],
            "display_time_zone": session.get("display_time_zone"),
            "display_time_range": session.get("display_time_range"),
            "segments": session["segments"],
            "plot_groups": session.get("plot_groups", []),
            "dedupe": session["dedupe"],
            "per_file_records": session["per_file_records"],
            "run_log": session["run_log"],
        }
        log_path.write_text(json.dumps(json_safe(log_payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _load_session(self, session_id: str) -> dict[str, Any]:
        path = self.upload_root / session_id / "session.json"
        if not path.exists():
            raise FileNotFoundError(session_id)
        return json.loads(path.read_text(encoding="utf-8"))


def has_dataset(h5: h5py.File, path: str) -> bool:
    return path.strip("/") in h5


def product_from_filename(filename: str) -> str:
    if "_HPM_5_" in filename:
        return "HPM_5"
    if "_HPM_6_" in filename:
        return "HPM_6"
    return "unknown"


def value_distribution(values: np.ndarray) -> dict[str, int]:
    flat = np.asarray(values).reshape(-1)
    distribution: dict[str, int] = {}
    for value in flat:
        key = str(json_safe(value))
        distribution[key] = distribution.get(key, 0) + 1
    return dict(sorted(distribution.items(), key=lambda item: item[0]))


def record_to_payload(record: UploadFileRecord) -> dict[str, Any]:
    return {
        "upload_id": record.upload_id,
        "filename": record.filename,
        "stored_path": str(record.stored_path),
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "duplicate_of": record.duplicate_of,
        "status": record.status,
        "hpm_product": record.hpm_product,
        "sample_count": record.sample_count,
        "time_parseable": record.time_parseable,
        "start_time": format_utc_millis(record.start_ms) if record.start_ms is not None else None,
        "end_time": format_utc_millis(record.end_ms) if record.end_ms is not None else None,
        "display_start_time": format_beijing_millis(record.start_ms) if record.start_ms is not None else None,
        "display_end_time": format_beijing_millis(record.end_ms) if record.end_ms is not None else None,
        "has_vector_magnetic": record.has_vector_magnetic,
        "has_scalar_magnetic": record.has_scalar_magnetic,
        "quality_flag_summary": record.quality_flag_summary,
        "warnings": record.warnings,
        "errors": record.errors,
    }


def merge_quality_summaries(records: list[UploadFileRecord]) -> dict[str, Any]:
    merged: dict[str, dict[str, int]] = {}
    for record in records:
        for field, summary in record.quality_flag_summary.items():
            merged.setdefault(field, {})
            for value, count in summary.get("distribution", {}).items():
                merged[field][value] = merged[field].get(value, 0) + int(count)
    return {field: {"distribution": dict(sorted(values.items()))} for field, values in sorted(merged.items())}


def dedupe_rows_by_time(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    duplicates = 0
    for row in sorted(rows, key=lambda item: item["time_ms"]):
        key = int(row["time_ms"])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        deduped.append(row)
    return deduped, duplicates


def build_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    times = np.asarray([row["time_ms"] for row in rows], dtype=np.int64)
    diffs = np.diff(times)
    positive = diffs[diffs > 0]
    cadence = int(np.median(positive)) if positive.size else 1000
    threshold = max(cadence * DEFAULT_GAP_FACTOR, cadence + 1)
    boundaries = [0]
    for index, diff in enumerate(diffs, start=1):
        if diff > threshold:
            boundaries.append(index)
    boundaries.append(len(rows))
    segments: list[dict[str, Any]] = []
    for index, (start_idx, end_idx) in enumerate(zip(boundaries[:-1], boundaries[1:], strict=True), start=1):
        start_ms = int(times[start_idx])
        end_ms = int(times[end_idx - 1])
        segments.append(
            {
                "segment_id": f"segment_{index}",
                "start": format_utc_millis(start_ms),
                "end": format_utc_millis(end_ms),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "sample_count": int(end_idx - start_idx),
            }
        )
    return segments


def build_plot_groups(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []
    groups: list[list[dict[str, Any]]] = [[segments[0]]]
    for segment in segments[1:]:
        previous = groups[-1][-1]
        gap_ms = int(segment["start_ms"]) - int(previous["end_ms"])
        same_beijing_day = beijing_day(int(segment["start_ms"])) == beijing_day(int(previous["start_ms"]))
        if same_beijing_day or gap_ms < PLOT_GROUP_GAP_MS:
            groups[-1].append(segment)
        else:
            groups.append([segment])
    payload: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        start_ms = int(group[0]["start_ms"])
        end_ms = int(group[-1]["end_ms"])
        payload.append(
            {
                "group_id": f"group_{index}",
                "start": format_utc_millis(start_ms),
                "end": format_utc_millis(end_ms),
                "display_start": format_beijing_millis(start_ms),
                "display_end": format_beijing_millis(end_ms),
                "segment_ids": [segment["segment_id"] for segment in group],
                "reason": "same_beijing_day_or_gap_lt_60min",
                "sample_count": sum(int(segment["sample_count"]) for segment in group),
            }
        )
    return payload


def beijing_day(value_ms: int) -> str:
    return datetime.fromtimestamp(value_ms / 1000, BEIJING_TZ).date().isoformat()


def format_beijing_millis(value_ms: int) -> str:
    return datetime.fromtimestamp(value_ms / 1000, BEIJING_TZ).strftime("%Y-%m-%d %H:%M")


def beijing_parts(value_ms: int) -> dict[str, int]:
    dt = datetime.fromtimestamp(value_ms / 1000, BEIJING_TZ)
    return {"year": dt.year, "month": dt.month, "day": dt.day, "hour": dt.hour, "minute": dt.minute}


def build_crop_options(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        empty = {"years": [], "months": [], "days": [], "hours": [], "minutes_by_hour": {}, "default": None}
        return {"start": empty, "end": empty}
    start_ms = int(rows[0]["time_ms"])
    end_ms = int(rows[-1]["time_ms"])
    available = available_beijing_minutes(start_ms, end_ms)
    option = {
        "years": sorted({item["year"] for item in available}),
        "months": sorted({item["month"] for item in available}),
        "days": sorted({item["day"] for item in available}),
        "hours": sorted({item["hour"] for item in available}),
        "minutes_by_hour": minutes_by_hour(available),
    }
    return {
        "start": {**option, "default": beijing_parts(start_ms)},
        "end": {**option, "default": beijing_parts(end_ms)},
    }


def available_beijing_minutes(start_ms: int, end_ms: int) -> list[dict[str, int]]:
    start_dt = datetime.fromtimestamp(start_ms / 1000, BEIJING_TZ).replace(second=0, microsecond=0)
    end_dt = datetime.fromtimestamp(end_ms / 1000, BEIJING_TZ).replace(second=0, microsecond=0)
    values: list[dict[str, int]] = []
    current = start_dt
    max_minutes = 370 * 24 * 60
    count = 0
    while current <= end_dt and count <= max_minutes:
        values.append({"year": current.year, "month": current.month, "day": current.day, "hour": current.hour, "minute": current.minute})
        current += timedelta(minutes=1)
        count += 1
    return values


def minutes_by_hour(values: list[dict[str, int]]) -> dict[str, list[int]]:
    grouped: dict[str, set[int]] = {}
    for item in values:
        key = f"{item['year']:04d}-{item['month']:02d}-{item['day']:02d}T{item['hour']:02d}"
        grouped.setdefault(key, set()).add(int(item["minute"]))
    return {key: sorted(minutes) for key, minutes in sorted(grouped.items())}


def rows_by_segments(rows: list[dict[str, Any]], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    for segment in segments:
        start = int(segment["start_ms"])
        end = int(segment["end_ms"])
        segment_rows = [row for row in rows if start <= int(row["time_ms"]) <= end]
        grouped.append({**segment, "rows": segment_rows})
    return grouped


def rows_by_plot_groups(segment_rows: list[dict[str, Any]], plot_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {segment["segment_id"]: segment for segment in segment_rows}
    grouped: list[dict[str, Any]] = []
    for group in plot_groups:
        rows: list[dict[str, Any]] = []
        for segment_id in group["segment_ids"]:
            rows.extend(by_id.get(segment_id, {}).get("rows", []))
        grouped.append({**group, "rows": rows})
    return grouped


def crop_bounds(crop: dict[str, Any]) -> tuple[int | None, int | None]:
    start = crop.get("start")
    end = crop.get("end")
    return (
        parse_time_bound_millis(start, field="start") if start else None,
        parse_time_bound_millis(end, field="end") if end else None,
    )


def crop_mask(time_ms: np.ndarray, start: int | None, end: int | None) -> np.ndarray:
    mask = np.ones(time_ms.shape, dtype=bool)
    if start is not None:
        mask &= time_ms >= start
    if end is not None:
        mask &= time_ms <= end
    return mask


def read_optional_1d(h5: h5py.File, path: str) -> np.ndarray:
    if not has_dataset(h5, path):
        return np.asarray([])
    return np.asarray(h5[path.strip("/")][:], dtype=float).reshape(-1)


def optional_value(values: np.ndarray, index: int) -> float | None:
    if index >= values.size:
        return None
    value = float(values[index])
    return value if np.isfinite(value) else None


def draw_magnetic_segments(
    path: Path,
    segments: list[dict[str, Any]],
    product: str,
    *,
    integer_hour_ticks: bool = False,
    title: str = "CSES HPM magnetic diagnostic by plot group",
) -> None:
    count = len(segments)
    cols = min(2, count)
    rows = int(math.ceil(count / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(7.2 * cols, 3.8 * rows), dpi=140, squeeze=False)
    for ax in axes.reshape(-1)[count:]:
        ax.axis("off")
    for ax, segment in zip(axes.reshape(-1), segments, strict=False):
        rows_data = segment["rows"]
        times = [datetime.fromtimestamp(row["time_ms"] / 1000, BEIJING_TZ).replace(tzinfo=None) for row in rows_data]
        if product == "HPM_6":
            values = np.asarray([row["values"][0] for row in rows_data], dtype=float)
            ax.plot(times, values, lw=1.1, color="#5f8376", label="A211")
            ax.set_ylabel("A211 (nT)")
        else:
            values = np.asarray([row["values"] for row in rows_data], dtype=float)
            labels = ["Bx", "By", "Bz"]
            colors = ["#2b6cb0", "#c05621", "#2f855a"]
            for idx, label in enumerate(labels):
                ax.plot(times, values[:, idx], lw=0.9, label=label, color=colors[idx])
            ax.plot(times, np.linalg.norm(values[:, :3], axis=1), lw=1.1, label="|B|", color="#1a202c")
            ax.set_ylabel("B (nT)")
        title_start = segment.get("display_start") or segment["start"]
        title_end = segment.get("display_end") or segment["end"]
        ax.set_title(f"{title_start} - {title_end} UTC+8", fontsize=9)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=7)
        if integer_hour_ticks:
            ax.xaxis.set_major_locator(mdates.HourLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        ax.set_xlabel("UTC+8 time")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    radius = EARTH_RADIUS_KM + alt_km
    return radius * math.cos(lat) * math.cos(lon), radius * math.cos(lat) * math.sin(lon), radius * math.sin(lat)


def color_map_for_segments(segments: list[dict[str, Any]], plot_groups: list[dict[str, Any]]) -> dict[str, str]:
    colors: dict[str, str] = {}
    for group_index, group in enumerate(plot_groups):
        family = SEGMENT_COLOR_FAMILIES[group_index % len(SEGMENT_COLOR_FAMILIES)]
        for segment_index, segment_id in enumerate(group["segment_ids"]):
            colors[segment_id] = family[segment_index % len(family)]
    for index, segment in enumerate(segments):
        colors.setdefault(segment["segment_id"], SEGMENT_COLORS[index % len(SEGMENT_COLORS)])
    return colors


def build_orbit_gap_links(segments: list[dict[str, Any]], segment_ranges: list[dict[str, Any]], colors: dict[str, str]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    by_id = {segment["segment_id"]: segment for segment in segments}
    for previous_range, current_range in zip(segment_ranges[:-1], segment_ranges[1:], strict=False):
        gap_ms = int(current_range["start_ms"]) - int(previous_range["end_ms"])
        if gap_ms >= ORBIT_LINK_GAP_MS:
            continue
        previous = by_id.get(previous_range["segment_id"])
        current = by_id.get(current_range["segment_id"])
        if not previous or not current or not previous.get("rows") or not current.get("rows"):
            continue
        last_row = previous["rows"][-1]
        first_row = current["rows"][0]
        points = great_circle_link_points(
            float(last_row["lat"]),
            float(last_row["lon"]),
            float(last_row["alt"]),
            float(first_row["lat"]),
            float(first_row["lon"]),
            float(first_row["alt"]),
        )
        links.append(
            {
                "from_segment_id": previous_range["segment_id"],
                "to_segment_id": current_range["segment_id"],
                "gap_minutes": round(gap_ms / 60000, 3),
                "color": colors.get(previous_range["segment_id"], "#5f8376"),
                "points": points,
            }
        )
    return links


def great_circle_link_points(start_lat: float, start_lon: float, start_alt: float, end_lat: float, end_lon: float, end_alt: float) -> list[dict[str, float]]:
    start_vec = unit_vector(start_lat, start_lon)
    end_vec = unit_vector(end_lat, end_lon)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(start_vec, end_vec, strict=True))))
    omega = math.acos(dot)
    points: list[dict[str, float]] = []
    for index in range(18):
        t = index / 17
        if omega < 1e-9:
            vec = start_vec
        else:
            sin_omega = math.sin(omega)
            a = math.sin((1 - t) * omega) / sin_omega
            b = math.sin(t * omega) / sin_omega
            vec = tuple(a * start_vec[i] + b * end_vec[i] for i in range(3))
        norm = math.sqrt(sum(item * item for item in vec)) or 1.0
        unit = tuple(item / norm for item in vec)
        alt = start_alt + (end_alt - start_alt) * t
        radius = EARTH_RADIUS_KM + alt
        points.append({"x": round(unit[0] * radius, 3), "y": round(unit[1] * radius, 3), "z": round(unit[2] * radius, 3)})
    return points


def unit_vector(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    return math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)


def write_interactive_orbit_html(path: Path, segments: list[dict[str, Any]], segment_ranges: list[dict[str, Any]], plot_groups: list[dict[str, Any]]) -> None:
    payload_segments: list[dict[str, Any]] = []
    segment_colors = color_map_for_segments(segment_ranges, plot_groups)
    gap_links = build_orbit_gap_links(segments, segment_ranges, segment_colors)
    for index, segment in enumerate(segments):
        x: list[float] = []
        y: list[float] = []
        z: list[float] = []
        lat: list[float] = []
        lon: list[float] = []
        alt: list[float] = []
        time: list[str] = []
        display_time: list[str] = []
        for row in segment["rows"]:
            px, py, pz = geodetic_to_ecef(float(row["lat"]), float(row["lon"]), float(row["alt"]))
            x.append(round(px, 3))
            y.append(round(py, 3))
            z.append(round(pz, 3))
            lat.append(round(float(row["lat"]), 5))
            lon.append(round(float(row["lon"]), 5))
            alt.append(round(float(row["alt"]), 3))
            time.append(row.get("time_utc") or format_utc_millis(int(row["time_ms"])))
            display_time.append(row.get("display_time") or format_beijing_millis(int(row["time_ms"])))
        payload_segments.append(
            {
                "segment_id": segment["segment_id"],
                "start": segment["start"],
                "end": segment["end"],
                "display_start": segment.get("display_start") or format_beijing_millis(int(segment["start_ms"])),
                "display_end": segment.get("display_end") or format_beijing_millis(int(segment["end_ms"])),
                "color": segment_colors.get(segment["segment_id"], SEGMENT_COLORS[index % len(SEGMENT_COLORS)]),
                "x": x,
                "y": y,
                "z": z,
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "time": time,
                "display_time": display_time,
            }
        )
    payload = {
        "earth_radius_km": EARTH_RADIUS_KM,
        "segments": payload_segments,
        "segment_ranges": segment_ranges,
        "plot_groups": plot_groups,
        "gap_links": gap_links,
        "overall_start": segment_ranges[0]["start"] if segment_ranges else None,
        "overall_end": segment_ranges[-1]["end"] if segment_ranges else None,
        "overall_display_start": segment_ranges[0].get("display_start") if segment_ranges else None,
        "overall_display_end": segment_ranges[-1].get("display_end") if segment_ranges else None,
    }
    path.write_text(interactive_orbit_html(payload), encoding="utf-8")


def interactive_orbit_html(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(json_safe(payload), ensure_ascii=False)
    earth_texture_json = json.dumps(earth_texture_data_url())
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CSES HPM 交互轨道图</title>
  <style>
    body {{ margin: 0; background: #f4ecd8; color: #211c16; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; padding: 12px 16px; border-bottom: 2px solid #2a2923; }}
    h1 {{ margin: 0; font-size: 18px; }}
    button {{ border: 2px solid #2a2923; background: #c88b2d; padding: 8px 12px; font-weight: 700; }}
    .stage {{ position: relative; height: calc(100vh - 64px); min-height: 520px; }}
    canvas {{ width: 100%; height: 100%; display: block; touch-action: none; cursor: grab; }}
    .readout, .legend {{ position: absolute; background: rgba(244,236,216,.9); border: 1px solid #2a2923; padding: 8px; font-size: 12px; line-height: 1.45; }}
    .readout {{ left: 12px; top: 12px; min-width: 260px; }}
    .legend {{ right: 12px; top: 12px; }}
  </style>
</head>
<body>
<header><div><h1>轨道图</h1><div>起始时间: {payload.get('overall_display_start')} / 结束时间: {payload.get('overall_display_end')} 北京时间</div></div><button id="resetView">Reset view</button></header>
<section class="stage">
  <canvas id="orbitCanvas"></canvas>
  <div class="readout" id="pointReadout"><strong>最近点</strong><br>在轨道上移动鼠标读取经纬度。</div>
  <div class="legend"><strong>Segments</strong><div id="legendRows"></div><div>Lat/Lon grid: 30 deg spacing</div></div>
</section>
<script>
const orbitData = {payload_json};
const earthTextureUrl = {earth_texture_json};
const uiFont = '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif';
const canvas = document.getElementById("orbitCanvas");
const ctx = canvas.getContext("2d");
const resetButton = document.getElementById("resetView");
const readout = document.getElementById("pointReadout");
document.getElementById("legendRows").innerHTML = orbitData.segments.map(s => `<div style="color:${{s.color}}">${{s.segment_id}}: ${{s.display_start}} - ${{s.display_end}}</div>`).join("");
let yaw = 0.75, pitch = -0.34, zoom = 1.0, dragging = false, lastX = 0, lastY = 0, pointer = null, projectedPoints = [];
const earthTexture = {{ ready: false, width: 0, height: 0, data: null }};
if (earthTextureUrl) {{
  const earthImage = new Image();
  earthImage.onload = () => {{
    const textureCanvas = document.createElement("canvas");
    textureCanvas.width = earthImage.naturalWidth;
    textureCanvas.height = earthImage.naturalHeight;
    const textureCtx = textureCanvas.getContext("2d");
    textureCtx.drawImage(earthImage, 0, 0);
    const texturePixels = textureCtx.getImageData(0, 0, textureCanvas.width, textureCanvas.height);
    earthTexture.ready = true;
    earthTexture.width = textureCanvas.width;
    earthTexture.height = textureCanvas.height;
    earthTexture.data = texturePixels.data;
    draw();
  }};
  earthImage.src = earthTextureUrl;
}}
function resizeCanvas() {{ const r = canvas.getBoundingClientRect(); const d = window.devicePixelRatio || 1; canvas.width = Math.max(1, Math.round(r.width*d)); canvas.height = Math.max(1, Math.round(r.height*d)); ctx.setTransform(d,0,0,d,0,0); draw(); }}
function rotatePoint(x,y,z) {{ const cy=Math.cos(yaw), sy=Math.sin(yaw), cp=Math.cos(pitch), sp=Math.sin(pitch); const x1=x*cy-y*sy, y1=x*sy+y*cy; return {{x:x1,y:y1*cp-z*sp,z:y1*sp+z*cp}}; }}
function project(p, scale, cx, cy) {{ const depth=18000; const k=depth/(depth-p.z); return {{x:cx+p.x*scale*k,y:cy-p.y*scale*k,z:p.z,k}}; }}
function geo(latDeg, lonDeg, radius) {{ const lat=latDeg*Math.PI/180, lon=lonDeg*Math.PI/180; return {{x:radius*Math.cos(lat)*Math.cos(lon),y:radius*Math.cos(lat)*Math.sin(lon),z:radius*Math.sin(lat)}}; }}
function projectedGeoPoint(lat, lon, radius, scale, cx, cy) {{ const p=geo(lat, lon, radius); return project(rotatePoint(p.x,p.y,p.z),scale,cx,cy); }}
function line(points, color, width=1) {{ if(points.length<2)return; ctx.beginPath(); ctx.moveTo(points[0].x,points[0].y); for(let i=1;i<points.length;i++)ctx.lineTo(points[i].x,points[i].y); ctx.strokeStyle=color; ctx.lineWidth=width; ctx.stroke(); }}
function dashedLine(points, color, width=1) {{ if(points.length<2)return; ctx.save(); ctx.setLineDash([6, 6]); ctx.beginPath(); ctx.moveTo(points[0].x,points[0].y); for(let i=1;i<points.length;i++)ctx.lineTo(points[i].x,points[i].y); ctx.strokeStyle=color; ctx.lineWidth=width; ctx.stroke(); ctx.restore(); }}
function segmentHighlightColor(color) {{ const match = /^#?([a-f\\d]{{2}})([a-f\\d]{{2}})([a-f\\d]{{2}})$/i.exec(color || ""); if(!match) return "rgba(255,244,214,.95)"; const r=Math.min(255, parseInt(match[1],16)+70), g=Math.min(255, parseInt(match[2],16)+54), b=Math.min(255, parseInt(match[3],16)+42); return `rgb(${{r}},${{g}},${{b}})`; }}
function drawOrbitStroke(points, color) {{ if(points.length<2)return; line(points, "rgba(42,41,35,.86)", 8.2); line(points, "rgba(244,236,216,.94)", 6.0); line(points, color, 3.4); ctx.save(); ctx.setLineDash([2, 8]); ctx.lineCap="round"; ctx.beginPath(); ctx.moveTo(points[0].x,points[0].y); for(let i=1;i<points.length;i++)ctx.lineTo(points[i].x,points[i].y); ctx.strokeStyle=segmentHighlightColor(color); ctx.lineWidth=2.0; ctx.stroke(); ctx.restore(); }}
function label(text, p, dx=0, dy=0) {{ ctx.save(); ctx.font="11px " + uiFont; ctx.strokeStyle="rgba(244,236,216,.92)"; ctx.lineWidth=3; ctx.fillStyle="#2a2923"; ctx.strokeText(text,p.x+dx,p.y+dy); ctx.fillText(text,p.x+dx,p.y+dy); ctx.restore(); }}
function drawLatitudeLongitudeGrid(cx, cy, scale) {{ const radius=orbitData.earth_radius_km; for(let lat=-60;lat<=60;lat+=30){{ const pts=[]; for(let lon=-180;lon<=180;lon+=5)pts.push(projectedGeoPoint(lat,lon,radius,scale,cx,cy)); line(pts, lat===0?"rgba(188,131,39,.56)":"rgba(95,131,118,.35)", lat===0?1.4:.9); label(`Latitude ${{lat}} deg`, projectedGeoPoint(lat,-170,radius,scale,cx,cy),4,-4); }} for(let lon=-180;lon<180;lon+=30){{ const pts=[]; for(let lat=-90;lat<=90;lat+=4)pts.push(projectedGeoPoint(lat,lon,radius,scale,cx,cy)); line(pts, lon===0?"rgba(188,131,39,.56)":"rgba(95,131,118,.28)", lon===0?1.4:.8); if(lon%60===0)label(`Longitude ${{lon}} deg`, projectedGeoPoint(0,lon,radius,scale,cx,cy),6,12); }} }}
function drawFallbackEarth(cx, cy, radius) {{
  const ocean=ctx.createRadialGradient(cx-radius*.32,cy-radius*.38,radius*.08,cx,cy,radius);
  ocean.addColorStop(0,"#9ed2f3");
  ocean.addColorStop(.45,"#2f8fc1");
  ocean.addColorStop(1,"#15527c");
  ctx.beginPath();
  ctx.arc(cx,cy,radius,0,Math.PI*2);
  ctx.fillStyle=ocean;
  ctx.fill();
}}
function drawTexturedEarth(cx, cy, radius) {{
  if (!earthTexture.ready || !earthTexture.data) {{
    drawFallbackEarth(cx, cy, radius);
    return;
  }}
  const diameter = Math.max(32, Math.round(radius * 2));
  const image = ctx.createImageData(diameter, diameter);
  const out = image.data;
  const cosYaw=Math.cos(yaw), sinYaw=Math.sin(yaw), cosPitch=Math.cos(pitch), sinPitch=Math.sin(pitch);
  const light = {{x: -0.45, y: -0.34, z: 0.83}};
  for (let py = 0; py < diameter; py++) {{
    const ny = (py + 0.5 - radius) / radius;
    for (let px = 0; px < diameter; px++) {{
      const nx = (px + 0.5 - radius) / radius;
      const r2 = nx * nx + ny * ny;
      if (r2 > 1) continue;
      const viewZ = Math.sqrt(Math.max(0, 1 - r2));
      const viewX = nx;
      const viewY = -ny;
      const yawY = viewY * cosPitch + viewZ * sinPitch;
      const worldZ = -viewY * sinPitch + viewZ * cosPitch;
      const worldX = viewX * cosYaw + yawY * sinYaw;
      const worldY = -viewX * sinYaw + yawY * cosYaw;
      let lon = Math.atan2(worldY, worldX);
      let lat = Math.asin(Math.max(-1, Math.min(1, worldZ)));
      let u = (lon + Math.PI) / (Math.PI * 2);
      let v = (Math.PI / 2 - lat) / Math.PI;
      let tx = Math.min(earthTexture.width - 1, Math.max(0, Math.floor(u * earthTexture.width)));
      let ty = Math.min(earthTexture.height - 1, Math.max(0, Math.floor(v * earthTexture.height)));
      const src = (ty * earthTexture.width + tx) * 4;
      const dst = (py * diameter + px) * 4;
      const limb = Math.pow(viewZ, 0.36);
      const sun = Math.max(0, worldX * light.x + worldY * light.y + worldZ * light.z);
      const shade = 0.34 + 0.56 * limb + 0.22 * sun;
      out[dst] = Math.min(255, earthTexture.data[src] * shade + 14 * sun);
      out[dst + 1] = Math.min(255, earthTexture.data[src + 1] * shade + 18 * sun);
      out[dst + 2] = Math.min(255, earthTexture.data[src + 2] * shade + 28 * sun);
      out[dst + 3] = 255;
    }}
  }}
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI*2);
  ctx.clip();
  const globeCanvas = document.createElement("canvas");
  globeCanvas.width = diameter;
  globeCanvas.height = diameter;
  globeCanvas.getContext("2d").putImageData(image, 0, 0);
  ctx.drawImage(globeCanvas, cx - radius, cy - radius, diameter, diameter);
  ctx.restore();
}}
function drawEarthAtmosphere(cx, cy, radius) {{
  const shade = ctx.createRadialGradient(cx-radius*.38, cy-radius*.45, radius*.12, cx+radius*.18, cy+radius*.16, radius*1.08);
  shade.addColorStop(0, "rgba(255,255,255,.48)");
  shade.addColorStop(.45, "rgba(255,255,255,0)");
  shade.addColorStop(.78, "rgba(20,58,89,.12)");
  shade.addColorStop(1, "rgba(10,28,48,.48)");
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI*2);
  ctx.fillStyle=shade;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(cx, cy, radius*1.018, 0, Math.PI*2);
  ctx.strokeStyle="rgba(114,169,207,.62)";
  ctx.lineWidth=2;
  ctx.stroke();
}}
function drawEarth(cx, cy, scale) {{
  const center=project(rotatePoint(0,0,0),scale,cx,cy);
  const radius=orbitData.earth_radius_km*scale;
  drawTexturedEarth(center.x, center.y, radius);
  drawEarthAtmosphere(center.x, center.y, radius);
}}
function drawCurvedGapLinks(cx, cy, scale) {{ for(const link of orbitData.gap_links || []){{ const pts=link.points.map(p=>project(rotatePoint(p.x,p.y,p.z),scale,cx,cy)); dashedLine(pts, "rgba(244,236,216,.78)", 4.2); dashedLine(pts, link.color, 2.0); }} }}
function nearest() {{ if(!pointer) return null; let best=null; for(const p of projectedPoints){{ const d=(p.x-pointer.x)**2+(p.y-pointer.y)**2; if(!best||d<best.d) best={{...p,d}}; }} return best&&best.d<900?best:null; }}
function draw() {{ const r=canvas.getBoundingClientRect(), cx=r.width/2, cy=r.height/2, scale=Math.min(r.width,r.height)/15500*zoom; ctx.clearRect(0,0,r.width,r.height); drawEarth(cx,cy,scale); drawLatitudeLongitudeGrid(cx,cy,scale); drawCurvedGapLinks(cx,cy,scale); projectedPoints=[]; for(const seg of orbitData.segments){{ const pts=seg.x.map((x,i)=>{{ const p=project(rotatePoint(x,seg.y[i],seg.z[i]),scale,cx,cy); return {{...p,seg:seg.segment_id,color:seg.color,index:i,lat:seg.lat[i],lon:seg.lon[i],alt:seg.alt[i],time:seg.time[i],displayTime:seg.display_time[i]}}; }}); projectedPoints.push(...pts); drawOrbitStroke(pts, seg.color); for(const p of pts){{ ctx.beginPath(); ctx.arc(p.x,p.y,4.6,0,Math.PI*2); ctx.fillStyle="rgba(42,41,35,.86)"; ctx.fill(); ctx.beginPath(); ctx.arc(p.x,p.y,3.4,0,Math.PI*2); ctx.fillStyle="rgba(244,236,216,.96)"; ctx.fill(); ctx.beginPath(); ctx.arc(p.x,p.y,2.4,0,Math.PI*2); ctx.fillStyle=seg.color; ctx.fill(); }} if(pts[0]){{ ctx.beginPath(); ctx.arc(pts[0].x,pts[0].y,8.8,0,Math.PI*2); ctx.fillStyle="#f4ecd8"; ctx.fill(); ctx.strokeStyle="rgba(42,41,35,.9)"; ctx.lineWidth=4.6; ctx.stroke(); ctx.beginPath(); ctx.arc(pts[0].x,pts[0].y,6.6,0,Math.PI*2); ctx.strokeStyle=seg.color; ctx.lineWidth=3.0; ctx.stroke(); }} }} const n=nearest(); if(n){{ readout.innerHTML=`<strong>最近点</strong><br>Segment: ${{n.seg}}<br>时间: ${{n.displayTime}} 北京时间<br>纬度: ${{n.lat.toFixed(3)}} deg<br>经度: ${{n.lon.toFixed(3)}} deg<br>高度: ${{n.alt.toFixed(1)}} km`; ctx.beginPath(); ctx.arc(n.x,n.y,8,0,Math.PI*2); ctx.strokeStyle="#111"; ctx.lineWidth=2; ctx.stroke(); }} }}
function reset() {{ yaw=.75; pitch=-.34; zoom=1; draw(); }}
canvas.addEventListener("pointerdown", e=>{{ dragging=true; canvas.setPointerCapture(e.pointerId); lastX=e.clientX; lastY=e.clientY; }});
canvas.addEventListener("pointermove", e=>{{ const r=canvas.getBoundingClientRect(); pointer={{x:e.clientX-r.left,y:e.clientY-r.top}}; if(dragging){{ yaw+=(e.clientX-lastX)*.008; pitch=Math.max(-1.45,Math.min(1.45,pitch+(e.clientY-lastY)*.008)); lastX=e.clientX; lastY=e.clientY; }} draw(); }});
canvas.addEventListener("pointerup", ()=>{{ dragging=false; draw(); }});
canvas.addEventListener("pointerleave", ()=>{{ pointer=null; readout.innerHTML="<strong>最近点</strong><br>在轨道上移动鼠标读取经纬度。"; draw(); }});
canvas.addEventListener("wheel", e=>{{ e.preventDefault(); zoom=Math.max(.35,Math.min(4,zoom*Math.exp(-e.deltaY*.0012))); draw(); }}, {{passive:false}});
canvas.addEventListener("dblclick", reset); resetButton.addEventListener("click", reset); window.addEventListener("resize", resizeCanvas); resizeCanvas();
</script>
</body></html>
"""


def unavailable_plot(session: dict[str, Any], plot_type: str, reason: str) -> dict[str, Any]:
    return {
        "upload_session_id": session["upload_session_id"],
        "plot_type": plot_type,
        "status": "unavailable",
        "reason": reason,
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value
