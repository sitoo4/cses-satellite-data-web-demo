# Satellite Data Web Project Audit

Last updated: 2026-06-04

## Scope

This is the phase-1 audit for the planned web application under `<repo>`.

Confirmed inputs inspected in this phase:

- Cluster raw-data directory, sampled only by directory and filename metadata: `<cluster_raw_root>`
- Existing Cluster processing project: `<cluster_processed_root>`
- Existing Cluster processed outputs under `<cluster_processed_root>/daily_full`, `daily_compact`, `quicklook_B`, `quicklook_E`, `quicklook_POS`, `manifests`, `provenance`, and `analysis`

Out of scope for this phase:

- No CSES HPM H5 file was opened.
- No original Cluster CDF content was read beyond directory/file sampling.
- No production Cluster processing was rerun.
- No old IDL, `.pro`, `.sav`, or frozen Python physics code was modified.

## Existing Cluster Data Layout

Confirmed by directory sampling:

| Path | Role | Sampled contents |
|---|---|---|
| `<cluster_raw_root>/C1cichang` | C1 FGM spin magnetic-field CDF files | `c1_cp_fgm_spin_YYYYMMDD_vNN.cdf`; 7,676 CDF files sampled by filename |
| `<cluster_raw_root>/C1LMLT` | PMP L/MLT context files | `c1_jp_pmp_YYYYMM01_vNN.cdf`; 269 CDF files sampled by filename |
| `<cluster_raw_root>/C1_E_year` | yearly C1 EFW electric-field CDF files | `C1_CP_EFW_L3_E3D_GSE__YYYY0101_...cdf`; 18 CDF files sampled by filename |
| `<cluster_raw_root>/cl` | Cluster AUX position and spin-plane auxiliary data | `C1_CP_AUX_POSGSE_1M__...cdf`, `cl/sp/YYYY/cl_sp_aux_YYYYMMDD_vNN.cdf`; 7,437 CDF files sampled by filename |
| `<cluster_raw_root>/cis/2005` | C1 CIS density status sample for 2005-12-03 | `c1_pp_cis_20051203_v01.cdf` |
| `<cluster_raw_root>/whi/2005` | C1 WHISPER sample for 2005-12-03 | `c1_pp_whi_20051203_v01.cdf` |

Directory sizes sampled with `du -sh`:

- `C1cichang`: 8.2G
- `cl`: 7.6G
- `C1_E_year`: 4.9G
- `C1LMLT`: 270M
- `cis`: 5.0M
- `whi`: 4.0M

## Existing Cluster Processing Project

The existing processing code lives in `<cluster_processed_root>`.

Key documents read:

- `PROJECT_HANDOFF_SHORT.md`
- `docs/handoff/03_TRUSTED_AND_BLOCKED_BOUNDARIES.md`
- `docs/handoff/04_DATA_PRODUCTS_AND_PATHS.md`
- `docs/handoff/05_PIPELINE_STATUS.md`
- `reports/yearly_dry_run/2005/YEARLY_DRY_RUN_2005_AUDIT.md`

Confirmed current state:

- Magnetic B-chain Stage1-7 is PASS/frozen for gated dates `2005-12-03` and `2009-05-10`, segment 0.
- Electric E-chain E1-E5 is PASS/frozen for the same gated dates.
- 2005 yearly dry run is complete: 156 `SUCCESS`, 1 `SUCCESS_B_ONLY_NO_E`, 207 `NO_VALID_SEGMENT`, 1 `SKIP_MISSING_SOURCE`, 0 stage/write/quicklook failures.
- Production schema is segment-first. Daily quicklooks are segment-only.
- 2005 output uses one main quicklook name per product family: `B_YYYYMMDD.png`, `E_YYYYMMDD.png`, `POS_YYYYMMDD.png`.
- B/E ratio is a derived analysis product, not original IDL gold.
- Formal L-bin, f-L, Figure 3, and final Cummings matching remain blocked until `L_calc`, `PMP_L`, `L_for_bin`, `L_source`, and `L_quality_flag` are explicitly separated.

## Existing Cluster Scripts

Confirmed script inventory, grouped by role:

