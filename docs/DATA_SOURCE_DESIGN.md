# Data Source Design

Last updated: 2026-06-05

## Goal

The backend should expose Cluster and CSES HPM through one internal datasource interface while preserving strict separation of data roots, file formats, assumptions, and supported science features.

## Directory Boundary

Application root:

```text
/Volumes/Elements/satellite_data_web
```

External data roots:

```text
/Volumes/Elements/data/cluster
/Volumes/Elements/data/idlpython_v2
/Users/foursoils/Downloads/HPM
```

Rules:

- Do not copy raw H5 or CDF files into the application directory.
- Do not move or rename raw data.
- Do not modify `/Volumes/Elements/data/cluster`.
- Do not modify frozen Cluster stage scripts as part of the web app.
- Store generated inspection reports, plots, exports, and stats under `/Volumes/Elements/satellite_data_web/outputs`.

## Proposed Backend Layout

```text
satellite_data_web/
  backend/
    app/
      main.py
      core/
        config.py
        paths.py
        jobs.py
      datasources/
        base.py
        registry.py
        cluster.py
        cses_hpm.py
      services/
        cses_h5_inspector.py
        plotting.py
        table_export.py
        stats.py
      api/
        routes_health.py
        routes_datasources.py
        routes_jobs.py
    scripts/
      inspect_cses_hpm.py
  frontend/
  docs/
  outputs/
    cses_hpm_inspection/
    generated_plots/
      cluster/
      cses_hpm/
    exports/
    stats/
```

## Datasource Interface

All datasources should implement:

```python
class DataSource:
    name: str
    label: str

    def status(self) -> dict: ...
    def capabilities(self) -> dict: ...
    def list_files(self, filters: dict) -> list[dict]: ...
    def metadata(self, file_id: str | None = None) -> dict: ...
    def variables(self, file_id: str | None = None) -> list[dict]: ...
    def read_timeseries(self, request: dict) -> dict: ...
    def subset(self, request: dict) -> dict: ...
    def plot_catalog(self, file_id: str | None = None) -> dict: ...
    def plot(self, request: dict) -> dict: ...
    def export(self, request: dict) -> dict: ...
    def stats(self, request: dict) -> dict: ...
```

Each implementation should return structured capability and unsupported-feature messages rather than throwing generic errors for expected gaps.

## Data Model

File/date identity:

- Cluster processed date ID: `YYYYMMDD`
- CSES HPM file ID: stable relative path under configured HPM root

Variable identity:

- Cluster: product key or compact column, such as `segment_B_MFA_after_delete`
- CSES: H5 dataset path, such as `/group/dataset`

Time range:

```json
{
  "mode": "time",
  "start": "2005-12-03T15:00:00Z",
  "end": "2005-12-03T16:00:00Z"
}
```

Sample range:

```json
{
  "mode": "sample_index",
  "start_index": 0,
  "end_index": 1000
}
```

Confidence tags:

- `confirmed`: directly present in metadata, attrs, existing documentation, or verified product schema.
- `inferred`: guessed from names, shapes, dimensions, or sample statistics.
- `unsupported`: not supported for this datasource.
- `blocked`: scientifically or technically blocked pending a known decision.
- `todo`: planned but not implemented.

## Cluster Datasource

### Roots

Cluster datasource uses two roots:

- Raw root: `/Volumes/Elements/data/cluster`
- Processed root: `/Volumes/Elements/data/idlpython_v2`

The MVP should use processed root first.

### File Listing

List available processed dates by scanning:

- `daily_full/YYYY/daily_full_YYYYMMDD.npz`
- `daily_compact/YYYY/daily_compact_YYYYMMDD.parquet`
- `quicklook_B/YYYY/B_YYYYMMDD.png`
- `quicklook_E/YYYY/E_YYYYMMDD.png`
- `quicklook_POS/YYYY/POS_YYYYMMDD.png`
- `manifests/YYYY/manifest_YYYYMMDD.json`

Do not rely on old Windows paths inside manifests. Use local path conventions and the configured processed root.

### Metadata

For each processed date, metadata should include:

- local product paths and existence
- manifest fields
- segment start/end
- selected segment ID
- E availability
- quicklook window mode
- daily_full key inventory: key, shape, dtype
- daily_compact columns and dtypes

### Variables

Confirmed initial variables from `daily_full`:

| Category | Variables |
|---|---|
| Magnetic vector | `segment_B_GSE`, `segment_B0_GSE`, `segment_B_MFA_after_delete`, `segment_dB_MFA_after_delete`, `segment_dB_MFA_detrended` |
| Electric vector | `segment_E_GSE_clean`, `segment_E_corrected_GSE`, `segment_E_MFA`, `segment_dE_MFA_detrended` |
| Context | `segment_L`, `segment_MLT`, `segment_MLAT` |
| Frequency | `segment_frequency_axis` |
| Magnetic PSD | `segment_dB_radial_psd`, `segment_dB_phi_psd`, `segment_dB_parallel_psd` |
| Electric PSD | `segment_dE_radial_psd`, `segment_dE_phi_psd`, `segment_dE_parallel_psd` |
| Complex wavelet | `segment_dB_*_wv_complex`, `segment_dE_*_wv_complex` |
| Band power | `segment_Br_band_power`, `segment_Bphi_band_power`, `segment_Bpar_band_power`, `segment_Er_band_power`, `segment_Ephi_band_power`, `segment_Epar_band_power` |
| B/E derived ratios | `segment_BE_poloidal_ratio`, `segment_BE_toroidal_ratio`, `segment_BE_compressional_diagnostic_ratio` |

### Plotting

MVP plotting policy:

1. Treat historical PNG/PDF quicklooks in `/Volumes/Elements/data/idlpython_v2` as reference/debug artifacts only.
2. Generate formal web Cluster plots from existing `daily_full` arrays under `/Volumes/Elements/satellite_data_web/outputs/generated_plots/cluster`.
3. Use existing PSD arrays for spectrograms; do not recompute wavelets or rerun production.

Implemented Cluster catalog plots:

- `cluster_magnetic_overview`: magnetic vector/delta overview from `daily_full`.
- `cluster_electric_overview`: electric vector/delta overview from `daily_full`.
- `cluster_spectrogram_overview`: B/E PSD overview from existing PSD arrays.
- `cluster_orbit_overview`: L/MLT/MLAT overview from context arrays.
- `cluster_solar_wind_overview`: explicit unavailable response when validated solar-wind/context fields are missing.

Cluster quicklook semantics confirmed from `plot_daily_quicklook.py`:

- B quicklook: B GSE, B MFA, dB detrended, dB radial/phi/parallel PSD, B band power.
- E quicklook: E GSE, v x B, corrected E GSE, E MFA, dE detrended, dE radial/phi/parallel PSD, E band power.
- POS quicklook: L, MLT, MLAT plus position relation views.

### Unsupported Or Blocked Cluster Features

Return `blocked` for:

- formal L-bin conclusions
- formal f-L conclusions
- Figure 3
- final Cummings frequency matching
- modal classification from mixed B/E medians

Return `unsupported`, `not_available`, or `unavailable` when a selected date has no required E data, no valid segment, or no validated solar-wind/context fields.

Cluster solar wind is exposed as a catalog item so the frontend can show the intended output and the backend can return explicit `missing_fields`. It does not write an artifact until validated fields such as `flow_speed`, `SYM-H`, `pdyn`, `AE`, `Kp`, and `Bmag_model` are available.

## CSES HPM Datasource

### Root

CSES HPM root should default to:

```text
/Users/foursoils/Downloads/HPM
```

This differs from the originally known archive path `/Volumes/Elements/HPM`; the phase-2 script is explicitly required to inspect `/Users/foursoils/Downloads/HPM`.

### Phase-2 Inspector

The inspector service and CLI should be created before the CSES datasource makes semantic claims.

Required files:

```text
backend/app/services/cses_h5_inspector.py
backend/scripts/inspect_cses_hpm.py
```

Required output root:

```text
outputs/cses_hpm_inspection/
```

Required per-file outputs:

- `h5_tree.json`
- `h5_tree.txt`
- `summary.json`
- `report.md`

The inspector must:

- recursively find H5/HDF5 files
- walk groups/datasets
- record dataset path, shape, dtype, compression, chunking, attrs
- record units, fill value, valid range, description, and long_name when present
- take head/tail previews and bounded sample statistics
- avoid full-array reads for large datasets
- infer candidate time, B vector, B scalar, lat/lon/alt/orbit, and quality fields
- mark every candidate as `confirmed` or `inferred`

### CSES Variable Discovery

The datasource must read inspection summaries rather than hard-code fields.

Candidate types:

- time
- magnetic_vector
- magnetic_scalar
- latitude
- longitude
- altitude
- position_vector
- quality_flag
- mode/status

Inference evidence should be stored and shown to the user. Example evidence:

