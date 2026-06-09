from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_magnetic_timeseries(path: Path, *, x: np.ndarray, b: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(b, dtype=float)
    if data.ndim != 2 or data.shape[1] != 3:
        raise ValueError("magnetic_timeseries requires a 3-component vector dataset")
    axis = _x_axis(x, data.shape[0])
    magnitude = np.linalg.norm(data, axis=1)
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=140)
    for index, label in enumerate(["Bx", "By", "Bz"]):
        ax.plot(axis, data[:, index], linewidth=1.2, label=label)
    ax.plot(axis, magnitude, linewidth=1.4, label="|B|", color="#111827")
    ax.set_title(title)
    ax.set_xlabel("Sample" if x.size == 0 else "Time/sample value")
    ax.set_ylabel("Magnetic field")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_electric_timeseries(path: Path, *, x: np.ndarray, e: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(e, dtype=float)
    if data.ndim != 2 or data.shape[1] != 3:
        raise ValueError("electric_timeseries requires a 3-component vector dataset")
    axis = _x_axis(x, data.shape[0])
    magnitude = np.linalg.norm(data, axis=1)
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=140)
    for index, label in enumerate(["Ex", "Ey", "Ez"]):
        ax.plot(axis, data[:, index], linewidth=1.2, label=label)
    ax.plot(axis, magnitude, linewidth=1.4, label="|E|", color="#111827")
    ax.set_title(title)
    ax.set_xlabel("Sample" if x.size == 0 else "Time/sample value")
    ax.set_ylabel("Electric field")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_scalar_timeseries(path: Path, *, x: np.ndarray, y: np.ndarray, variable: str, unit: str | None, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(y, dtype=float)
    if data.ndim == 2 and data.shape[1] == 1:
        data = data.reshape(-1)
    elif data.ndim != 1:
        raise ValueError("scalar_timeseries requires a one-dimensional or single-column numeric dataset")
    axis = _x_axis(x, data.shape[0])
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=140)
    ax.plot(axis, data, linewidth=1.3, color="#2563eb")
    ax.set_title(title)
    ax.set_xlabel("Sample" if x.size == 0 else "Time/sample value")
    ax.set_ylabel(f"{variable}{f' ({unit})' if unit else ''}")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_trajectory_2d(path: Path, *, lat: np.ndarray, lon: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lat1 = np.asarray(lat, dtype=float).reshape(-1)
    lon1 = np.asarray(lon, dtype=float).reshape(-1)
    fig, ax = plt.subplots(figsize=(6.8, 5), dpi=140)
    ax.plot(lon1, lat1, linewidth=1.4, marker=".", markersize=4)
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_trajectory_3d(path: Path, *, lat: np.ndarray, lon: np.ndarray, alt: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lat1 = np.asarray(lat, dtype=float).reshape(-1)
    lon1 = np.asarray(lon, dtype=float).reshape(-1)
    alt1 = np.asarray(alt, dtype=float).reshape(-1)
    fig = plt.figure(figsize=(7, 5.4), dpi=140)
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(lon1, lat1, alt1, linewidth=1.2, marker=".", markersize=3)
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_zlabel("Altitude")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_vector_overview(
    path: Path,
    *,
    x: np.ndarray,
    data: np.ndarray,
    title: str,
    component_labels: list[str],
    ylabel: str,
    magnitude_label: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.asarray(data, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("plot_vector_overview requires a 3-component vector dataset")
    axis = _x_axis(x, values.shape[0])
    magnitude = np.linalg.norm(values, axis=1)
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 6.2), dpi=140, sharex=True)
    for index, label in enumerate(component_labels):
        axes[0].plot(axis, values[:, index], linewidth=1.0, label=label)
    axes[0].set_title(title)
    axes[0].set_ylabel(ylabel)
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="best", fontsize=8)
    axes[1].plot(axis, magnitude, linewidth=1.2, color="#111827", label=magnitude_label)
    axes[1].set_xlabel("Sample" if x.size == 0 else "Unix time")
    axes[1].set_ylabel(ylabel)
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_quality_overview(path: Path, *, x: np.ndarray, flags: np.ndarray, title: str) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.asarray(flags).reshape(-1)
    axis = _x_axis(x, values.shape[0])
    labels, counts = np.unique(values, return_counts=True)
    distribution = {str(_json_scalar(label)): int(count) for label, count in zip(labels, counts, strict=True)}
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), dpi=140)
    axes[0].plot(axis, values, linewidth=1.0, marker=".", markersize=3)
    axes[0].set_title("Flag by sample")
    axes[0].set_xlabel("Sample" if x.size == 0 else "Time/sample value")
    axes[0].set_ylabel("Flag")
    axes[0].grid(True, alpha=0.25)
    axes[1].bar([str(_json_scalar(label)) for label in labels], counts, color="#2563eb")
    axes[1].set_title("Flag distribution")
    axes[1].set_xlabel("Flag value")
    axes[1].set_ylabel("Count")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return distribution


