from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm


PSD_NORM = LogNorm(vmin=1e-2, vmax=1e3)
PSD_CMAP = plt.get_cmap("jet").copy()
PSD_CMAP.set_under("black")


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


def plot_psd_spectrogram(path: Path, *, time: np.ndarray, frequency: np.ndarray, psd: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(psd, dtype=float)
    if data.ndim != 2:
        raise ValueError("plot_psd_spectrogram requires a 2D PSD array")
    freq = np.asarray(frequency, dtype=float).reshape(-1)
    if freq.size != data.shape[1]:
        freq = np.arange(data.shape[1], dtype=float)
    axis = _x_axis(time, data.shape[0])
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=140)
    mesh = ax.pcolormesh(axis, freq, data.T, shading="auto", norm=PSD_NORM, cmap=PSD_CMAP)
    if freq.size:
        ax.set_ylim(0.001, min(0.05, float(np.nanmax(freq))))
    ax.set_title(title)
    ax.set_xlabel("Unix time")
    ax.set_ylabel("Frequency Hz")
    fig.colorbar(mesh, ax=ax, label="PSD")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_cluster_b_quicklook(
    path: Path,
    *,
    date8: str,
    segment_start_time: float | None,
    segment_end_time: float | None,
    time_context: np.ndarray,
    time_wavelet: np.ndarray,
    frequency: np.ndarray,
    b_gse: np.ndarray | None,
    b_mfa: np.ndarray | None,
    db_mfa: np.ndarray | None,
    db_radial_psd: np.ndarray | None,
    db_phi_psd: np.ndarray | None,
    db_parallel_psd: np.ndarray | None,
    sqrt_br_band_power: np.ndarray | None,
    sqrt_bphi_band_power: np.ndarray | None,
    sqrt_bpar_band_power: np.ndarray | None,
    l_shell: np.ndarray | None,
    mlt: np.ndarray | None,
    mlat: np.ndarray | None,
) -> list[str]:
    """Render the Web Cluster B quicklook with the idlpython_v2 panel recipe.

    This mirrors <cluster_processed_root>/plot_daily_quicklook.py:
    segment B_GSE, B_MFA, dB_MFA, three dB PSD panels using jet+LogNorm, band
    power, and bottom UTC/MLAT/MLT/L tick rows. It does not recompute physics.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    t_ctx = _unix_to_datetime_axis(time_context)
    t_wave = _unix_to_datetime_axis(time_wavelet)
    freq = np.asarray(frequency, dtype=float).reshape(-1)
    fig, axes = plt.subplots(7, 1, figsize=(13.5, 13.8), dpi=160, constrained_layout=False)
    fig.subplots_adjust(left=0.09, right=0.97, top=0.955, bottom=0.14, hspace=0.22)
    fig.suptitle(f"B_{date8} | {date8[:4]}-{date8[4:6]}-{date8[6:8]} segment 0", fontsize=15, fontweight="bold")
    used: list[str] = []

    for ax, key, x_axis, values, labels, panel_title in [
        (axes[0], "segment_B_GSE", t_ctx, b_gse, ("Bx", "By", "Bz"), "segment_B_GSE"),
        (axes[1], "segment_B_MFA_after_delete", t_ctx, b_mfa, ("Br", "Bphi", "Bpar"), "segment_B_MFA_after_delete"),
        (axes[2], "segment_dB_MFA_detrended", t_wave, db_mfa, ("dBr", "dBphi", "dBpar"), "segment_dB_MFA_detrended"),
    ]:
        if _plot_cluster_components(ax, x_axis, values, labels, panel_title, "nT"):
            used.append(key)

    for ax, key, values, panel_title in [
        (axes[3], "segment_dB_radial_psd", db_radial_psd, "segment dB radial PSD"),
        (axes[4], "segment_dB_phi_psd", db_phi_psd, "segment dB phi PSD"),
        (axes[5], "segment_dB_parallel_psd", db_parallel_psd, "segment dB parallel PSD"),
    ]:
        if _plot_cluster_psd_panel(ax, fig, t_wave, freq, values, panel_title):
            used.append(key)

    band_power = [
        ("segment_sqrt_Br_band_power", sqrt_br_band_power, "sqrt Br"),
        ("segment_sqrt_Bphi_band_power", sqrt_bphi_band_power, "sqrt Bphi"),
        ("segment_sqrt_Bpar_band_power", sqrt_bpar_band_power, "sqrt Bpar"),
    ]
    if t_wave.size and all(values is not None for _, values, _ in band_power):
        for key, values, label in band_power:
            y = np.asarray(values, dtype=float).reshape(-1)
            n = min(t_wave.size, y.size)
            axes[6].plot(t_wave[:n], y[:n], lw=0.85, label=label)
            used.append(key)
        axes[6].set_title("segment sqrt(B band power)", loc="left", fontsize=9)
        axes[6].set_ylabel("nT")
        axes[6].grid(True, alpha=0.22)
        axes[6].legend(loc="upper right", fontsize=7, ncol=3, frameon=False)
    else:
        _set_missing(axes[6], "segment sqrt B band power")

    _set_segment_xlim(list(axes), segment_start_time, segment_end_time)
    _format_time_axis(list(axes))
    used.extend(_add_cluster_context_tick_rows(fig, axes[-1], time_context, l_shell, mlt, mlat))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return used


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


def plot_dual_psd_spectrogram(
    path: Path,
    *,
    time: np.ndarray,
    frequency: np.ndarray,
    b_psd: np.ndarray,
    e_psd: np.ndarray,
    title: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    b_data = np.asarray(b_psd, dtype=float)
    e_data = np.asarray(e_psd, dtype=float)
    if b_data.ndim != 2 or e_data.ndim != 2:
        raise ValueError("plot_dual_psd_spectrogram requires 2D PSD arrays")
    freq = np.asarray(frequency, dtype=float).reshape(-1)
    if freq.size != b_data.shape[1] or freq.size != e_data.shape[1]:
        freq = np.arange(min(b_data.shape[1], e_data.shape[1]), dtype=float)
        b_data = b_data[:, : freq.size]
        e_data = e_data[:, : freq.size]
    b_axis = _x_axis(time, b_data.shape[0])
    e_axis = _x_axis(time, e_data.shape[0])
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.0), dpi=140, sharex=False)
    for ax, axis, values, label in [
        (axes[0], b_axis, b_data, "B phi PSD"),
        (axes[1], e_axis, e_data, "E phi PSD"),
    ]:
        mesh = ax.pcolormesh(axis, freq, values.T, shading="auto", norm=PSD_NORM, cmap=PSD_CMAP)
        if freq.size:
            ax.set_ylim(0.001, min(0.05, float(np.nanmax(freq))))
        ax.set_title(label)
        ax.set_xlabel("Unix time")
        ax.set_ylabel("Frequency Hz")
        fig.colorbar(mesh, ax=ax, label="PSD")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_cluster_orbit_overview(path: Path, *, mlt: np.ndarray, mlat: np.ndarray, l_shell: np.ndarray, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mlt1 = np.asarray(mlt, dtype=float).reshape(-1)
    mlat1 = np.asarray(mlat, dtype=float).reshape(-1)
    l1 = np.asarray(l_shell, dtype=float).reshape(-1)
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.9), dpi=140)
    axes[0].plot(mlt1, mlat1, linewidth=1.1, marker=".", markersize=3)
    axes[0].set_title("MLT vs MLAT")
    axes[0].set_xlabel("MLT")
    axes[0].set_ylabel("MLAT")
    axes[0].grid(True, alpha=0.25)
    axes[1].plot(l1, mlat1, linewidth=1.1, marker=".", markersize=3, color="#7c3aed")
    axes[1].set_title("L vs MLAT")
    axes[1].set_xlabel("L")
    axes[1].set_ylabel("MLAT")
    axes[1].grid(True, alpha=0.25)
    fig.suptitle(title)
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


def _unix_to_datetime_axis(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if not arr.size:
        return np.asarray([], dtype=object)
    from datetime import datetime, timezone

    return np.asarray([datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None) for value in arr], dtype=object)


def _set_missing(ax: Any, label: str) -> None:
    ax.text(0.5, 0.5, f"{label}\nmissing", ha="center", va="center", transform=ax.transAxes, color="0.35")
    ax.set_xticks([])
    ax.set_yticks([])


def _plot_cluster_components(ax: Any, x_axis: np.ndarray, values: np.ndarray | None, labels: tuple[str, str, str], title: str, ylabel: str) -> bool:
    if x_axis.size == 0 or values is None:
        _set_missing(ax, title)
        return False
    data = np.asarray(values, dtype=float)
    if data.ndim != 2 or data.shape[1] < 3:
        _set_missing(ax, title)
        return False
    n = min(x_axis.size, data.shape[0])
    if n < 2:
        _set_missing(ax, title)
        return False
    for index, (label, color) in enumerate(zip(labels, ("#1f77b4", "#d62728", "#2ca02c"), strict=True)):
        ax.plot(x_axis[:n], data[:n, index], lw=0.75, color=color, label=label)
    ax.set_title(title, loc="left", fontsize=9)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper right", fontsize=7, ncol=3, frameon=False)
    return True


def _plot_cluster_psd_panel(ax: Any, fig: Any, x_axis: np.ndarray, freq: np.ndarray, values: np.ndarray | None, title: str) -> bool:
    if x_axis.size == 0 or freq.size == 0 or values is None:
        _set_missing(ax, title)
        return False
    psd = np.asarray(values, dtype=float)
    if psd.ndim != 2:
        _set_missing(ax, title)
        return False
    n_t = min(x_axis.size, psd.shape[0])
    n_f = min(freq.size, psd.shape[1])
    if n_t < 2 or n_f < 2:
        _set_missing(ax, title)
        return False
    mesh = ax.pcolormesh(
        x_axis[:n_t],
        np.asarray(freq[:n_f], dtype=float),
        psd[:n_t, :n_f].T,
        shading="auto",
        norm=PSD_NORM,
        cmap=PSD_CMAP,
    )
    ax.set_ylim(0.001, min(0.05, float(np.nanmax(freq[:n_f]))))
    ax.set_ylabel("Hz")
    ax.set_title(title, loc="left", fontsize=9)
    cbar = fig.colorbar(mesh, ax=ax, pad=0.006, fraction=0.025)
    cbar.ax.tick_params(labelsize=6)
    return True


def _format_time_axis(axes: list[Any]) -> None:
    if not axes:
        return
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[-1].set_xlabel("UTC")
    for ax in axes[:-1]:
        plt.setp(ax.get_xticklabels(), visible=False)


def _set_segment_xlim(axes: list[Any], start: float | None, end: float | None) -> None:
    if start is None or end is None or not np.isfinite(start) or not np.isfinite(end):
        return
    from datetime import datetime, timezone

    limits = (
        datetime.fromtimestamp(float(start), tz=timezone.utc).replace(tzinfo=None),
        datetime.fromtimestamp(float(end), tz=timezone.utc).replace(tzinfo=None),
    )
    for ax in axes:
        ax.set_xlim(*limits)


def _add_cluster_context_tick_rows(
    fig: Any,
    ax: Any,
    time_context: np.ndarray,
    l_shell: np.ndarray | None,
    mlt: np.ndarray | None,
    mlat: np.ndarray | None,
) -> list[str]:
    if l_shell is None or mlt is None or mlat is None:
        return []
    time_unix = np.asarray(time_context, dtype=float).reshape(-1)
    l_val = np.asarray(l_shell, dtype=float).reshape(-1)
    mlt_val = np.asarray(mlt, dtype=float).reshape(-1)
    mlat_val = np.asarray(mlat, dtype=float).reshape(-1)
    n = min(time_unix.size, l_val.size, mlt_val.size, mlat_val.size)
    if n < 2:
        return []
    time_unix = time_unix[:n]
    l_val = l_val[:n]
    mlt_val = mlt_val[:n]
    mlat_val = mlat_val[:n]
    finite = np.isfinite(time_unix) & np.isfinite(l_val) & np.isfinite(mlt_val) & np.isfinite(mlat_val)
    if finite.sum() < 2:
        return []
    from datetime import datetime, timezone

    tick_times = np.linspace(float(np.nanmin(time_unix[finite])), float(np.nanmax(time_unix[finite])), 5)
    tick_dt = _unix_to_datetime_axis(tick_times)
    l_tick = np.interp(tick_times, time_unix[finite], l_val[finite])
    mlt_tick = np.interp(tick_times, time_unix[finite], mlt_val[finite])
    mlat_tick = np.interp(tick_times, time_unix[finite], mlat_val[finite])
    labels = []
    for time_value, mlat_value, mlt_value, l_value in zip(tick_times, mlat_tick, mlt_tick, l_tick, strict=True):
        utc = datetime.fromtimestamp(float(time_value), tz=timezone.utc).strftime("%H:%M")
        labels.append(f"{utc}\n{mlat_value:.1f}\n{mlt_value:.1f}\n{l_value:.1f}")
    ax.set_xticks(tick_dt)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_xlabel("")
    for y_pos, text in [(-0.13, "UTC"), (-0.26, "MLAT"), (-0.39, "MLT"), (-0.52, "L")]:
        ax.text(-0.055, y_pos, text, transform=ax.transAxes, ha="right", va="center", fontsize=8, clip_on=False)
    fig.subplots_adjust(left=0.09, bottom=0.12)
    return ["segment_time_context_unix", "segment_L", "segment_MLT", "segment_MLAT"]


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value
