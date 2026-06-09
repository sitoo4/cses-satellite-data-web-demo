# Phase 6 Export And Statistics Notes

Last updated: 2026-06-05

## Scope

Phase 6 adds bounded subset, generated datasource PNG plots, csv/dat/h5 export, per-export manifest JSON, and statistics plus saved stats artifacts for the existing datasource abstraction. The later plot-catalog update makes formal generated plots datasource-specific and stores them under `outputs/generated_plots`.

Implemented backend endpoints:

- `POST /api/datasources/{name}/subset`
- `POST /api/datasources/{name}/stats`
- `POST /api/datasources/{name}/export`
- `POST /api/datasources/{name}/plot`
- `GET /api/datasources/{name}/plot-catalog`
- `GET /api/jobs/{job_id}`

Implemented frontend controls:

- CSES sample-index or inferred `/UTC_TIME` preview, HPM plot catalog, selected multi-file Batch Plot, single-file stats, selected multi-file Batch Stats, and csv/dat/h5 export.
- CSES 2D/3D trajectory controls are enabled only when the selected H5 variable list contains the required coordinate fields; the backend also returns `not_available` instead of a 400 error when a trajectory request names missing coordinate variables.
- CSES electric-field, solar-wind, and spectrogram controls remain visible but disabled with source-specific reasons.
- Cluster processed-array preview table, generated magnetic/electric/spectrogram/orbit overview catalog, stats, csv/dat/h5 export, and explicit solar-wind unavailable response. Cluster controls support either sample-index ranges or confirmed UTC ranges backed by `segment_time_context_unix`.
- Cluster historical quicklooks are reference/debug only; formal web plots are regenerated into `outputs/generated_plots/cluster`.
- Download links use registered artifact IDs, not filesystem paths.
- Stats actions use the selected JSON/CSV/DAT/H5 stats artifact format and display the registered stats artifact link.
- Stats tables display per-component min/max/mean/median/std and missing ratio when the backend returns those fields.
- Batch Stats and Batch Plot send selected CSES H5 `file_ids`; the current H5 file remains included. Batch Plot uses the same numeric time sort/deduplicate rule as Batch Stats.
- Batch Stats summary displays cadence median, quality flag distribution, spatial coverage, and `|B|` mean when those fields are present in the backend response.
- Data context and processing-log panels show current file, selected variables, units, current range, confirmed Cluster time/cadence/sample-rate, inferred CSES time/quality candidates, mechanically parsed CSES time span/cadence/sample-rate, inferred quality-flag distributions when available, inspection report links when available, sample counts, and recent action status.
- Export format selector shows disabled `CDF TODO`; backend export/statistics CDF requests return `unsupported` with `reserved=true`.
- Plot/export/stats API calls return a synchronous completed `job_id`; the current backend process serves the job record from memory.

## Boundaries

- Cluster reads existing `daily_full` NPZ arrays only.
- Cluster metadata time spans and cadence are computed from existing `daily_full` `segment_time_context_unix` values and marked `confirmed` because the field is part of the processed Cluster schema.
- Cluster subset, generated overview plots, stats, and exports can resolve UTC ranges against confirmed `segment_time_context_unix` without reading raw CDF or rerunning production code.
- Cluster metadata quality summary counts observed `segment_E_quality` values and marks the field `confirmed`; the web app does not interpret the flag codes.
- Cluster generated magnetic/electric/spectrogram/orbit overview plots read existing `daily_full` arrays only and do not rerun wavelet or production code.
- Cluster raw CDF files are not read by Phase 6 endpoints.
- Cluster production scripts are not run.
- CSES reads only selected H5 datasets under the configured HPM root.
- CSES metadata returns a mechanically parsed file-level `/UTC_TIME` summary when available: UTC start/end, sample count, and cadence min/median/max. The time candidate and semantic confidence remain `inferred`.
- CSES metadata returns a file-level quality-flag distribution when an inferred flag dataset such as `/FLAG_MT` is readable. The flag values are counted but not interpreted.
- CSES single-file subset, plot, export, and stats can resolve parseable `/UTC_TIME` values to bounded sample-index reads. The time candidate and semantic confidence remain `inferred`.
- CSES spectrogram generation remains disabled until sampling cadence and time semantics are confirmed.
- Generated Cluster plots are written under `outputs/generated_plots/cluster`.
- Generated CSES HPM plots are written under `outputs/generated_plots/cses_hpm`.
- Exports are written under `outputs/exports`.
- Saved stats summaries are written under `outputs/stats`.
- Raw H5/CDF files are not copied into the app tree.

## Supported Outputs

Implemented:

- CSES HPM `cses_hpm_magnetic_overview`, `cses_hpm_quality_overview`, `cses_hpm_trajectory_overview`, `cses_hpm_cadence_overview`, and selected multi-file batch PNG/stat artifacts.
- CSV export.
- DAT export as tab-separated text.
- H5 export with `sample_index` and selected variables under `/variables`.
- Per-export `manifest.json`.
- Stats artifact export as JSON, CSV, DAT, or H5 summaries.
- Reserved CDF interface: no writer is run, and no CDF artifact is produced.