def plot_cses_trajectory_overview(
    path: Path,
    *,
    x: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    alt: np.ndarray,
    title: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lat1 = np.asarray(lat, dtype=float).reshape(-1)
    lon1 = np.asarray(lon, dtype=float).reshape(-1)
    alt1 = np.asarray(alt, dtype=float).reshape(-1)
    axis = _x_axis(x, lat1.shape[0])
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.6), dpi=140)
    axes[0].plot(lon1, lat1, linewidth=1.1, marker=".", markersize=3)
    axes[0].set_title("Lon vs Lat")
    axes[0].set_xlabel("Longitude")
    axes[0].set_ylabel("Latitude")
    axes[0].grid(True, alpha=0.25)
    axes[1].plot(axis, alt1, linewidth=1.1, color="#0f766e")
    axes[1].set_title("Altitude")
    axes[1].set_xlabel("Sample" if x.size == 0 else "Time/sample value")
    axes[1].set_ylabel("Altitude")
    axes[1].grid(True, alpha=0.25)
    axes[2].plot(axis, lat1, linewidth=1.0, label="Lat")
    axes[2].plot(axis, lon1, linewidth=1.0, label="Lon")
    axes[2].set_title("Lat/Lon by sample")
    axes[2].set_xlabel("Sample" if x.size == 0 else "Time/sample value")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="best", fontsize=8)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_cadence_overview(path: Path, *, parsed_time_ms: np.ndarray, title: str, annotation: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.asarray(parsed_time_ms, dtype=float).reshape(-1)
    diffs = np.diff(values) if values.size > 1 else np.asarray([], dtype=float)
    duplicate_count = int(np.sum(diffs == 0)) if diffs.size else 0
    gap_count = int(np.sum(diffs > (np.median(diffs) * 2))) if diffs.size else 0
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), dpi=140)
    axes[0].plot(np.arange(diffs.size), diffs, linewidth=1.0, marker=".", markersize=3)
    axes[0].set_title("Cadence sequence")
    axes[0].set_xlabel("Interval index")
    axes[0].set_ylabel("Delta ms")
    axes[0].grid(True, alpha=0.25)
    if diffs.size:
        axes[1].hist(diffs, bins=min(40, max(5, int(np.sqrt(diffs.size)))), color="#2563eb", alpha=0.85)
    axes[1].set_title("Cadence histogram")
    axes[1].set_xlabel("Delta ms")
    axes[1].set_ylabel("Count")
    fig.suptitle(f"{title}\n{annotation}")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return {
        "interval_count": int(diffs.size),
        "duplicate_count": duplicate_count,
        "gap_count": gap_count,
        "min_ms": float(np.min(diffs)) if diffs.size else None,
        "median_ms": float(np.median(diffs)) if diffs.size else None,
        "max_ms": float(np.max(diffs)) if diffs.size else None,
    }


def _x_axis(x: np.ndarray, sample_count: int) -> np.ndarray:
    arr = np.asarray(x)
    if arr.size == sample_count:
        return arr.reshape(-1)
    return np.arange(sample_count)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value
