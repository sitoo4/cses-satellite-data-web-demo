# Cluster Web Plot Regeneration

Last updated: 2026-06-05

## Policy

Cluster Web plots are formal Web-owned artifacts. The backend may read existing validated processed arrays and reuse field selection or plotting logic from `/Volumes/Elements/data/idlpython_v2`, but it must regenerate PNGs under:

```text
/Volumes/Elements/satellite_data_web/outputs/generated_plots/cluster/
```

Old PNG/PDF quicklooks under `/Volumes/Elements/data/idlpython_v2` are reference/debug products only. The Web app does not write to `/Volumes/Elements/data/idlpython_v2` or `/Volumes/Elements/data/cluster`, and it does not rerun multi-year production.

## Implemented Cluster Catalog Plots

### `cluster_magnetic_overview`

- Reads: `segment_B_MFA_after_delete`, optional `segment_time_context_unix`
- Source product: `daily_full/YYYY/daily_full_YYYYMMDD.npz`
- Output: regenerated PNG in `outputs/generated_plots/cluster`
- Figure content: MFA magnetic components plus `|B|`
- Metadata: field path, `nT`, `MFA`, range, processing log
- Quicklook relationship: replaces formal Web use of old B quicklook; old quicklook remains reference/debug only

### `cluster_electric_overview`

- Reads: `segment_E_MFA`, optional `segment_time_context_unix`, `segment_E_quality`
- Source product: `daily_full`
- Output: regenerated PNG in `outputs/generated_plots/cluster`
- Figure content: MFA electric components plus `|E|`
- Metadata: field path, `mV/m`, `MFA`, observed `segment_E_quality` distribution, range, processing log
- Boundary: quality values are reported only; no automatic EFW masking is applied

### `cluster_spectrogram_overview`

- Reads: `segment_dB_phi_psd`, `segment_dE_phi_psd`, `segment_frequency_axis`, `segment_time_wavelet_unix`
- Source product: `daily_full`
- Output: regenerated PNG in `outputs/generated_plots/cluster`
- Figure content: B phi PSD and E phi PSD panels
- Reuse: existing PSD arrays and original wavelet-output field semantics; no wavelet recomputation

### `cluster_orbit_overview`

- Reads: `segment_MLT`, `segment_MLAT`, `segment_L`
- Source product: `daily_full`
- Output: regenerated PNG in `outputs/generated_plots/cluster`
- Figure content: MLT-MLAT and L-MLAT panels
- Boundary: no raw CDF read and no new coordinate conversion is done in the Web runtime

### `cluster_solar_wind_overview`

- Desired fields: `flow_speed`, `SYM-H`, `pdyn`, `AE`, `Kp`, `Bmag_model`
- Current status for `20051203`: `unavailable`
- Current evidence: keyword search in `/Volumes/Elements/data/idlpython_v2` finds old context/quicklook traces, but `daily_full_20051203.npz` exposes only local Cluster context fields such as `segment_time_context_unix`, `segment_context_mask`, `full_day_time_context_unix`, and `full_day_context_mask`; it does not expose the desired solar-wind/context fields.
- API behavior: returns `status="unavailable"` with `missing_fields`; no PNG is generated

## Missing Or Unverified Work

- Identify whether a validated OMNI/solar-wind/context source exists outside the current `daily_full` product.
- Trace original solar-wind plotting logic, if any, to field source files rather than old PNG outputs.
- Add a verified schema for `flow_speed`, `SYM-H`, `pdyn`, `AE`, `Kp`, and `Bmag_model` before enabling `cluster_solar_wind_overview`.
- Keep old quicklook PNG/PDF files out of the formal Web artifact path unless explicitly requested as debug/reference material.
