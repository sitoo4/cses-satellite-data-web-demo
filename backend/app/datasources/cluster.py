from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.artifacts import ArtifactRegistry
from app.core.config import AppConfig
from app.datasources.base import DataSource
from app.datasources.cses_hpm import json_safe
from app.services.plotting import (
    plot_cluster_b_quicklook,
    plot_cluster_orbit_overview,
    plot_dual_psd_spectrogram,
    plot_electric_timeseries,
    plot_magnetic_timeseries,
    plot_psd_spectrogram,
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
    read_array_range,
    request_digest,
    sanitize_id,
    stats_extension,
    stats_media_type,
    write_manifest,
    write_stats_artifact,
    write_table_export,
)


class ClusterDataSource(DataSource):
    name = "cluster"
    label = "Cluster C1 processed products"
    datasource_type = "Cluster CDF multi-instrument datasource"
    solar_wind_fields = ["flow_speed", "SYM-H", "pdyn", "AE", "Kp", "Bmag_model"]
    cluster_b_quicklook_fields = [
        "segment_time_context_unix",
        "segment_time_wavelet_unix",
        "segment_frequency_axis",
        "segment_B_GSE",
        "segment_B_MFA_after_delete",
        "segment_dB_MFA_detrended",
        "segment_dB_radial_psd",
        "segment_dB_phi_psd",
        "segment_dB_parallel_psd",
        "segment_sqrt_Br_band_power",
        "segment_sqrt_Bphi_band_power",
        "segment_sqrt_Bpar_band_power",
        "segment_L",
        "segment_MLT",
        "segment_MLAT",
    ]

    def __init__(self, config: AppConfig, artifacts: ArtifactRegistry) -> None:
        self.config = config
        self.artifacts = artifacts

    @property
    def root(self) -> Path:
        return self.config.cluster_processed_root

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": "available" if self.root.exists() else "missing",
            "root_status": {
                "raw_root": "confirmed" if self.config.cluster_raw_root.exists() else "missing",
                "processed_root": "confirmed" if self.root.exists() else "missing",
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
            "blocked": [
                {
                    "feature": "production_rerun",
                    "reason": "Web runtime is read-only for existing processed products; production reruns stay disabled.",
                }
            ],
            "unsupported": [],
            "inventory": self._inventory_counts(),
            "paths": {
                "raw_root": str(Path(self.config.cluster_raw_root)),
                "processed_root": str(Path(self.root)),
            },
        }

    def list_files(self, filters: dict[str, Any]) -> dict[str, Any]:
        year_filter = str(filters.get("year") or "")
        limit = filters.get("limit")
        rows = []
        dates = self._available_dates()
        for date8 in sorted(dates):
            if year_filter and not date8.startswith(year_filter):
                continue
            products = self._product_paths(date8)
            rows.append(
                {
                    "file_id": date8,
                    "date": date8,
                    "year": date8[:4],
                    "products": {
                        name: {"path": str(path), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0}
                        for name, path in products.items()
                    },
                }
            )
        total = len(rows)
        if limit is not None:
            rows = rows[: int(limit)]
        return {"datasource": self.name, "total_count": total, "files": rows}

    def metadata(self, file_id: str | None = None) -> dict[str, Any]:
        date8 = self._validate_date(file_id)
        products = self._product_paths(date8)
        if not products["daily_full"].exists():
            raise FileNotFoundError(f"daily_full product not found for {date8}")

        with np.load(products["daily_full"], allow_pickle=False) as z:
            keys = [{"name": key, "shape": list(z[key].shape), "dtype": str(z[key].dtype)} for key in z.files]
            time_summary = self._time_summary(z)
            quality_summary = self._quality_summary(z)

        compact_columns: list[dict[str, str]] = []
        compact_rows = 0
        if products["daily_compact"].exists():
            df_head = pd.read_parquet(products["daily_compact"])
            compact_rows = int(len(df_head))
            compact_columns = [{"name": col, "dtype": str(dtype)} for col, dtype in df_head.dtypes.items()]

        manifest = {}
        if products["manifest"].exists():
            manifest = json.loads(products["manifest"].read_text(encoding="utf-8"))

        return {
            "datasource": self.name,
            "file_id": date8,
            "date": date8,
            "products": {
                name: {"path": str(path), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0}
                for name, path in products.items()
            },
            "manifest": self._safe_manifest_subset(manifest),
            "time_summary": time_summary,
            "quality_summary": quality_summary,
            "candidates": {"quality_flag": [{"path": "segment_E_quality", "confidence": "confirmed"}]} if quality_summary["status"] == "parsed" else {},
            "daily_full": {"key_count": len(keys), "keys": keys},
            "daily_compact": {"row_count": compact_rows, "column_count": len(compact_columns), "columns": compact_columns},
        }

    def variables(self, file_id: str | None = None) -> dict[str, Any]:
        date8 = self._validate_date(file_id)
        products = self._product_paths(date8)
        with np.load(products["daily_full"], allow_pickle=False) as z:
            variables = [self._variable_descriptor(key, z[key]) for key in z.files if z[key].shape != ()]
        return {"datasource": self.name, "file_id": date8, "variables": variables}

    def plot_catalog(self, file_id: str | None = None) -> dict[str, Any]:
        date8 = self._validate_date(file_id) if file_id else None
        keys: set[str] = set()
        if date8:
            source = self._product_paths(date8)["daily_full"]
            if source.exists():
                with np.load(source, allow_pickle=False) as z:
                    keys = set(z.files)
        cluster_b_quicklook_available = not date8 or set(self.cluster_b_quicklook_fields).issubset(keys)
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plots": [
                {
                    "plot_type": "cluster_magnetic_overview",
                    "display_name": "Magnetic overview",
                    "description": "Segment-only B quicklook regenerated with the idlpython_v2 B panel recipe.",
                    "enabled": bool(cluster_b_quicklook_available),
                    "disabled_reason": None if cluster_b_quicklook_available else "missing segment B quicklook fields in daily_full",
                    "required_fields": self.cluster_b_quicklook_fields,
                    "confirmed_fields": [field for field in self.cluster_b_quicklook_fields if not date8 or field in keys],
                    "inferred_fields": [],
                    "output_group": "cluster",
                },
                {
                    "plot_type": "cluster_electric_overview",
                    "display_name": "Electric overview",
                    "description": "Electric field MFA components plus magnitude regenerated from daily_full.",
                    "enabled": bool(not date8 or "segment_E_MFA" in keys),
                    "disabled_reason": None if not date8 or "segment_E_MFA" in keys else "missing field segment_E_MFA in daily_full or EFW quality unavailable",
                    "required_fields": ["segment_E_MFA", "segment_time_context_unix"],
                    "confirmed_fields": ["segment_E_MFA"] if not date8 or "segment_E_MFA" in keys else [],
                    "inferred_fields": [],
                    "output_group": "cluster",
                },
                {
                    "plot_type": "cluster_spectrogram_overview",
                    "display_name": "Spectrogram overview",
                    "description": "B/E phi PSD spectrogram panels regenerated from daily_full PSD arrays.",
                    "enabled": bool(not date8 or {"segment_dB_phi_psd", "segment_dE_phi_psd", "segment_frequency_axis", "segment_time_wavelet_unix"}.issubset(keys)),
                    "disabled_reason": None
                    if not date8 or {"segment_dB_phi_psd", "segment_dE_phi_psd", "segment_frequency_axis", "segment_time_wavelet_unix"}.issubset(keys)
                    else "missing PSD, frequency, or wavelet time arrays in daily_full",
                    "required_fields": ["segment_dB_phi_psd", "segment_dE_phi_psd", "segment_frequency_axis", "segment_time_wavelet_unix"],
                    "confirmed_fields": [field for field in ["segment_dB_phi_psd", "segment_dE_phi_psd", "segment_frequency_axis", "segment_time_wavelet_unix"] if not date8 or field in keys],
                    "inferred_fields": [],
                    "output_group": "cluster",
                },
                {
                    "plot_type": "cluster_orbit_overview",
                    "display_name": "Orbit overview",
                    "description": "MLT/MLAT and L/MLAT orbit panels regenerated from daily_full context arrays.",
                    "enabled": bool(not date8 or {"segment_MLT", "segment_MLAT", "segment_L"}.issubset(keys)),
                    "disabled_reason": None if not date8 or {"segment_MLT", "segment_MLAT", "segment_L"}.issubset(keys) else "missing MLT, MLAT, or L context arrays in daily_full",
                    "required_fields": ["segment_MLT", "segment_MLAT", "segment_L"],
                    "confirmed_fields": [field for field in ["segment_MLT", "segment_MLAT", "segment_L"] if not date8 or field in keys],
                    "inferred_fields": [],
                    "output_group": "cluster",
                },
            ],
        }

    def plot(self, request: dict[str, Any]) -> dict[str, Any]:
        date8 = self._validate_date(str(request.get("file_id") or ""))
        plot_type = str(request.get("plot_type") or "")
        if plot_type in {"existing_quicklook_b", "existing_quicklook_e", "existing_quicklook_pos"}:
            return {
                "datasource": self.name,
                "file_id": date8,
                "plot_type": plot_type,
                "status": "unsupported",
                "reason": "Existing quicklook images are reference/debug only; Web formal plot products are regenerated under outputs/generated_plots/cluster.",
            }
        if plot_type == "cluster_magnetic_overview":
            return self._plot_cluster_magnetic_overview(date8, request)
        if plot_type == "cluster_electric_overview":
            return self._plot_cluster_electric_overview(date8, request)
        if plot_type == "cluster_spectrogram_overview":
            return self._plot_cluster_spectrogram_overview(date8)
        if plot_type == "cluster_orbit_overview":
            return self._plot_cluster_orbit_overview(date8, request)
        if plot_type == "cluster_solar_wind_overview":
            return self._plot_cluster_solar_wind_overview(date8)
        if plot_type == "solar_wind":
            return {
                "datasource": self.name,
                "file_id": date8,
                "plot_type": plot_type,
                "status": "unsupported",
                "reason": "No validated solar-wind product is exposed in the current Cluster processed web datasource.",
            }
        if plot_type == "cluster_spectrogram_b":
            return self._plot_existing_b_spectrogram(date8)
        if plot_type == "cluster_spectrogram_e":
            return self._plot_existing_e_spectrogram(date8)
        if plot_type == "timeseries":
            return self._plot_processed_timeseries(date8, request)
        if plot_type == "electric_timeseries":
            return self._plot_processed_timeseries(
                date8,
                request,
                default_variable="segment_E_MFA",
                plot_type="electric_timeseries",
            )
        if plot_type == "orbit_2d":
            return self._plot_processed_orbit_2d(date8, request)
        if plot_type == "orbit_3d":
            return self._plot_processed_orbit_3d(date8, request)
        mapping: dict[str, str] = {}
        if plot_type not in mapping:
            return {
                "datasource": self.name,
                "status": "unsupported",
                "reason": "Cluster formal plot requests use datasource-specific overview plot types from plot-catalog.",
            }
        product = mapping[plot_type]
        path = self._product_paths(date8)[product]
        if not path.exists():
            raise FileNotFoundError(f"{product} not found for {date8}")
        artifact = self.artifacts.register(
            f"cluster:{product}:{date8}",
            path,
            media_type="image/png",
            label=f"{product} {date8}",
        )
        return {"datasource": self.name, "file_id": date8, "plot_type": plot_type, "artifact": artifact}

    def _plot_cluster_magnetic_overview(self, date8: str, request: dict[str, Any]) -> dict[str, Any]:
        source = self._product_paths(date8)["daily_full"]
        if not source.exists():
            return self._missing_daily_full_response(date8, "cluster_magnetic_overview", source)
        required = [
            "segment_time_context_unix",
            "segment_time_wavelet_unix",
            "segment_frequency_axis",
            "segment_B_GSE",
            "segment_B_MFA_after_delete",
            "segment_dB_MFA_detrended",
            "segment_dB_radial_psd",
            "segment_dB_phi_psd",
            "segment_dB_parallel_psd",
            "segment_sqrt_Br_band_power",
            "segment_sqrt_Bphi_band_power",
            "segment_sqrt_Bpar_band_power",
            "segment_L",
            "segment_MLT",
            "segment_MLAT",
        ]
        digest = request_digest({"file_id": date8, "plot_type": "cluster_magnetic_overview", "quicklook_recipe": "idlpython_v2_B"})
        out_path = self._generated_plot_path(f"{date8}_cluster_magnetic_overview_{digest}.png")
        with np.load(source, allow_pickle=False) as z:
            unavailable = self._missing_fields_response(date8, "cluster_magnetic_overview", required, z.files)
            if unavailable:
                return unavailable
            used_fields = plot_cluster_b_quicklook(
                out_path,
                date8=date8,
                segment_start_time=float(np.asarray(z["segment_start_time"])) if "segment_start_time" in z else None,
                segment_end_time=float(np.asarray(z["segment_end_time"])) if "segment_end_time" in z else None,
                time_context=np.asarray(z["segment_time_context_unix"], dtype=float),
                time_wavelet=np.asarray(z["segment_time_wavelet_unix"], dtype=float),
                frequency=np.asarray(z["segment_frequency_axis"], dtype=float),
                b_gse=np.asarray(z["segment_B_GSE"], dtype=float),
                b_mfa=np.asarray(z["segment_B_MFA_after_delete"], dtype=float),
                db_mfa=np.asarray(z["segment_dB_MFA_detrended"], dtype=float),
                db_radial_psd=np.asarray(z["segment_dB_radial_psd"], dtype=float),
                db_phi_psd=np.asarray(z["segment_dB_phi_psd"], dtype=float),
                db_parallel_psd=np.asarray(z["segment_dB_parallel_psd"], dtype=float),
                sqrt_br_band_power=np.asarray(z["segment_sqrt_Br_band_power"], dtype=float),
                sqrt_bphi_band_power=np.asarray(z["segment_sqrt_Bphi_band_power"], dtype=float),
                sqrt_bpar_band_power=np.asarray(z["segment_sqrt_Bpar_band_power"], dtype=float),
                l_shell=np.asarray(z["segment_L"], dtype=float),
                mlt=np.asarray(z["segment_MLT"], dtype=float),
                mlat=np.asarray(z["segment_MLAT"], dtype=float),
            )
            sample_count = int(np.asarray(z["segment_time_context_unix"]).size)
        artifact = self.artifacts.register(
            f"{self.name}:magnetic_overview:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster B quicklook {date8}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plot_type": "cluster_magnetic_overview",
            "source_product": "daily_full",
            "fields": [{"path": field, "unit": "nT or PSD/band-power context", "coordinate_system": "segment-first stored product"} for field in used_fields],
            "coordinate_system": "GSE/MFA stored segment fields",
            "sample_count": sample_count,
            "processing_log": [
                "Read segment-first B quicklook fields from daily_full.",
                "Matched /Volumes/Elements/data/idlpython_v2/plot_daily_quicklook.py B panel recipe.",
                "Used stored arrays only; no B-chain, detrend, wavelet, band-power, or context values were recomputed.",
            ],
            "artifact": artifact,
        }

    def _plot_cluster_electric_overview(self, date8: str, request: dict[str, Any]) -> dict[str, Any]:
        source = self._product_paths(date8)["daily_full"]
        if not source.exists():
            return self._missing_daily_full_response(date8, "cluster_electric_overview", source)
        variable = "segment_E_MFA"
        digest = request_digest({"file_id": date8, "plot_type": "cluster_electric_overview", "range": request.get("range", {})})
        out_path = self._generated_plot_path(f"{date8}_cluster_electric_overview_{digest}.png")
        quality_summary: dict[str, Any] = {}
        with np.load(source, allow_pickle=False) as z:
            unavailable = self._missing_fields_response(date8, "cluster_electric_overview", [variable], z.files)
            if unavailable:
                return unavailable
            range_payload = self._resolve_range(z, request.get("range", {}), default_limit=500, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            data = read_array_range(z[variable], start, end)
            time_data = read_array_range(z["segment_time_context_unix"], start, end) if "segment_time_context_unix" in z else np.asarray([])
            quality_summary = self._quality_summary(z)
        plot_vector_overview(
            out_path,
            x=time_data,
            data=data,
            title=f"Cluster electric overview {date8} ({variable}, MFA, mV/m)",
            component_labels=["E_MFA_1", "E_MFA_2", "E_MFA_3"],
            ylabel="E (mV/m)",
            magnitude_label="|E|",
        )
        artifact = self.artifacts.register(
            f"{self.name}:electric_overview:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster electric overview {date8}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plot_type": "cluster_electric_overview",
            "source_product": "daily_full",
            "fields": [{"path": variable, "unit": "mV/m", "coordinate_system": "MFA", "components": ["E_MFA_1", "E_MFA_2", "E_MFA_3", "|E|"]}],
            "coordinate_system": "MFA",
            "quality_summary": quality_summary,
            "range": self._range_response(range_payload, sample_count=max(0, end - start)),
            "processing_log": [
                "Read segment_E_MFA from daily_full.",
                "Reported segment_E_quality distribution without applying automatic masking.",
                "Regenerated the formal Web PNG under outputs/generated_plots/cluster.",
            ],
            "artifact": artifact,
        }

    def _plot_cluster_spectrogram_overview(self, date8: str) -> dict[str, Any]:
        source = self._product_paths(date8)["daily_full"]
        if not source.exists():
            return self._missing_daily_full_response(date8, "cluster_spectrogram_overview", source)
        required = ["segment_dB_phi_psd", "segment_dE_phi_psd", "segment_frequency_axis", "segment_time_wavelet_unix"]
        digest = request_digest({"file_id": date8, "plot_type": "cluster_spectrogram_overview"})
        out_path = self._generated_plot_path(f"{date8}_cluster_spectrogram_overview_{digest}.png")
        with np.load(source, allow_pickle=False) as z:
            unavailable = self._missing_fields_response(date8, "cluster_spectrogram_overview", required, z.files)
            if unavailable:
                return unavailable
            b_psd = np.asarray(z["segment_dB_phi_psd"], dtype=float)
            e_psd = np.asarray(z["segment_dE_phi_psd"], dtype=float)
            frequency = np.asarray(z["segment_frequency_axis"], dtype=float)
            time = np.asarray(z["segment_time_wavelet_unix"], dtype=float)
        plot_dual_psd_spectrogram(
            out_path,
            time=time,
            frequency=frequency,
            b_psd=b_psd,
            e_psd=e_psd,
            title=f"Cluster B/E phi PSD overview {date8}",
        )
        artifact = self.artifacts.register(
            f"{self.name}:spectrogram_overview:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster B/E spectrogram overview {date8}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plot_type": "cluster_spectrogram_overview",
            "source_product": "daily_full",
            "psd_variables": ["segment_dB_phi_psd", "segment_dE_phi_psd"],
            "frequency_variable": "segment_frequency_axis",
            "time_variable": "segment_time_wavelet_unix",
            "fields": [
                {"path": "segment_dB_phi_psd", "unit": "nT^2/Hz", "coordinate_system": "MFA phi"},
                {"path": "segment_dE_phi_psd", "unit": "(mV/m)^2/Hz", "coordinate_system": "MFA phi"},
            ],
            "sample_count": int(time.size),
            "processing_log": [
                "Read segment_dB_phi_psd and segment_dE_phi_psd from daily_full.",
                "Regenerated a combined B/E PSD overview under outputs/generated_plots/cluster.",
            ],
            "artifact": artifact,
        }

    def _plot_cluster_orbit_overview(self, date8: str, request: dict[str, Any]) -> dict[str, Any]:
        source = self._product_paths(date8)["daily_full"]
        if not source.exists():
            return self._missing_daily_full_response(date8, "cluster_orbit_overview", source)
        required = ["segment_MLT", "segment_MLAT", "segment_L"]
        digest = request_digest({"file_id": date8, "plot_type": "cluster_orbit_overview", "range": request.get("range", {})})
        out_path = self._generated_plot_path(f"{date8}_cluster_orbit_overview_{digest}.png")
        with np.load(source, allow_pickle=False) as z:
            unavailable = self._missing_fields_response(date8, "cluster_orbit_overview", required, z.files)
            if unavailable:
                return unavailable
            range_payload = self._resolve_range(z, request.get("range", {}), default_limit=500, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            mlt = read_array_range(z["segment_MLT"], start, end)
            mlat = read_array_range(z["segment_MLAT"], start, end)
            l_shell = read_array_range(z["segment_L"], start, end)
        plot_cluster_orbit_overview(out_path, mlt=mlt, mlat=mlat, l_shell=l_shell, title=f"Cluster orbit overview {date8}")
        artifact = self.artifacts.register(
            f"{self.name}:orbit_overview:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster orbit overview {date8}",
        )
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plot_type": "cluster_orbit_overview",
            "source_product": "daily_full",
            "coordinate_variables": required,
            "fields": [{"path": field, "unit": self._variable_unit(field)} for field in required],
            "range": self._range_response(range_payload, sample_count=max(0, end - start)),
            "processing_log": [
                "Read segment_MLT, segment_MLAT, and segment_L from daily_full.",
                "Regenerated the formal orbit overview under outputs/generated_plots/cluster.",
            ],
            "artifact": artifact,
        }

    def _plot_cluster_solar_wind_overview(self, date8: str) -> dict[str, Any]:
        source = self._product_paths(date8)["daily_full"]
        if not source.exists():
            return self._missing_daily_full_response(date8, "cluster_solar_wind_overview", source)
        with np.load(source, allow_pickle=False) as z:
            available = set(z.files)
        missing = [field for field in self.solar_wind_fields if field not in available]
        if missing:
            return {
                "datasource": self.name,
                "datasource_type": self.datasource_type,
                "file_id": date8,
                "plot_type": "cluster_solar_wind_overview",
                "status": "unavailable",
                "required_fields": self.solar_wind_fields,
                "missing_fields": missing,
                "unverified_fields": [],
                "reason": "Solar-wind/context fields are not exposed in daily_full for this processed day; old quicklook/context traces were not treated as a validated web datasource product.",
                "processing_log": [
                    "Checked daily_full field names for flow_speed, SYM-H, pdyn, AE, Kp, and Bmag_model.",
                    "No formal Web PNG was generated because the required fields are missing or unverified.",
                ],
            }
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plot_type": "cluster_solar_wind_overview",
            "status": "unavailable",
            "required_fields": self.solar_wind_fields,
            "missing_fields": [],
            "unverified_fields": self.solar_wind_fields,
            "reason": "Solar-wind fields exist by name but have not yet been semantically validated for Web plotting.",
        }

    def _plot_existing_b_spectrogram(self, date8: str) -> dict[str, Any]:
        source = self._product_paths(date8)["daily_full"]
        digest = request_digest({"file_id": date8, "plot_type": "cluster_spectrogram_b"})
        out_path = self._generated_plot_path(f"{date8}_spectrogram_B_{digest}.png")
        with np.load(source, allow_pickle=False) as z:
            psd = np.asarray(z["segment_dB_phi_psd"], dtype=float)
            frequency = np.asarray(z["segment_frequency_axis"], dtype=float)
            time = np.asarray(z["segment_time_wavelet_unix"], dtype=float)
        plot_psd_spectrogram(out_path, time=time, frequency=frequency, psd=psd, title=f"Cluster B phi PSD {date8}")
        artifact = self.artifacts.register(
            f"{self.name}:spectrogram_B:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster B PSD spectrogram {date8}",
        )
        return {"datasource": self.name, "file_id": date8, "plot_type": "cluster_spectrogram_b", "artifact": artifact}

    def _plot_existing_e_spectrogram(self, date8: str) -> dict[str, Any]:
        source = self._product_paths(date8)["daily_full"]
        digest = request_digest({"file_id": date8, "plot_type": "cluster_spectrogram_e"})
        out_path = self._generated_plot_path(f"{date8}_spectrogram_E_{digest}.png")
        with np.load(source, allow_pickle=False) as z:
            psd = np.asarray(z["segment_dE_phi_psd"], dtype=float)
            frequency = np.asarray(z["segment_frequency_axis"], dtype=float)
            time = np.asarray(z["segment_time_wavelet_unix"], dtype=float)
        plot_psd_spectrogram(out_path, time=time, frequency=frequency, psd=psd, title=f"Cluster E phi PSD {date8}")
        artifact = self.artifacts.register(
            f"{self.name}:spectrogram_E:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster E PSD spectrogram {date8}",
        )
        return {
            "datasource": self.name,
            "file_id": date8,
            "plot_type": "cluster_spectrogram_e",
            "source_product": "daily_full",
            "psd_variable": "segment_dE_phi_psd",
            "artifact": artifact,
        }

    def _plot_processed_timeseries(
        self,
        date8: str,
        request: dict[str, Any],
        *,
        default_variable: str = "segment_B_MFA_after_delete",
        plot_type: str = "timeseries",
    ) -> dict[str, Any]:
        variable = str((request.get("variables") or [default_variable])[0])
        digest = request_digest({"file_id": date8, "plot_type": plot_type, "variable": variable, "range": request.get("range", {})})
        stem = sanitize_id(variable)
        out_path = self._generated_plot_path(f"{date8}_{plot_type}_{stem}_{digest}.png")
        with np.load(self._product_paths(date8)["daily_full"], allow_pickle=False) as z:
            range_payload = self._resolve_range(z, request.get("range", {}), default_limit=500, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            data = read_array_range(z[variable], start, end)
            time_data = read_array_range(z["segment_time_context_unix"], start, end) if "segment_time_context_unix" in z else np.asarray([])
        if data.ndim == 2 and data.shape[-1] == 3:
            if plot_type == "electric_timeseries" or variable.startswith(("segment_E", "segment_dE")):
                plot_electric_timeseries(out_path, x=time_data, e=data, title=f"Cluster {variable} {date8}")
            else:
                plot_magnetic_timeseries(out_path, x=time_data, b=data, title=f"Cluster {variable} {date8}")
        else:
            plot_scalar_timeseries(out_path, x=time_data, y=data, variable=variable, unit=self._variable_unit(variable), title=f"Cluster {variable} {date8}")
        label_prefix = "Cluster electric timeseries" if plot_type == "electric_timeseries" else "Cluster timeseries"
        artifact = self.artifacts.register(
            f"{self.name}:{plot_type}:{date8}:{stem}:{digest}",
            out_path,
            media_type="image/png",
            label=f"{label_prefix} {variable} {date8}",
        )
        return {
            "datasource": self.name,
            "file_id": date8,
            "plot_type": plot_type,
            "source_product": "daily_full",
            "variable": variable,
            "range": self._range_response(range_payload, sample_count=max(0, end - start)),
            "artifact": artifact,
        }

    def _plot_processed_orbit_2d(self, date8: str, request: dict[str, Any]) -> dict[str, Any]:
        digest = request_digest({"file_id": date8, "plot_type": "orbit_2d", "range": request.get("range", {})})
        out_path = self._generated_plot_path(f"{date8}_orbit_2d_{digest}.png")
        with np.load(self._product_paths(date8)["daily_full"], allow_pickle=False) as z:
            range_payload = self._resolve_range(z, request.get("range", {}), default_limit=500, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            lon = read_array_range(z["segment_MLT"], start, end)
            lat = read_array_range(z["segment_MLAT"], start, end)
        plot_trajectory_2d(out_path, lat=lat, lon=lon, title=f"Cluster MLT/MLAT trajectory {date8}")
        artifact = self.artifacts.register(
            f"{self.name}:orbit_2d:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster MLT/MLAT orbit {date8}",
        )
        return {
            "datasource": self.name,
            "file_id": date8,
            "plot_type": "orbit_2d",
            "source_product": "daily_full",
            "coordinate_variables": ["segment_MLT", "segment_MLAT"],
            "range": self._range_response(range_payload, sample_count=max(0, end - start)),
            "artifact": artifact,
        }

    def _plot_processed_orbit_3d(self, date8: str, request: dict[str, Any]) -> dict[str, Any]:
        digest = request_digest({"file_id": date8, "plot_type": "orbit_3d", "range": request.get("range", {})})
        out_path = self._generated_plot_path(f"{date8}_orbit_3d_{digest}.png")
        with np.load(self._product_paths(date8)["daily_full"], allow_pickle=False) as z:
            range_payload = self._resolve_range(z, request.get("range", {}), default_limit=500, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            lon = read_array_range(z["segment_MLT"], start, end)
            lat = read_array_range(z["segment_MLAT"], start, end)
            alt = read_array_range(z["segment_L"], start, end)
        plot_trajectory_3d(out_path, lat=lat, lon=lon, alt=alt, title=f"Cluster MLT/MLAT/L trajectory {date8}")
        artifact = self.artifacts.register(
            f"{self.name}:orbit_3d:{date8}:{digest}",
            out_path,
            media_type="image/png",
            label=f"Cluster MLT/MLAT/L orbit {date8}",
        )
        return {
            "datasource": self.name,
            "file_id": date8,
            "plot_type": "orbit_3d",
            "source_product": "daily_full",
            "coordinate_variables": ["segment_MLT", "segment_MLAT", "segment_L"],
            "range": self._range_response(range_payload, sample_count=max(0, end - start)),
            "artifact": artifact,
        }

    def subset(self, request: dict[str, Any]) -> dict[str, Any]:
        date8 = self._validate_date(str(request.get("file_id") or ""))
        variables = [str(item) for item in request.get("variables", [])]
        out_vars: list[dict[str, Any]] = []
        with np.load(self._product_paths(date8)["daily_full"], allow_pickle=False) as z:
            range_payload = self._resolve_range(z, request.get("range", {}))
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            preview_limit = max(0, int(request.get("preview_limit", end - start)))
            read_end = min(end, start + preview_limit)
            for variable in variables:
                data = read_array_range(z[variable], start, read_end)
                out_vars.append(
                    {
                        "path": variable,
                        "shape": list(z[variable].shape),
                        "dtype": str(z[variable].dtype),
                        "data": json_safe(data),
                    }
                )
        result = {
            "datasource": self.name,
            "file_id": date8,
            "range": self._range_response(range_payload, preview_end_index=read_end, sample_count=max(0, read_end - start)),
            "variables": out_vars,
        }
        return result

    def timeseries(self, request: dict[str, Any]) -> dict[str, Any]:
        date8 = self._validate_date(str(request.get("file_id") or ""))
        variables = [str(item) for item in request.get("variables", [])]
        out_vars: list[dict[str, Any]] = []
        with np.load(self._product_paths(date8)["daily_full"], allow_pickle=False) as z:
            range_payload = self._resolve_range(z, request.get("range", {}), default_limit=1000, max_samples=20000)
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            time_axis = self._timeseries_axis(z, start, end)
            for variable in variables:
                data = read_array_range(z[variable], start, end)
                out_vars.append(
                    {
                        "path": variable,
                        "shape": list(z[variable].shape),
                        "dtype": str(z[variable].dtype),
                        "data": json_safe(data),
                    }
                )
        return {
            "datasource": self.name,
            "file_id": date8,
            "range": self._range_response(range_payload, sample_count=max(0, end - start)),
            "time_axis": time_axis,
            "variables": out_vars,
        }

    def stats(self, request: dict[str, Any]) -> dict[str, Any]:
        date8 = self._validate_date(str(request.get("file_id") or ""))
        variables = [str(item) for item in request.get("variables", [])]
        out_vars: list[dict[str, Any]] = []
        with np.load(self._product_paths(date8)["daily_full"], allow_pickle=False) as z:
            range_payload = self._resolve_range(z, request.get("range", {}))
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            for variable in variables:
                out_vars.append(numeric_stats(variable, read_array_range(z[variable], start, end)))
        result = {
            "datasource": self.name,
            "file_id": date8,
            "range": self._range_response(range_payload, sample_count=max(0, end - start)),
            "variables": out_vars,
        }
        return self._maybe_attach_stats_artifact(result, request, file_id=date8)

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
        stem = sanitize_id(file_id)
        out_path = self.config.outputs_root / "stats" / self.name / f"{stem}_{digest}.{extension}"
        write_stats_artifact(out_path, save_format, result)
        artifact = self.artifacts.register(
            f"{self.name}:stats:{stem}:{digest}",
            out_path,
            media_type=stats_media_type(save_format),
            label=f"Cluster stats {file_id} {save_format.upper()}",
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
                "reason": "Phase 6 supports csv, dat, and h5 export for Cluster processed products; CDF remains reserved.",
            }
        date8 = self._validate_date(str(request.get("file_id") or ""))
        variables = [str(item) for item in request.get("variables", [])]
        export_vars: list[dict[str, Any]] = []
        source = self._product_paths(date8)["daily_full"]
        with np.load(source, allow_pickle=False) as z:
            range_payload = self._resolve_range(z, request.get("range", {}))
            start = int(range_payload["start_index"])
            end = int(range_payload["end_index"])
            for variable in variables:
                export_vars.append({"path": variable, "data": read_array_range(z[variable], start, end), "unit": self._variable_unit(variable)})
        digest = request_digest({"file_id": date8, "variables": variables, "range": request.get("range", {}), "format": export_format})
        extension = export_extension(export_format)
        out_path = self.config.outputs_root / "exports" / self.name / f"{date8}_{digest}.{extension}"
        table_info = write_table_export(out_path, export_format, start, export_vars)
        sample_count = int(table_info.get("row_count", max(0, end - start)))
        response_range = self._range_response(range_payload, sample_count=sample_count)
        manifest = build_export_manifest(
            datasource=self.name,
            file_id=date8,
            original_file=str(source),
            variables=export_vars,
            range_spec=response_range,
            export_format=export_format,
            sample_count=sample_count,
            artifact_path=out_path,
        )
        manifest_path = out_path.with_name(f"{out_path.stem}_manifest.json")
        write_manifest(manifest_path, manifest)
        artifact = self.artifacts.register(
            f"{self.name}:export:{date8}:{digest}",
            out_path,
            media_type=export_media_type(export_format),
            label=f"Cluster {export_format.upper()} export {date8}",
        )
        manifest_artifact = self.artifacts.register(
            f"{self.name}:export_manifest:{date8}:{digest}",
            manifest_path,
            media_type="application/json",
            label=f"Cluster export manifest {date8}",
        )
        return {
            "datasource": self.name,
            "file_id": date8,
            "format": export_format,
            "range": response_range,
            "table": table_info,
            "artifact": artifact,
            "manifest": manifest,
            "manifest_artifact": manifest_artifact,
        }

    def _resolve_range(
        self,
        z: np.lib.npyio.NpzFile,
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

        variable = "segment_time_context_unix"
        if variable not in z:
            raise ValueError("segment_time_context_unix not found in daily_full")
        time_values = np.asarray(z[variable], dtype=float).reshape(-1)
        if time_values.size > 1 and np.any(np.diff(time_values) < 0):
            raise ValueError("segment_time_context_unix must be monotonic for time range resolution")
        start_seconds = parse_cluster_time_bound_seconds(range_spec.get("start"), field="start")
        end_seconds = parse_cluster_time_bound_seconds(range_spec.get("end"), field="end")
        if end_seconds < start_seconds:
            raise ValueError("time range end must be greater than or equal to start")
        start_index = int(np.searchsorted(time_values, start_seconds, side="left"))
        end_index = int(np.searchsorted(time_values, end_seconds, side="left"))
        bounded_start = max(0, min(start_index, time_values.size))
        bounded_end = max(bounded_start, min(end_index, time_values.size))
        if bounded_end - bounded_start > max_samples:
            raise ValueError(f"time range is limited to {max_samples} samples")
        return {
            "mode": "time",
            "resolved_mode": "sample_index",
            "start": str(range_spec.get("start")),
            "end": str(range_spec.get("end")),
            "start_index": bounded_start,
            "end_index": bounded_end,
            "time_variable": variable,
            "time_confidence": "confirmed",
            "time_units": "unix_seconds",
        }

    @staticmethod
    def _range_response(range_payload: dict[str, Any], *, sample_count: int, preview_end_index: int | None = None) -> dict[str, Any]:
        response = dict(range_payload)
        if preview_end_index is not None:
            response["preview_end_index"] = int(preview_end_index)
        response["sample_count"] = int(sample_count)
        return response

    @staticmethod
    def _timeseries_axis(z: np.lib.npyio.NpzFile, start: int, end: int) -> dict[str, Any]:
        variable = "segment_time_context_unix"
        if variable not in z:
            return {
                "kind": "sample_index",
                "confidence": "confirmed",
                "data": list(range(start, end)),
            }
        data = read_array_range(z[variable], start, end)
        return {
            "kind": "utc",
            "path": variable,
            "confidence": "confirmed",
            "unit": "unix_seconds",
            "data": [format_unix_seconds_utc(float(value)) for value in np.asarray(data, dtype=float).reshape(-1)],
        }

    def _available_dates(self) -> set[str]:
        dates: set[str] = set()
        for family, pattern in [
            ("daily_full", r"daily_full_(\d{8})\.npz$"),
            ("daily_compact", r"daily_compact_(\d{8})\.parquet$"),
            ("manifests", r"manifest_(\d{8})\.json$"),
        ]:
            base = self.root / family
            if not base.exists():
                continue
            rx = re.compile(pattern)
            for path in base.glob("*/*"):
                if path.name.startswith("._") or not path.is_file():
                    continue
                match = rx.match(path.name)
                if match:
                    dates.add(match.group(1))
        return dates

    def _inventory_counts(self) -> dict[str, int]:
        return {
            family: sum(1 for path in (self.root / family).glob("*/*") if path.is_file() and not path.name.startswith("._"))
            if (self.root / family).exists()
            else 0
            for family in ["daily_full", "daily_compact", "quicklook_B", "quicklook_E", "quicklook_POS", "manifests"]
        }

    def _product_paths(self, date8: str) -> dict[str, Path]:
        year = date8[:4]
        return {
            "daily_full": self.root / "daily_full" / year / f"daily_full_{date8}.npz",
            "daily_compact": self.root / "daily_compact" / year / f"daily_compact_{date8}.parquet",
            "quicklook_B": self.root / "quicklook_B" / year / f"B_{date8}.png",
            "quicklook_E": self.root / "quicklook_E" / year / f"E_{date8}.png",
            "quicklook_POS": self.root / "quicklook_POS" / year / f"POS_{date8}.png",
            "manifest": self.root / "manifests" / year / f"manifest_{date8}.json",
            "provenance": self.root / "provenance" / year / f"daily_provenance_{date8}.json",
        }

    def _generated_plot_path(self, name: str) -> Path:
        return self.config.outputs_root / "generated_plots" / self.name / name

    def _missing_daily_full_response(self, date8: str, plot_type: str, path: Path) -> dict[str, Any]:
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plot_type": plot_type,
            "status": "unavailable",
            "reason": "missing processed arrays: daily_full product is required for Web-generated Cluster plots.",
            "missing_products": [{"product": "daily_full", "path": str(path)}],
        }

    def _missing_fields_response(self, date8: str, plot_type: str, required_fields: list[str], available_fields: list[str]) -> dict[str, Any] | None:
        available = set(available_fields)
        missing = [field for field in required_fields if field not in available]
        if not missing:
            return None
        return {
            "datasource": self.name,
            "datasource_type": self.datasource_type,
            "file_id": date8,
            "plot_type": plot_type,
            "status": "unavailable",
            "required_fields": required_fields,
            "missing_fields": missing,
            "reason": "missing field in processed daily_full arrays",
        }

    @staticmethod
    def _validate_date(file_id: str | None) -> str:
        if file_id is None or not re.fullmatch(r"\d{8}", str(file_id)):
            raise ValueError("Cluster file_id must be a YYYYMMDD processed date")
        return str(file_id)

    @staticmethod
    def _safe_manifest_subset(manifest: dict[str, Any]) -> dict[str, Any]:
        keep = [
            "date8",
            "schema_version",
            "selected_segment_id",
            "segment_start_time",
            "segment_end_time",
            "quicklook_window_mode",
            "E_availability_status",
            "E_unavailable_reason",
            "has_E_psd",
            "has_E_band_power",
            "has_BE_ratio",
            "quicklook_naming_policy",
        ]
        return {key: manifest.get(key) for key in keep if key in manifest}

    @staticmethod
    def _time_summary(z: np.lib.npyio.NpzFile) -> dict[str, Any]:
        variable = "segment_time_context_unix"
        if variable not in z:
            return {
                "status": "unavailable",
                "time_variable": variable,
                "time_confidence": "confirmed",
                "reason": "segment_time_context_unix not found in daily_full",
            }
        values = np.asarray(z[variable], dtype=float).reshape(-1)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return {
                "status": "unavailable",
                "time_variable": variable,
                "time_confidence": "confirmed",
                "sample_count": 0,
                "reason": "segment_time_context_unix has no finite samples",
            }
        if finite.size > 1 and np.any(np.diff(finite) < 0):
            return {
                "status": "unparsed",
                "time_variable": variable,
                "time_confidence": "confirmed",
                "sample_count": int(finite.size),
                "reason": "segment_time_context_unix is not monotonic",
            }
        cadence = np.diff(finite) * 1000.0
        return {
            "status": "parsed",
            "time_variable": variable,
            "time_confidence": "confirmed",
            "time_units": "unix_seconds",
            "sample_count": int(finite.size),
            "start": format_unix_seconds_utc(float(finite[0])),
            "end": format_unix_seconds_utc(float(finite[-1])),
            "cadence_ms": cluster_cadence_summary(cadence),
        }

    @staticmethod
    def _quality_summary(z: np.lib.npyio.NpzFile) -> dict[str, Any]:
        variable = "segment_E_quality"
        if variable not in z:
            return {
                "status": "unavailable",
                "flag_variable": variable,
                "flag_confidence": "confirmed",
                "reason": "segment_E_quality not found in daily_full",
            }
        values = np.asarray(z[variable]).reshape(-1)
        if values.size == 0:
            return {
                "status": "unavailable",
                "flag_variable": variable,
                "flag_confidence": "confirmed",
                "sample_count": 0,
                "reason": "segment_E_quality has no samples",
            }
        unique, counts = np.unique(values, return_counts=True)
        return {
            "status": "parsed",
            "flag_variable": variable,
            "flag_confidence": "confirmed",
            "sample_count": int(values.size),
            "distribution": {str(json_safe(value)): int(count) for value, count in zip(unique, counts, strict=True)},
        }

    @staticmethod
    def _variable_unit(key: str) -> str | None:
        if key.startswith("segment_B") or key.startswith("full_day_B") or key.startswith("segment_dB"):
            return "nT"
        if key.startswith("segment_E") or key.startswith("segment_dE") or key.startswith("segment_vxb"):
            return "mV/m"
        if key.endswith("_MLAT") or key.endswith("_MLT") or key.endswith("_L") or key in {"segment_MLAT", "segment_MLT", "segment_L"}:
            return None
        if "time" in key:
            return "unix_seconds"
        return None

    @staticmethod
    def _variable_descriptor(key: str, array: np.ndarray) -> dict[str, Any]:
        data_kind = "dataset"
        unit = None
        components: list[str] = []
        if key.startswith("segment_B") or key.startswith("full_day_B") or key.startswith("segment_dB"):
            if key.endswith("_psd"):
                data_kind = "spectrogram"
            else:
                data_kind = "magnetic_vector" if array.ndim == 2 and array.shape[-1] == 3 else "magnetic"
            unit = "nT"
        if key.startswith("segment_E") or key.startswith("segment_dE") or key.startswith("segment_vxb"):
            if key.endswith("_psd"):
                data_kind = "spectrogram"
            else:
                data_kind = "electric_vector" if array.ndim == 2 and array.shape[-1] == 3 else "electric"
            unit = "mV/m"
        if key in {"segment_L", "segment_MLT", "segment_MLAT", "full_day_L", "full_day_MLT", "full_day_MLAT"}:
            data_kind = "context"
        if key == "segment_frequency_axis":
            data_kind = "frequency_axis"
            unit = "Hz"
        if key.startswith("segment_BE_"):
            data_kind = "be_ratio"
        if array.ndim == 2 and array.shape[-1] == 3:
            components = ["x", "y", "z"]
        return {
            "name": key,
            "label": key,
            "source": "daily_full_npz",
            "data_kind": data_kind,
            "confidence": "confirmed",
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "unit": unit,
            "components": components,
        }


def format_unix_seconds_utc(value: float) -> str:
    dt = datetime.fromtimestamp(value, timezone.utc)
    if dt.microsecond:
        return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_cluster_time_bound_seconds(value: Any, *, field: str) -> float:
    if value is None:
        raise ValueError(f"time range {field} is required")
    if isinstance(value, (int, np.integer, float, np.floating)):
        number = float(value)
        if not np.isfinite(number):
            raise ValueError(f"time range {field} must be finite")
        return number
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
    return dt.timestamp()


def cluster_cadence_summary(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size == 0:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
    }
