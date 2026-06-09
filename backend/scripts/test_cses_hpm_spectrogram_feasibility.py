#!/usr/bin/env python
"""Draft CSES-01 HPM spectrogram feasibility test.

This is an isolated diagnostic script. It does not enable the formal CSES plot
catalog spectrogram, does not alter the Cluster pipeline, and does not modify
or copy raw H5 files.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import matplotlib
import numpy as np
import pandas as pd
from scipy import signal

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402


DEFAULT_OUTDIR = Path("/Volumes/Elements/satellite_data_web/outputs/cses_hpm_spectrogram_feasibility")
DEFAULT_INPUT_ROOT = Path("/Users/foursoils/Downloads/HPM")
PC5_MIN_MHZ = 1.6
PC5_MAX_MHZ = 6.7
PC5_MIN_PERIOD_SEC = 1000.0 / PC5_MIN_MHZ
EARTH_SHADOW_FIELD = "/FLAG_SHW"
MAGNETORQUER_FIELD = "/FLAG_MT"
TBB_FIELD = "/FLAG_TBB"


def json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.reshape(-1).tolist()]
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return str(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def path_name(path: str) -> str:
    return path.strip("/")


def read_h5_dataset(handle: h5py.File, path: str, max_samples: int | None = None) -> tuple[np.ndarray, h5py.Dataset]:
    name = path_name(path)
    if name not in handle:
        raise KeyError(f"H5 dataset {path!r} not found")
    dataset = handle[name]
    if dataset.shape == ():
        data = np.asarray([dataset[()]])
    else:
        n = int(dataset.shape[0])
        stop = n if max_samples is None else min(n, int(max_samples))
        slices = [slice(0, stop)]
        slices.extend(slice(None) for _ in dataset.shape[1:])
        data = np.asarray(dataset[tuple(slices)])
    return data, dataset


def cses_utc_time_text(value: Any) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, np.bytes_):
        text = value.astype(str).item()
    elif isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return ""
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


def parse_one_cses_utc(value: Any) -> float:
    text = cses_utc_time_text(value)
    if len(text) < 17:
        return np.nan
    try:
        dt = datetime(
            int(text[0:4]),
            int(text[4:6]),
            int(text[6:8]),
            int(text[8:10]),
            int(text[10:12]),
            int(text[12:14]),
            int(text[14:17]) * 1000,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return np.nan
    return float(dt.timestamp())


def parse_cses_utc_time(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values).reshape(-1)
    unix_seconds = np.asarray([parse_one_cses_utc(item) for item in arr], dtype=float)
    finite = np.isfinite(unix_seconds)
    iso = [
        pd.Timestamp(value, unit="s", tz="UTC").isoformat() if np.isfinite(value) else None
        for value in unix_seconds
    ]
    return {
        "kind": "compact_YYYYMMDDHHMMSSmmm",
        "confidence": "inferred",
        "success_fraction": float(np.mean(finite)) if unix_seconds.size else 0.0,
        "parsed_count": int(np.count_nonzero(finite)),
        "total_count": int(unix_seconds.size),
        "unix_seconds": unix_seconds,
        "iso": iso,
        "start": iso[int(np.nonzero(finite)[0][0])] if finite.any() else None,
        "end": iso[int(np.nonzero(finite)[0][-1])] if finite.any() else None,
    }


def percentile_summary(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"count": 0}
    pct = np.nanpercentile(arr, [0, 5, 50, 95, 100])
    return {
        "count": int(arr.size),
        "min": float(pct[0]),
        "p05": float(pct[1]),
        "median": float(pct[2]),
        "p95": float(pct[3]),
        "max": float(pct[4]),
    }


def summarize_cadence(unix_seconds: np.ndarray) -> dict[str, Any]:
    time = np.asarray(unix_seconds, dtype=float).reshape(-1)
    finite = np.isfinite(time)
    finite_time = time[finite]
    diffs = np.diff(finite_time)
    positive = diffs[np.isfinite(diffs) & (diffs > 0)]
    diff_summary = percentile_summary(diffs)
    median = float(np.nanmedian(positive)) if positive.size else np.nan
    duplicate_count = int(np.count_nonzero(diffs == 0)) if diffs.size else 0
    large_gap_threshold = 3.0 * median if np.isfinite(median) and median > 0 else np.nan
    large_gap_count = int(np.count_nonzero(diffs > large_gap_threshold)) if np.isfinite(large_gap_threshold) else 0
    monotonic = bool(np.all(diffs > 0)) if diffs.size else False
    p05 = diff_summary.get("p05")
    p95 = diff_summary.get("p95")
    stable = (
        bool(monotonic)
        and duplicate_count == 0
        and large_gap_count == 0
        and np.isfinite(median)
        and median > 0
        and p05 is not None
        and p95 is not None
        and abs(float(p95) - float(p05)) <= max(0.05 * median, 0.1)
    )
    duration = float(finite_time[-1] - finite_time[0]) if finite_time.size >= 2 else 0.0
    return {
        "finite_time_count": int(finite_time.size),
        "duration_seconds": duration,
        "diff_seconds": diff_summary,
        "median_interval_seconds": median if np.isfinite(median) else None,
        "sample_rate_hz": float(1.0 / median) if np.isfinite(median) and median > 0 else None,
        "duplicate_timestamp_count": duplicate_count,
        "large_gap_threshold_seconds": large_gap_threshold if np.isfinite(large_gap_threshold) else None,
        "large_gap_count": large_gap_count,
        "monotonic_increasing": monotonic,
        "stable_for_stft": stable,
    }


def attrs_dict(dataset: h5py.Dataset) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in dataset.attrs.keys():
        value = dataset.attrs[key]
        if isinstance(value, bytes):
            out[str(key)] = value.decode("utf-8", errors="replace")
        elif isinstance(value, np.ndarray):
            out[str(key)] = json_safe(value)
        elif isinstance(value, np.generic):
            out[str(key)] = json_safe(value)
        else:
            out[str(key)] = value
    return json_safe(out)


def attr_value(attrs: dict[str, Any], *names: str) -> Any:
    lower = {str(key).lower(): value for key, value in attrs.items()}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def possible_fill_values(dataset: h5py.Dataset, attrs: dict[str, Any]) -> list[float]:
    values: list[Any] = []
    for key in ("FillValue", "_FillValue", "fill_value", "missing_value"):
        value = attr_value(attrs, key)
        if value is not None:
            values.append(value)
    if dataset.fillvalue is not None:
        values.append(dataset.fillvalue)
    out: list[float] = []
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            try:
                number = float(item)
            except (TypeError, ValueError):
                continue
            if not any(np.isclose(number, old, equal_nan=True) for old in out):
                out.append(number)
    return out


def count_fill_values(data: np.ndarray, fill_values: list[float]) -> dict[str, int]:
    if not fill_values:
        return {}
    arr = np.asarray(data, dtype=float).reshape(-1)
    out = {}
    for fill in fill_values:
        if np.isnan(fill):
            count = int(np.count_nonzero(np.isnan(arr)))
        else:
            count = int(np.count_nonzero(np.isclose(arr, fill, equal_nan=False)))
        out[str(fill)] = count
    return out


def summarize_magnetic(data: np.ndarray, dataset: h5py.Dataset, time_count: int) -> dict[str, Any]:
    attrs = attrs_dict(dataset)
    values = np.asarray(data)
    numeric = np.issubdtype(values.dtype, np.number)
    fill_values = possible_fill_values(dataset, attrs)
    if values.ndim == 2 and values.shape[1] >= 3 and numeric:
        b = values[:, :3].astype(float)
    else:
        b = np.empty((0, 3), dtype=float)
    finite_fraction = float(np.isfinite(b).mean()) if b.size else 0.0
    nan_count = int(np.count_nonzero(np.isnan(b))) if b.size else 0
    b_abs = np.linalg.norm(b, axis=1) if b.size else np.asarray([])
    unit = attr_value(attrs, "Units", "units", "UNIT", "unit")
    return {
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "numeric_dtype": bool(numeric),
        "unit": unit,
        "unit_is_nt": bool(str(unit).lower() == "nt"),
        "length_matches_time": bool(values.shape[0] == time_count) if values.ndim >= 1 else False,
        "finite_fraction": finite_fraction,
        "nan_count": nan_count,
        "fill_values": fill_values,
        "fill_value_counts": count_fill_values(b, fill_values),
        "component_ranges": [percentile_summary(b[:, index]) for index in range(3)] if b.size else [],
        "b_abs_range": percentile_summary(b_abs) if b_abs.size else {"count": 0},
        "data": b,
        "b_abs": b_abs,
        "attrs": attrs,
    }


def summarize_flag(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values).reshape(-1)
    finite = arr[np.isfinite(arr)] if np.issubdtype(arr.dtype, np.number) else arr
    unique, counts = np.unique(finite, return_counts=True)
    total = int(np.sum(counts))
    return {
        "total_count": total,
        "distribution": [
            {"value": json_safe(value), "count": int(count), "fraction": float(count / total) if total else 0.0}
            for value, count in zip(unique.tolist(), counts.tolist())
        ],
    }


def choose_stft_params(sample_count: int, sample_rate_hz: float, freq_min_mhz: float) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if sample_count < 16 or sample_rate_hz <= 0:
        return {"nperseg": 0, "noverlap": 0, "frequency_resolution_mhz": None}, ["not enough samples for STFT"]
    lowest_period = 1000.0 / float(freq_min_mhz)
    target_seconds = 4.0 * lowest_period
    target_samples = int(math.ceil(target_seconds * sample_rate_hz))
    nperseg = min(sample_count, max(64, target_samples))
    if nperseg > sample_count:
        nperseg = sample_count
    if nperseg == sample_count and sample_count < target_samples:
        warnings.append(
            f"single file is shorter than 4 periods of the lowest requested frequency ({freq_min_mhz:.3g} mHz); STFT low-frequency resolution is limited"
        )
    if nperseg >= 32:
        nperseg = 2 ** int(math.floor(math.log2(nperseg)))
    nperseg = max(8, min(sample_count, nperseg))
    noverlap = int(nperseg // 2)
    resolution_mhz = float(sample_rate_hz / nperseg * 1000.0)
    return {
        "nperseg": int(nperseg),
        "noverlap": int(noverlap),
        "frequency_resolution_mhz": resolution_mhz,
        "target_window_seconds": target_seconds,
        "actual_window_seconds": float(nperseg / sample_rate_hz),
    }, warnings


def pc5_duration_warnings(duration_seconds: float) -> list[str]:
    warnings: list[str] = []
    periods = duration_seconds / PC5_MIN_PERIOD_SEC if PC5_MIN_PERIOD_SEC else 0.0
    if periods < 4:
        warnings.append(
            f"duration covers only {periods:.2f} cycles at 1.6 mHz; single-file Pc5 interpretation is limited"
        )
    if duration_seconds < 3600:
        warnings.append(
            "single-file Pc5 interpretation is weak for this low-frequency band; stitching adjacent H5 files should be evaluated"
        )
    return warnings


def rolling_mean_detrend(data: np.ndarray, sample_rate_hz: float, window_sec: float) -> tuple[np.ndarray, np.ndarray]:
    window = max(3, int(round(window_sec * sample_rate_hz)))
    if window % 2 == 0:
        window += 1
    frame = pd.DataFrame(np.asarray(data, dtype=float))
    background = frame.rolling(window=window, center=True, min_periods=max(3, window // 4)).mean()
    background = background.bfill().ffill()
    bg = background.to_numpy(dtype=float)
    return np.asarray(data, dtype=float) - bg, bg


def polynomial_detrend(data: np.ndarray, order: int = 3) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(data, dtype=float)
    x = np.arange(y.shape[0], dtype=float)
    bg = np.empty_like(y)
    for col in range(y.shape[1]):
        finite = np.isfinite(y[:, col])
        if finite.sum() <= order + 2:
            bg[:, col] = np.nanmedian(y[:, col])
            continue
        coeff = np.polyfit(x[finite], y[finite, col], deg=min(order, finite.sum() - 2))
        bg[:, col] = np.polyval(coeff, x)
    return y - bg, bg


def apply_detrend(data: np.ndarray, method: str, sample_rate_hz: float, rolling_window_sec: float) -> tuple[np.ndarray, np.ndarray]:
    if method == "none":
        zeros = np.zeros_like(np.asarray(data, dtype=float))
        return np.asarray(data, dtype=float), zeros
    if method == "rolling_mean":
        return rolling_mean_detrend(data, sample_rate_hz, rolling_window_sec)
    if method == "polynomial":
        return polynomial_detrend(data)
    raise ValueError(f"unsupported detrend method: {method}")


def mask_interference(data: np.ndarray, flag_mt: np.ndarray | None) -> np.ndarray:
    out = np.asarray(data, dtype=float).copy()
    if flag_mt is None:
        return out
    flags = np.asarray(flag_mt).reshape(-1)
    n = min(len(flags), out.shape[0])
    out[:n][flags[:n] == 1] = np.nan
    return out


def fill_nan_for_stft(series: np.ndarray) -> np.ndarray:
    values = np.asarray(series, dtype=float).reshape(-1)
    frame = pd.Series(values)
    frame = frame.interpolate(limit_direction="both").bfill().ffill()
    return frame.to_numpy(dtype=float)


def compute_stft(series: np.ndarray, sample_rate_hz: float, nperseg: int, noverlap: int) -> dict[str, Any]:
    clean = fill_nan_for_stft(series)
    freq_hz, time_offsets, zxx = signal.stft(
        clean,
        fs=sample_rate_hz,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend=False,
        boundary=None,
        padded=False,
    )
    psd = np.abs(zxx) ** 2
    return {
        "frequency_mhz": freq_hz * 1000.0,
        "time_offsets_seconds": time_offsets,
        "power": psd,
    }


def datetime_axis(unix_seconds: np.ndarray) -> np.ndarray:
    return np.asarray([datetime.fromtimestamp(float(t), tz=timezone.utc).replace(tzinfo=None) for t in unix_seconds])


def bin_edges_from_centers(centers: np.ndarray) -> np.ndarray:
    values = np.asarray(centers, dtype=float).reshape(-1)
    if values.size == 0:
        return values
    if values.size == 1:
        half_width = abs(float(values[0])) if values[0] != 0 else 0.5
        return np.asarray([values[0] - half_width, values[0] + half_width], dtype=float)
    mids = (values[:-1] + values[1:]) / 2.0
    first = values[0] - (mids[0] - values[0])
    last = values[-1] + (values[-1] - mids[-1])
    return np.concatenate([[first], mids, [last]]).astype(float)


def stft_time_edges_seconds(offsets: np.ndarray) -> np.ndarray:
    edges = bin_edges_from_centers(offsets)
    if edges.size == 2 and edges[0] < 0 <= np.asarray(offsets, dtype=float).reshape(-1)[0]:
        edges = edges - edges[0]
    return edges


def frequency_edges_mhz(freq_mhz: np.ndarray) -> np.ndarray:
    edges = bin_edges_from_centers(freq_mhz)
    if edges.size:
        edges[0] = max(0.0, edges[0])
    return edges


def component_names(component: str) -> list[str]:
    if component == "all":
        return ["B1", "B2", "B3"]
    return [component]


def component_series(name: str, b: np.ndarray, b_abs: np.ndarray) -> np.ndarray:
    if name == "B1":
        return b[:, 0]
    if name == "B2":
        return b[:, 1]
    if name == "B3":
        return b[:, 2]
    if name == "Babs":
        return b_abs
    raise ValueError(f"unknown component: {name}")


def plot_time_cadence(path: Path, times: np.ndarray, cadence: dict[str, Any], flag_mt: np.ndarray | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dt = datetime_axis(times)
    diffs = np.diff(times)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), dpi=150, constrained_layout=True)
    if diffs.size:
        axes[0].plot(dt[1:], diffs, lw=0.8, color="#2563eb")
        axes[0].axhline(cadence["diff_seconds"].get("median", np.nan), color="#111827", ls="--", lw=1.0, label="median")
        axes[0].legend(loc="best")
    if flag_mt is not None:
        flags = np.asarray(flag_mt).reshape(-1)
        n = min(len(flags), len(dt))
        bad = flags[:n] == 1
        if np.any(bad):
            axes[0].scatter(np.asarray(dt[:n])[bad], np.full(np.count_nonzero(bad), np.nanmax(diffs) if diffs.size else 1.0), s=8, color="#dc2626", label="FLAG_MT=1")
    axes[0].set_title("CSES HPM time cadence diagnostic (inferred UTC_TIME)")
    axes[0].set_ylabel("Delta t (s)")
    axes[0].grid(True, alpha=0.25)
    finite_diffs = diffs[np.isfinite(diffs)]
    if finite_diffs.size:
        axes[1].hist(finite_diffs, bins=60, color="#475569", alpha=0.85)
    axes[1].set_xlabel("Delta t (s)")
    axes[1].set_ylabel("Count")
    axes[1].grid(True, alpha=0.25)
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.savefig(path)
    plt.close(fig)


def plot_magnetic_timeseries(path: Path, times: np.ndarray, b: np.ndarray, title: str, ylabel: str, flag_mt: np.ndarray | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dt = datetime_axis(times)
    b_abs = np.linalg.norm(b, axis=1)
    fig, ax = plt.subplots(figsize=(12, 5.8), dpi=150, constrained_layout=True)
    for index, label in enumerate(["B1", "B2", "B3"]):
        ax.plot(dt, b[:, index], lw=0.8, label=label)
    ax.plot(dt, b_abs, lw=1.0, color="#111827", label="|B|")
    if flag_mt is not None:
        flags = np.asarray(flag_mt).reshape(-1)
        n = min(len(flags), len(dt))
        bad = flags[:n] == 1
        if np.any(bad):
            ymin, ymax = ax.get_ylim()
            ax.scatter(np.asarray(dt[:n])[bad], np.full(np.count_nonzero(bad), ymax), s=10, color="#dc2626", label="FLAG_MT=1")
            ax.set_ylim(ymin, ymax)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("UTC")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=5, fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.savefig(path)
    plt.close(fig)


def plot_spectrogram(
    path: Path,
    stft_result: dict[str, Any],
    base_start_unix: float,
    freq_min_mhz: float,
    freq_max_mhz: float,
    title: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    freq = np.asarray(stft_result["frequency_mhz"], dtype=float)
    offsets = np.asarray(stft_result["time_offsets_seconds"], dtype=float)
    power = np.asarray(stft_result["power"], dtype=float)
    mask = (freq >= freq_min_mhz) & (freq <= freq_max_mhz)
    freq_plot = freq[mask]
    power_plot = power[mask, :]
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150, constrained_layout=True)
    if freq_plot.size == 0 or offsets.size == 0 or power_plot.size == 0:
        ax.text(0.5, 0.5, "No STFT bins in requested frequency range", ha="center", va="center", transform=ax.transAxes)
        ax.set_title(title)
        fig.savefig(path)
        plt.close(fig)
        return
    floor = np.nanpercentile(power_plot[np.isfinite(power_plot) & (power_plot > 0)], 2) if np.any(power_plot > 0) else 1e-12
    ceiling = np.nanpercentile(power_plot[np.isfinite(power_plot) & (power_plot > 0)], 98) if np.any(power_plot > 0) else 1.0
    dt_edges = datetime_axis(base_start_unix + stft_time_edges_seconds(offsets))
    freq_edges = frequency_edges_mhz(freq_plot)
    mesh = ax.pcolormesh(
        dt_edges,
        freq_edges,
        np.maximum(power_plot, floor),
        shading="auto",
        norm=LogNorm(vmin=max(floor, np.finfo(float).tiny), vmax=max(ceiling, floor * 10)),
        cmap="viridis",
    )
    if offsets.size == 1:
        ax.text(
            0.01,
            0.98,
            "single STFT time window",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8,
            bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none", "pad": 3},
        )
    ax.axhspan(PC5_MIN_MHZ, PC5_MAX_MHZ, color="white", alpha=0.13, label="Pc5 1.6-6.7 mHz")
    ax.set_ylim(freq_min_mhz, freq_max_mhz)
    ax.set_title(title)
    ax.set_ylabel("Frequency (mHz)")
    ax.set_xlabel("UTC")
    ax.grid(True, alpha=0.18)
    ax.legend(loc="upper right", fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.colorbar(mesh, ax=ax, label="diagnostic STFT power")
    fig.savefig(path)
    plt.close(fig)


def plot_overview(
    path: Path,
    stfts: dict[str, dict[str, Any]],
    base_start_unix: float,
    freq_min_mhz: float,
    freq_max_mhz: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = [name for name in ("B1", "B2", "B3") if name in stfts]
    if not names:
        return
    fig, axes = plt.subplots(len(names), 1, figsize=(12, 3.8 * len(names)), dpi=150, sharex=True, constrained_layout=True)
    if len(names) == 1:
        axes = [axes]
    for ax, name in zip(axes, names):
        result = stfts[name]
        freq = np.asarray(result["frequency_mhz"], dtype=float)
        offsets = np.asarray(result["time_offsets_seconds"], dtype=float)
        power = np.asarray(result["power"], dtype=float)
        mask = (freq >= freq_min_mhz) & (freq <= freq_max_mhz)
        freq_plot = freq[mask]
        power_plot = power[mask, :]
        if freq_plot.size == 0 or offsets.size == 0 or power_plot.size == 0:
            ax.text(0.5, 0.5, "No STFT bins in requested frequency range", ha="center", va="center", transform=ax.transAxes)
            ax.set_ylabel(f"{name}\nFrequency (mHz)")
            continue
        positive = power_plot[np.isfinite(power_plot) & (power_plot > 0)]
        floor = np.nanpercentile(positive, 2) if positive.size else 1e-12
        ceiling = np.nanpercentile(positive, 98) if positive.size else 1.0
        dt_edges = datetime_axis(base_start_unix + stft_time_edges_seconds(offsets))
        freq_edges = frequency_edges_mhz(freq_plot)
        mesh = ax.pcolormesh(
            dt_edges,
            freq_edges,
            np.maximum(power_plot, floor),
            shading="auto",
            norm=LogNorm(vmin=max(floor, np.finfo(float).tiny), vmax=max(ceiling, floor * 10)),
            cmap="viridis",
        )
        if offsets.size == 1:
            ax.text(
                0.01,
                0.96,
                "single STFT time window",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none", "pad": 3},
            )
        ax.axhspan(PC5_MIN_MHZ, PC5_MAX_MHZ, color="white", alpha=0.13)
        ax.set_ylim(freq_min_mhz, freq_max_mhz)
        ax.set_ylabel(f"{name}\nFrequency (mHz)")
        ax.grid(True, alpha=0.18)
        fig.colorbar(mesh, ax=ax, label="power")
    axes[0].set_title("CSES HPM diagnostic STFT spectrogram overview (detrended dB)")
    axes[-1].set_xlabel("UTC")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.savefig(path)
    plt.close(fig)


def feasibility_checks(time_summary: dict[str, Any], magnetic_summary: dict[str, Any]) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    ok = True
    if time_summary["parse"]["success_fraction"] < 0.99:
        ok = False
        warnings.append("time field parse success fraction is below 0.99")
    cadence = time_summary["cadence"]
    if not cadence["stable_for_stft"]:
        ok = False
        warnings.append("sampling cadence is not stable enough for this single-file STFT gate")
    if not magnetic_summary["length_matches_time"]:
        ok = False
        warnings.append("magnetic sample length does not match time sample length")
    if not magnetic_summary["numeric_dtype"] or magnetic_summary["shape"][1:] != [3]:
        ok = False
        warnings.append("magnetic field is not a numeric [N,3] dataset")
    if magnetic_summary["finite_fraction"] < 0.95:
        ok = False
        warnings.append("magnetic finite fraction is below 0.95")
    return ok, warnings


def stft_time_bin_warnings(stft_outputs: dict[str, Any]) -> list[str]:
    single_bin = [
        name
        for name, info in stft_outputs.items()
        if int(info.get("time_bin_count", 0)) == 1
    ]
    if not single_bin:
        return []
    return [
        "STFT produced only 1 time bin for "
        + ", ".join(single_bin)
        + "; this is a windowed spectral diagnostic over the file, not resolved time-frequency evolution"
    ]


def write_report(summary: dict[str, Any], outdir: Path) -> None:
    lines: list[str] = []
    lines.append("# CSES HPM Spectrogram Feasibility Report")
    lines.append("")
    lines.append("This is a diagnostic spectrogram feasibility test, not formal CSES Pc5 science processing.")
    lines.append("")
    lines.append("## Direct Answers")
    lines.append("")
    lines.append(f"- Can this H5 produce a technical spectrogram? {'Yes, as a diagnostic STFT spectrogram.' if summary['spectrogram']['computed'] else 'No, prerequisite checks failed.'}")
    if summary["spectrogram"].get("computed") and not summary["spectrogram"].get("time_frequency_evolution_resolved"):
        lines.append("- In this run, STFT has only one time window at the low-frequency-oriented setting, so the output is closer to a single-window spectral diagnostic than a resolved spectrogram.")
    lines.append(f"- Can it support Pc5-band plots? {'Technically yes, but diagnostic only.' if summary['pc5']['technical_pc5_plot_possible'] else 'Not reliably from this single file.'}")
    lines.append("- Scientific usability: diagnostic only; inferred time semantics and product-document confirmation are still required.")
    lines.append(f"- Recommend enabling `cses_hpm_spectrogram_overview`: {'yes' if summary['recommend_enable_catalog'] else 'no'}")
    lines.append("")
    lines.append("## Confirmed From File Readback")
    lines.append("")
    lines.append(f"- Input file: `{summary['input_file']}`")
    lines.append(f"- Time field: `{summary['time_field']}` parse success {summary['time']['parse']['success_fraction']:.3f}")
    lines.append(f"- Time span: {summary['time']['parse']['start']} to {summary['time']['parse']['end']}")
    lines.append(f"- Duration: {summary['time']['cadence']['duration_seconds']:.1f} s")
    lines.append(f"- Cadence median: {summary['time']['cadence']['median_interval_seconds']} s")
    lines.append(f"- Magnetic field: `{summary['magnetic_field']}` shape {summary['magnetic']['shape']} dtype {summary['magnetic']['dtype']} unit {summary['magnetic']['unit']}")
    lines.append(f"- Magnetic finite fraction: {summary['magnetic']['finite_fraction']:.6f}")
    lines.append(f"- Quality flags: {', '.join(summary['quality_flags'].keys())}")
    lines.append("")
    lines.append("## Inferred")
    lines.append("")
    lines.append("- `/UTC_TIME` is treated as compact `YYYYMMDDHHMMSSmmm` based on prior inspector behavior and local parser compatibility; this remains inferred time semantics.")
    lines.append("- `/B_FGM` is treated as a three-component magnetic candidate in nT for this feasibility test; coordinate frame and component semantics require product-document confirmation.")
    lines.append("- Raw B includes main field and orbital-scale variation. Detrended `dB = B - rolling_mean(B)` is used for diagnostic STFT.")
    lines.append("")
    lines.append("## Quality Flags")
    lines.append("")
    for path, info in summary["quality_flags"].items():
        lines.append(f"- `{path}` distribution: `{json.dumps(info['distribution'], ensure_ascii=False)}`")
    lines.append("- `FLAG_MT=1` is treated as magnetorquer interference for diagnostic masking. Unfiltered and masked STFT feasibility outputs are recorded; `FLAG_SHW` and `FLAG_TBB` are reported as status fields only.")
    lines.append("")
    lines.append("## Cluster Reference Logic")
    lines.append("")
    lines.append("- Cluster web spectrograms read existing `daily_full` PSD arrays such as `segment_dB_phi_psd`, `segment_dE_phi_psd`, `segment_frequency_axis`, and `segment_time_wavelet_unix`; they do not recompute wavelets in the web runtime.")
    lines.append("- Cluster narrowband/event code samples existing wavelet/PSD products at stored time/frequency bins and keeps MFA/L/MLT/MLAT context separate.")
    lines.append("- For CSES HPM, those Cluster-specific MFA, electric-field, B/E, L/MLT/MLAT, and modal-classification assumptions cannot be copied.")
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    if summary["warnings"]:
        for warning in summary["warnings"]:
            lines.append(f"- {warning}")
    else:
        lines.append("- No warnings recorded.")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    for item in summary["outputs"]:
        rel = Path(item).relative_to(outdir)
        if rel.suffix.lower() == ".png":
            lines.append(f"- ![]({rel.as_posix()})")
        else:
            lines.append(f"- `{rel.as_posix()}`")
    lines.append("")
    lines.append("## Next Conditions Before Frontend Catalog Enablement")
    lines.append("")
    lines.append("- Confirm CSES `/UTC_TIME` semantics, leap-second/epoch policy, and product cadence from official product documentation.")
    lines.append("- Confirm `/B_FGM` component order, coordinate frame, units, fill values, and calibration status.")
    lines.append("- Define quality masking policy for `FLAG_MT`, `FLAG_SHW`, `FLAG_TBB`, and any other status fields.")
    lines.append("- Evaluate multi-file stitching across adjacent H5 files for robust low-frequency Pc5 coverage.")
    lines.append("- Decide whether the frontend should show this as diagnostic-only, separate from formal Cluster spectrograms.")
    (outdir / "CSES_HPM_SPECTROGRAM_FEASIBILITY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def inspect_and_compute(args: argparse.Namespace) -> dict[str, Any]:
    input_file = choose_input_file(args)
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    outputs: list[str] = []
    with h5py.File(input_file, "r") as h5:
        time_raw, time_ds = read_h5_dataset(h5, args.time_field, args.max_samples)
        time_parse = parse_cses_utc_time(time_raw)
        if time_parse["success_fraction"] < 0.99:
            summary = failure_summary(input_file, args, time_parse, "time_parse_failed")
            summary["warnings"].append("time field cannot be parsed well enough; frequency analysis stopped")
            write_failure_outputs(summary, outdir)
            return summary
        unix_seconds = np.asarray(time_parse["unix_seconds"], dtype=float)
        cadence = summarize_cadence(unix_seconds)
        time_summary = {"field": args.time_field, "attrs": attrs_dict(time_ds), "parse": compact_time_summary(time_parse), "cadence": cadence}

        mag_raw, mag_ds = read_h5_dataset(h5, args.mag_field, args.max_samples)
        magnetic = summarize_magnetic(mag_raw, mag_ds, time_parse["total_count"])
        b = magnetic.pop("data")
        b_abs = magnetic.pop("b_abs")

        flag_arrays: dict[str, np.ndarray] = {}
        quality_flags: dict[str, Any] = {}
        for flag_path in (MAGNETORQUER_FIELD, EARTH_SHADOW_FIELD, TBB_FIELD):
            try:
                flag_data, _ = read_h5_dataset(h5, flag_path, args.max_samples)
                flag_arrays[flag_path] = flag_data.reshape(-1)
                quality_flags[flag_path] = summarize_flag(flag_data)
            except Exception as exc:
                quality_flags[flag_path] = {"status": "missing_or_unreadable", "error": repr(exc), "distribution": []}

    ok, check_warnings = feasibility_checks(time_summary, magnetic)
    warnings.extend(check_warnings)
    warnings.extend(pc5_duration_warnings(cadence["duration_seconds"]))
    sample_rate = cadence["sample_rate_hz"] or 0.0
    stft_params, stft_warnings = choose_stft_params(b.shape[0], sample_rate, args.freq_min_mhz)
    warnings.extend(stft_warnings)
    pc5_technical = bool(ok and stft_params["nperseg"] > 0 and cadence["duration_seconds"] >= 2 * PC5_MIN_PERIOD_SEC)

    plot_time_cadence(outdir / "time_cadence_diagnostic.png", unix_seconds, cadence, flag_arrays.get(MAGNETORQUER_FIELD))
    outputs.append(str(outdir / "time_cadence_diagnostic.png"))
    plot_magnetic_timeseries(outdir / "magnetic_raw_timeseries.png", unix_seconds, b, "CSES HPM raw magnetic candidate (diagnostic)", "nT", flag_arrays.get(MAGNETORQUER_FIELD))
    outputs.append(str(outdir / "magnetic_raw_timeseries.png"))

    d_b, background = apply_detrend(b, args.detrend, sample_rate, args.rolling_window_sec)
    del background
    plot_magnetic_timeseries(outdir / "magnetic_detrended_timeseries.png", unix_seconds, d_b, f"CSES HPM detrended dB ({args.detrend}, diagnostic)", "dB (nT)", flag_arrays.get(MAGNETORQUER_FIELD))
    outputs.append(str(outdir / "magnetic_detrended_timeseries.png"))

    stft_outputs: dict[str, Any] = {}
    masked_stft_outputs: dict[str, Any] = {}
    if ok and args.method == "stft" and stft_params["nperseg"] > 0:
        names = component_names(args.component)
        for name in names:
            series = component_series(name, d_b, np.linalg.norm(d_b, axis=1))
            result = compute_stft(series, sample_rate, stft_params["nperseg"], stft_params["noverlap"])
            stft_outputs[name] = summarize_stft_result(result)
            plot_path = outdir / f"cses_hpm_stft_spectrogram_{name}.png"
            plot_spectrogram(plot_path, result, unix_seconds[0], args.freq_min_mhz, args.freq_max_mhz, f"CSES HPM diagnostic STFT {name} detrended dB")
            outputs.append(str(plot_path))

            masked_series = component_series(name, mask_interference(d_b, flag_arrays.get(MAGNETORQUER_FIELD)), np.linalg.norm(mask_interference(d_b, flag_arrays.get(MAGNETORQUER_FIELD)), axis=1))
            masked = compute_stft(masked_series, sample_rate, stft_params["nperseg"], stft_params["noverlap"])
            masked_stft_outputs[name] = summarize_stft_result(masked)
            masked_path = outdir / f"cses_hpm_stft_spectrogram_{name}_FLAG_MT_masked.png"
            plot_spectrogram(masked_path, masked, unix_seconds[0], args.freq_min_mhz, args.freq_max_mhz, f"CSES HPM diagnostic STFT {name} detrended dB, FLAG_MT masked")
            outputs.append(str(masked_path))

        if args.component == "all":
            overview_results = {
                name: compute_stft(component_series(name, d_b, np.linalg.norm(d_b, axis=1)), sample_rate, stft_params["nperseg"], stft_params["noverlap"])
                for name in ("B1", "B2", "B3")
            }
            overview = outdir / "cses_hpm_spectrogram_overview.png"
            plot_overview(overview, overview_results, unix_seconds[0], args.freq_min_mhz, args.freq_max_mhz)
            outputs.append(str(overview))

    warnings.extend(stft_time_bin_warnings(stft_outputs))
    time_frequency_evolution_resolved = bool(
        stft_outputs and all(int(info.get("time_bin_count", 0)) >= 2 for info in stft_outputs.values())
    )

    if args.method != "stft":
        warnings.append("wavelet method is not implemented in this feasibility script; only STFT was computed when requested")

    summary = {
        "status": "completed",
        "test_type": "cses_hpm_spectrogram_feasibility",
        "input_file": str(input_file),
        "time_field": args.time_field,
        "magnetic_field": args.mag_field,
        "component": args.component,
        "sample_count": int(b.shape[0]),
        "time": time_summary,
        "magnetic": magnetic,
        "quality_flags": quality_flags,
        "detrend": {"method": args.detrend, "rolling_window_sec": args.rolling_window_sec},
        "spectrogram": {
            "method": args.method,
            "computed": bool(ok and args.method == "stft" and bool(stft_outputs)),
            "frequency_range_mhz": [args.freq_min_mhz, args.freq_max_mhz],
            "stft_params": stft_params,
            "components": stft_outputs,
            "flag_mt_masked_components": masked_stft_outputs,
            "time_frequency_evolution_resolved": time_frequency_evolution_resolved,
        },
        "pc5": {
            "band_mhz": [PC5_MIN_MHZ, PC5_MAX_MHZ],
            "minimum_period_seconds": PC5_MIN_PERIOD_SEC,
            "duration_lowest_period_count": cadence["duration_seconds"] / PC5_MIN_PERIOD_SEC,
            "technical_pc5_plot_possible": pc5_technical,
            "scientific_pc5_ready": False,
        },
        "minimum_conditions": {"passed": ok, "warnings": check_warnings},
        "warnings": warnings,
        "outputs": outputs + [str(outdir / "summary.json"), str(outdir / "CSES_HPM_SPECTROGRAM_FEASIBILITY_REPORT.md")],
        "recommend_enable_catalog": False,
        "cluster_reference": cluster_reference_summary(),
    }
    write_json(outdir / "summary.json", summary)
    write_report(summary, outdir)
    return summary


def compact_time_summary(time_parse: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": time_parse["kind"],
        "confidence": time_parse["confidence"],
        "success_fraction": time_parse["success_fraction"],
        "parsed_count": time_parse["parsed_count"],
        "total_count": time_parse["total_count"],
        "start": time_parse["start"],
        "end": time_parse["end"],
    }


def summarize_stft_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "frequency_count": int(np.asarray(result["frequency_mhz"]).size),
        "time_bin_count": int(np.asarray(result["time_offsets_seconds"]).size),
        "frequency_mhz_min": float(np.nanmin(result["frequency_mhz"])) if np.asarray(result["frequency_mhz"]).size else None,
        "frequency_mhz_max": float(np.nanmax(result["frequency_mhz"])) if np.asarray(result["frequency_mhz"]).size else None,
    }


def cluster_reference_summary() -> dict[str, Any]:
    return {
        "usable_reference": [
            "validate time/cadence before spectrogram",
            "plot PSD with explicit time and frequency axes",
            "keep generated web artifacts under the web outputs tree",
            "read frozen Cluster PSD arrays rather than rerunning production in the web runtime",
        ],
        "not_directly_reusable": [
            "MFA/toroidal/poloidal/compressional component semantics",
            "electric-field and B/E ratio logic",
            "Cluster L/MLT/MLAT context",
            "Cluster event and modal classification pipeline",
        ],
    }


def failure_summary(input_file: Path, args: argparse.Namespace, time_parse: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "reason": reason,
        "test_type": "cses_hpm_spectrogram_feasibility",
        "input_file": str(input_file),
        "time_field": args.time_field,
        "magnetic_field": args.mag_field,
        "time": {"parse": compact_time_summary(time_parse)},
        "spectrogram": {"computed": False, "method": args.method},
        "warnings": [],
        "outputs": [],
        "recommend_enable_catalog": False,
    }


def write_failure_outputs(summary: dict[str, Any], outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    summary["outputs"] = [str(outdir / "summary.json"), str(outdir / "CSES_HPM_SPECTROGRAM_FEASIBILITY_REPORT.md")]
    write_json(outdir / "summary.json", summary)
    write_report(summary, outdir)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def choose_input_file(args: argparse.Namespace) -> Path:
    if args.input_file:
        return Path(args.input_file).expanduser().resolve()
    root = Path(args.input_root or DEFAULT_INPUT_ROOT).expanduser().resolve()
    files = sorted([item for item in root.iterdir() if item.suffix.lower() in {".h5", ".hdf5"}])
    if not files:
        raise FileNotFoundError(f"no H5 files found under {root}")
    return files[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSES HPM spectrogram feasibility test")
    parser.add_argument("--input-file", type=Path, default=None)
    parser.add_argument("--input-root", type=Path, default=None)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--time-field", default="/UTC_TIME")
    parser.add_argument("--mag-field", default="/B_FGM")
    parser.add_argument("--component", choices=["B1", "B2", "B3", "Babs", "all"], default="all")
    parser.add_argument("--freq-min-mhz", type=float, default=1.0)
    parser.add_argument("--freq-max-mhz", type=float, default=100.0)
    parser.add_argument("--method", choices=["stft", "wavelet"], default="stft")
    parser.add_argument("--detrend", choices=["none", "rolling_mean", "polynomial"], default="rolling_mean")
    parser.add_argument("--rolling-window-sec", type=float, default=600.0)
    parser.add_argument("--max-samples", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = inspect_and_compute(args)
    print("CSES HPM spectrogram feasibility complete")
    print(f"input_file: {summary['input_file']}")
    print(f"status: {summary['status']}")
    print(f"spectrogram_computed: {summary.get('spectrogram', {}).get('computed')}")
    print(f"recommend_enable_catalog: {summary.get('recommend_enable_catalog')}")
    print(f"warnings: {len(summary.get('warnings', []))}")
    print(f"outdir: {Path(args.outdir).expanduser().resolve()}")
    return 0 if summary["status"] in {"completed", "failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