- dataset name contains `time`, `utc`, `epoch`, `lat`, `lon`, `alt`, `B`
- shape is one-dimensional and same length as a candidate data variable
- shape has last dimension 3
- attrs include units, long_name, description, valid_min/max, fill value

### CSES Plotting

MVP catalog after inspection:

- `cses_hpm_magnetic_overview`: HPM vector magnetic components plus `|B|`.
- `cses_hpm_quality_overview`: inferred quality-flag distribution when a flag field exists.
- `cses_hpm_trajectory_overview`: enabled only when latitude/longitude/altitude fields are available.
- `cses_hpm_cadence_overview`: mechanically parsed `/UTC_TIME` cadence overview.
- `cses_hpm_batch_statistics_overview`: selected multi-file batch statistics using numeric time sort/deduplicate.
- `cses_hpm_spectrogram_overview`: disabled until time semantics, cadence, magnetic variable, and quality masking are confirmed.

MVP unsupported:

- electric-field plots, because CSES HPM is magnetometer-only
- solar-wind plots, because CSES HPM is magnetometer-only
- pitch-angle analysis
- blind wavelet/spectrogram before sampling cadence and time field are confirmed

### CSES Statistics

Phase 6 stats support one user-selected file with `sample_index` or mechanically resolved inferred `/UTC_TIME` ranges, plus selected multi-file CSES batches with `sample_index` ranges. Implemented behavior:

- bounded H5 dataset reads under the configured HPM root
- sample count and selected index range, including resolved sample indices for supported single-file time ranges
- per-component finite count, min, max, mean, median, standard deviation, and missing ratio
- selected multi-file CSES reads with numeric time sort/deduplicate
- selected multi-file magnetic Batch Plot using the same numeric time sort/deduplicate result
- cadence summary, quality flag distribution, `|B|` magnitude stats, and spatial coverage when the request supplies the relevant variables
- saved stats artifacts in json/csv/dat/h5 formats under `outputs/stats`
- stats CDF output returns `unsupported`/`reserved` until a CDF writer and metadata mapping are verified
- frontend single-file Stats action uses the selected JSON/CSV/DAT/H5 stats artifact format and displays a registered artifact link
- frontend Batch Stats control sends selected CSES H5 `file_ids` while keeping the current H5 file included and using the selected stats artifact format

Deferred behavior:

- semantic validation of parsed time encoding and leap-second/cadence policy

## Export Design

Exports should be datasource-neutral and written under:

```text
/Volumes/Elements/satellite_data_web/outputs/exports/
```

Phase 6 implemented:

- CSV, DAT, and H5 exports for selected variables and bounded `sample_index` ranges.
- CSES single-file CSV/DAT/H5 export with mechanically resolved inferred `/UTC_TIME` ranges when `/UTC_TIME` is parseable.
- Per-export `manifest.json` with datasource, original file, variables, request/resolved range, sample count, units, export format, and processing time.
- Registered artifact IDs for controlled download through `GET /api/artifacts/{artifact_id}`.
- Cluster exports read existing `daily_full` arrays only.
- CSES exports read selected datasets under the configured HPM root only.

Deferred:

- multi-file export packages

CDF export is reserved:

- The interface can accept `format="cdf"`.
- The response is `status="unsupported"` with `reserved=true` unless `cdflib` or `spacepy` write support is verified and metadata mapping is designed.
- The frontend shows a disabled `CDF TODO` option so users can see the planned interface without generating CDF files.

## Job Design

Use jobs for:

- CSES inspection over many files
- batch stats
- export
- generated plots that may take more than a trivial amount of time

Simple existing quicklook lookup can be synchronous.

Job records should include:

- job ID
- datasource
- operation
- status
- created/started/finished timestamps
- progress text
- output artifact IDs
- error code and message if failed

## Safety Checks

Before any datasource operation:

- Confirm the requested path is inside the configured datasource root.
- Reject absolute file paths from user requests unless resolved by file ID.
- Enforce output writes under `outputs_root`.
- Set size/preview limits for metadata reads.
- Avoid H5 full-array reads unless the user explicitly requests a bounded subset.
- Avoid Cluster production reruns unless a future endpoint is explicitly designed as an administrative/offline action.

## MVP Build Sequence

Phase 1 completed by this document:

- audit existing Cluster data and code
- define API
- define datasource design

Next phases:

1. Implement and run CSES H5 inspector.
2. Implement config, registry, and CSES minimal metadata API.
3. Implement Cluster processed-output datasource and existing quicklook API. Done in phase 4.
4. Implement frontend MVP.
5. Implement subset/export/stats.