| Script | Role | Reuse recommendation |
|---|---|---|
| `project_paths.py` | Mac path-root configuration and module path rebinding | Reuse conceptually for config handling; do not import blindly into web backend unless path side effects are understood |
| `run_daily_production.py` | Generalized daily production driver wiring B Stage1-7, E E1-E5, B/E, daily products, manifests, quicklooks | Do not call automatically from web MVP; expose as explicit offline/manual action only |
| `plot_daily_quicklook.py` | Reads existing `daily_full` and generates segment-only B/E/POS quicklook PNGs | Reuse plotting field map and figure semantics; first prefer existing PNGs |
| `plot_daily_position_quicklook.py` | POS quicklook compatibility wrapper | Secondary reuse; note it may write segment-suffix copies for older gated date behavior |
| `yearly_dry_run_2005.py` | 2005 dry-run orchestration/reporting | Read results only for MVP; do not rerun by default |
| `monthly_dry_run_200512.py`, `monthly_dry_run_200512_after_e1_no_e_policy.py` | December 2005 dry-run reports | Read results only |
| `production_smoke_test.py`, `production_smoke_test_rerun_20051201_20051207.py` | bounded smoke tests | Useful for later maintenance, not required for web MVP |
| `production_output_layout.py`, `segment_first_daily_products.py` | older layout/trial migration scripts | Treat as provenance; do not use as current runtime entry points |
| `analysis/position_drift/build_position_drift_2005.py` | 2005 position-drift diagnostic from existing products | Reuse outputs for context/statistics; do not recompute unless requested |
| `analysis/narrowband/*.py` | 2005-12-03 narrowband peak/event/phase/B-E diagnostics from existing products | Reuse generated tables and figures; do not rerun raw wavelet/PSD |
| `analysis/density_alfven/*` | density-source, CIS, WHISPER, and Alfven audit scripts | Reuse reports/tables for 2005-12-03 context; not general Cluster web MVP yet |

## Existing Cluster Products

Confirmed production product layout:

| Product family | Confirmed paths |
|---|---|
| daily full NPZ | `<cluster_processed_root>/daily_full/YYYY/daily_full_YYYYMMDD.npz` |
| daily compact parquet | `<cluster_processed_root>/daily_compact/YYYY/daily_compact_YYYYMMDD.parquet` |
| B quicklook PNG | `<cluster_processed_root>/quicklook_B/YYYY/B_YYYYMMDD.png` |
| E quicklook PNG | `<cluster_processed_root>/quicklook_E/YYYY/E_YYYYMMDD.png` |
| POS quicklook PNG | `<cluster_processed_root>/quicklook_POS/YYYY/POS_YYYYMMDD.png` |
| manifest JSON | `<cluster_processed_root>/manifests/YYYY/manifest_YYYYMMDD.json` |
| provenance JSON | `<cluster_processed_root>/provenance/YYYY/daily_provenance_YYYYMMDD.json` |
| logs | `<cluster_processed_root>/logs/YYYY/run_YYYYMMDD.log` |

Confirmed current product coverage:

- `daily_full`: 157 files for 2005, 1 file for 2009.
- `daily_compact`: 157 files for 2005, 1 file for 2009.
- `quicklook_B`, `quicklook_E`, `quicklook_POS`: 157 main files each for 2005. For 2009, both main and `_seg000` files are present.
- `manifests`: 157 files for 2005, 1 file for 2009.

Important path caveat:

- Some manifest/provenance JSON payloads still contain historical `E:\data\...` path strings.
- The web backend must resolve product paths from local configuration and filename conventions, not blindly trust Windows paths stored in old manifests.

## Existing Cluster Fields

Confirmed by opening `<cluster_processed_root>/daily_full/2005/daily_full_20051203.npz` metadata only:

- 74 keys, size about 11.5 MB.
- Time axes:
  - `segment_time_context_unix`
  - `segment_time_wavelet_unix`
  - `segment_E_time_unix`
  - `full_day_time_context_unix`
- Context/orbit:
  - `segment_L`, `segment_MLT`, `segment_MLAT`, `segment_context_mask`
  - `full_day_L`, `full_day_MLT`, `full_day_MLAT`, `full_day_context_mask`
- Magnetic field and perturbations:
  - `segment_B_GSE`
  - `segment_B0_GSE`
  - `segment_B_MFA_after_delete`
  - `segment_dB_MFA_after_delete`
  - `segment_B_smoothed_background`
  - `segment_dB_MFA_detrended`