Deferred:

- Actual CDF writing after `cdflib` or `spacepy` behavior and metadata mapping are verified.
- Persistent or asynchronous job queue.
- Semantic validation of CSES parsed time, leap-second policy, coordinate frame, and cadence beyond the mechanical `/UTC_TIME` parser.

## Verification

Commands run on 2026-06-05:

```bash
PYTHONPATH=<repo>/backend \
  python -m unittest discover -s <repo>/backend/tests -p 'test_*.py' -v
```

Result:

```text
Ran 5 tests in 0.376s
OK
```

```bash
cd <repo>/frontend
npm test
```

Result:

```text
Test Files  2 passed (2)
Tests  9 passed (9)
```

```bash
cd <repo>/frontend
npm run build
```

Result:

```text
tsc -b && vite build
1581 modules transformed.
built in 984ms
```

2026-06-05 refresh:

```text
Backend unittest: Ran 10 tests in 1.072s, OK
Frontend vitest: Test Files 2 passed; Tests 17 passed
Frontend build: vite v7.3.5, 1581 modules transformed, built in 1.17s
npm audit: found 0 vulnerabilities
Raw-data safety scan under app tree: no .hdf5/.he5/.cdf files found; .h5 files appeared only under outputs/exports and outputs/stats, with macOS ._* sidecars
```

Browser/runtime verification:

```text
Local backend restarted on 127.0.0.1:8000 and frontend restarted on 127.0.0.1:5173.
Cluster UI: Stats returned 3 rows for segment_B_MFA_after_delete; CSV artifact GET returned sample_index plus vector component columns.
CSES UI: Stats returned 6 rows for /UTC_TIME, /B_FGM, /GEO_LAT, and /GEO_LON; CSV artifact GET returned selected H5 dataset columns.
CSES H5 export UI: Export format H5 produced Download H5 and Manifest artifact links.
CSES H5 export API: generated /sample_index plus /variables/B_FGM and manifest with unit nT; H5 unit attr verified as string.
CSES batch stats API: supports selected multi-file reads, numeric time sort/deduplicate, cadence summary, quality-flag distribution, spatial coverage, component medians, and `|B|` magnitude stats.
CSES batch stats UI: selected an additional H5 file, sent `file_ids` with time/flag/position helper variables and the selected stats format, displayed the registered stats artifact link, and artifact `cses_hpm:stats:batch:a603219efa4a` returned `mode=batch`, 2 files, and 24 samples.
CSES batch stats summary UI: displayed cadence median, `/FLAG_MT` distribution, lat/lon/alt spatial coverage, and `|B|` mean for a two-file batch with no page alert or browser console errors.
CSES batch plot UI/API: selected an additional H5 file, clicked Batch Plot, generated `cses_hpm:plot:batch:2d3d2fc7ab27`; artifact GET returned `content-type: image/png` and a 1260 x 672 PNG. Browser console errors: none observed.
CSES context/log UI: displays the current H5 file, `nT` unit from confirmed unit metadata objects, `sample_index` range, inferred `/UTC_TIME` and `/FLAG_MT`, mechanically parsed file time span/cadence/sample-rate, inferred flag distribution when available, batch sample counts, and recent action status.
CSES UTC range UI/API: single-file Preview, HPM catalog plots, Stats, and Export send `range.mode=time` with `time_variable=/UTC_TIME`; backend resolves the request to bounded sample indices and returns `time_confidence=inferred`.
CSES/Cluster stats artifacts: API supports json/csv/dat/h5 saved summary artifacts; frontend Stats action displays a registered stats artifact link for the selected format; stats CDF output returns `unsupported`/`reserved`.
Cluster stats DAT API: live backend returned `text/plain` artifact `cluster:stats:20051203:5e9bd2f24048`; artifact GET returned tab-separated component statistics for `segment_MLAT`.
CSES stats format UI: browser selected `DAT` in the Stats format control, clicked single-file Stats, and displayed a `Stats DAT` artifact link with no console errors.
CSES plot UI/API: generated HPM magnetic, quality, trajectory, and cadence catalog PNG artifacts when required fields are present; spectrogram remains disabled in the catalog.
Cluster PSD UI/API: `cluster_spectrogram_overview` generates B/E PSD PNGs from existing `daily_full` PSD arrays without rerunning wavelet code.
Cluster orbit UI/API: `cluster_orbit_overview` generates an L/MLT/MLAT trajectory PNG from existing `daily_full` `segment_MLT`, `segment_MLAT`, and `segment_L` arrays.
Cluster solar-wind UI/API: frontend shows `cluster_solar_wind_overview`; backend returns `status=unavailable` with explicit missing fields.
Jobs API: live backend returned job_id `plot:cses_hpm:661f478d7c9a`; `GET /api/jobs/{job_id}` returned status `completed`, kind `plot`, datasource `cses_hpm`, and an existing PNG artifact.
Browser console errors: none observed.
Backend log after restart: /api/datasources/cluster/stats, /cluster/export, /cses_hpm/stats, /cses_hpm/export, and /cses_hpm/plot all returned 200 OK.
```