- Electric field:
  - `segment_E_GSE_clean`
  - `segment_E_quality`
  - `segment_vxb_gse`
  - `segment_E_corrected_GSE`
  - `segment_E_MFA`
  - `segment_E_MFA_smoothed`
  - `segment_dE_MFA_detrended`
- Frequency/PSD/wavelet:
  - `segment_frequency_axis`
  - `segment_dB_radial_psd`, `segment_dB_phi_psd`, `segment_dB_parallel_psd`
  - `segment_dB_radial_wv_complex`, `segment_dB_phi_wv_complex`, `segment_dB_parallel_wv_complex`
  - `segment_dE_radial_psd`, `segment_dE_phi_psd`, `segment_dE_parallel_psd`
  - `segment_dE_radial_wv_complex`, `segment_dE_phi_wv_complex`, `segment_dE_parallel_wv_complex`
- Band power and B/E derived ratios:
  - `segment_Br_band_power`, `segment_Bphi_band_power`, `segment_Bpar_band_power`
  - `segment_Er_band_power`, `segment_Ephi_band_power`, `segment_Epar_band_power`
  - `segment_BE_poloidal_ratio`, `segment_BE_toroidal_ratio`, `segment_BE_compressional_diagnostic_ratio`

Confirmed compact table `<cluster_processed_root>/daily_compact/2005/daily_compact_20051203.parquet`:

- Shape: 219 rows x 41 columns.
- Key columns include `time_unix`, `time_iso`, `L`, `MLT`, `MLAT`, `valid_B_flag`, `valid_E_flag`, `valid_BE_flag`, `quality_flag`, band powers, and B/E ratio summary fields.

## Existing Cluster Figures

Confirmed reusable quicklook figures:

- B quicklook: `B_YYYYMMDD.png`, generated from B GSE, B MFA, detrended dB MFA, dB PSD panels, and B band-power panels.
- E quicklook: `E_YYYYMMDD.png`, generated from E GSE, v x B, corrected E GSE, E MFA, detrended dE MFA, dE PSD panels, and E band-power panels.
- POS quicklook: `POS_YYYYMMDD.png`, generated from L, MLT, MLAT and position relation views.

Confirmed narrowband analysis figures/tables for `2005-12-03`:

- Peak detection: f-peak, peak PSD, f-width, valid peak flags, dB spectrogram overlays.
- Event table: event timelines and event distributions.
- Phase diagnostics: phase difference vs time, event R bars, rose plots, phase-colored f-peak overlays, histograms.
- B/E ridge diagnostics and validation: event-level B/E or E/B time series, error bars, phase-R comparisons, MLAT/f-peak comparisons.
- Standing-wave spatial diagnostics: event-level E/B vs VA, MLAT plots, per-event time series.
- Component dominance: component bar plots and per-event amplitude/fraction plots.
- Position drift: MLAT/L/MLT span distributions and usability curves for 2005.
- Density/Alfven audits: CIS and WHISPER density inventory, event overlap, quality, and figures for 2005-12-03.

## Functions That Can Be Reused

High-confidence reuse:

- Existing processed products as read-only data sources.
- Existing quicklook PNGs for initial web display.
- `daily_full` NPZ arrays for plotting data endpoints.
- `daily_compact` parquet tables for date listing, summaries, and lightweight statistics.
- Manifest/provenance/log files for inspection and provenance display, after local path normalization.
- Existing narrowband and density analysis output tables/figures as static/read-only Cluster analysis artifacts.

Medium-confidence reuse:

- `plot_daily_quicklook.py` field mapping and plotting logic, if the web backend later needs to regenerate missing PNGs.
- `source_paths()` logic in `run_daily_production.py`, adapted into a safe indexer that does not run production stages.

Not appropriate for immediate web runtime:

- Automatic calls to `run_daily_production.py`.
- Automatic yearly/monthly production runs.
- Editing or executing IDL `.pro` files.
- Treating B/E ratio as original IDL validation.
- Any final L-bin, f-L, Figure 3, or Cummings classification workflow.

## CSES HPM H5 Unknowns For Phase 2

No H5 file was read in phase 1. The following remain unknown and must be discovered from H5 structure and attrs:

- File grouping and mission/product naming convention.
- Dataset tree and whether data are stored as groups, compound datasets, separate variables, or table-like arrays.
- Time field name, epoch format, units, time zone, leap-second convention, and monotonicity.
- Magnetic field vector field names, component order, coordinate frame, units, fill values, valid range, and scale/offset.
- Scalar magnetic field availability and whether it is measured or derived.
- Orbit/geolocation fields: longitude, latitude, altitude, radius, position vector, coordinate frame.
- Quality flags, status bits, mode flags, calibration flags, and bad-data indicators.
- Sampling cadence, gaps, duplicate samples, and sorting requirements.
- Chunking/compression and safe read strategy for large arrays.

All field identification in phase 2 must be recorded as either `confirmed` from metadata/attrs or `inferred` from names/shapes/sample statistics.

## MVP Recommendation

The smallest useful MVP should avoid rerunning Cluster science logic and avoid premature CSES physics:

1. Backend config and datasource registry:
   - `cluster` uses `<cluster_processed_root>` processed outputs.
   - `cses_hpm` uses `<local_cses_hpm_root>` or configured HPM root.
2. Cluster read-only display:
   - List available Cluster processed dates.
   - Show date status from manifests or yearly reports.
   - Show existing B/E/POS quicklook PNGs.
   - List `daily_full` variables and compact summary fields.
   - Provide simple time-series data from `daily_full` for selected fields.
3. CSES HPM inspection first:
   - Recursively inspect H5 files without full-array loading.
   - Emit per-file tree, metadata, inferred candidates, and reports.
4. CSES HPM minimal display after inspection:
   - Show confirmed/inferred magnetic vector candidates.
   - Plot B components and `|B|` only after time/vector fields are identified.
   - Show lat/lon/alt trajectory only if fields exist.
   - Support time crop only if time is parseable; otherwise support sample-index crop.
5. Export/statistics:
   - Implement after datasource interfaces are stable.
   - Support csv/dat/h5 first.
   - Keep CDF export as a reserved interface until `cdflib` or `spacepy` support is verified.

## Phase 2 Command

The next phase should create and run:

```bash
cd <repo>
python backend/scripts/inspect_cses_hpm.py \
  --input-root <local_cses_hpm_root> \
  --output-root <repo>/outputs/cses_hpm_inspection \
  --max-preview 8 \
  --sample-size 2048
```

Expected outputs per H5 file:

- `h5_tree.json`
- `h5_tree.txt`
- `summary.json`
- `report.md`

Phase 2 must not copy raw H5 files into the project.

## Phase 2 Result

Phase 2 has been run and documented in `docs/CSES_HPM_INSPECTION_NOTES.md`.

Confirmed execution result:

- HPM files inspected: `656`.
- Successful inspections: `656`.
- Errors: `0`.
- Per-file outputs present: `h5_tree.json`, `h5_tree.txt`, `summary.json`, and `report.md`.
- No raw H5/HDF5/HE5/CDF files were copied under `<repo>`.

## Phase 6 Result

Phase 6 adds bounded sample-index preview, csv/dat/h5 export, per-export manifest JSON, and statistics endpoints through the datasource interface.

Implemented runtime scope:

- Cluster reads existing `daily_full` NPZ arrays only for subset/statistics/export.
- CSES reads selected H5 datasets under the configured HPM root with bounded sample-index ranges.
- Exports and per-export `manifest.json` files are written under `<repo>/outputs/exports` and served by artifact ID.
- CSV, DAT, and H5 are supported export formats; CDF export remains deferred/reserved.

Safety boundaries preserved:

- No Cluster raw CDF files are read by Phase 6 endpoints.
- No Cluster production scripts are run by the web runtime.
- No raw H5/HDF5/HE5/CDF files are copied into `<repo>`.

Initial inferred CSES HPM candidates:

- time: `/UTC_TIME` in all 656 files.
- magnetic vector: `/B_FGM` in 328 files.
- latitude/longitude/altitude: `/GEO_LAT`, `/GEO_LON`, `/ALTITUDE` in all 656 files.
- quality/status flag: `/FLAG_MT` in all 656 files.

These are candidates, not final confirmed science semantics. Time encoding, component order, coordinate frame, and flag meanings still need explicit confirmation.
