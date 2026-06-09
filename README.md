# Satellite Data Web

Local web workbench for satellite data inspection and draft visualization.

当前前端主流程已经改成 **张衡一号 CSES-01 HPM H5 文件上传驱动**。页面不再从固定 HPM 数据目录或日期档案里选择文件；用户只能上传一个或多个 `.h5` 文件，由后端创建 `upload_session_id` 并完成 metadata 读取、时间解析、排序、去重、分段、绘图和导出。

中文使用说明见 [`docs/CSES_HPM_UPLOAD_WORKFLOW_ZH.md`](docs/CSES_HPM_UPLOAD_WORKFLOW_ZH.md)。

## Current Scope

- Frontend main page: CSES HPM upload console.
- One uploaded file enters `SINGLE FILE` mode; two or more uploaded files enter `BATCH` mode automatically.
- The frontend never parses H5. It only uploads files and renders backend responses.
- Backend saves temporary uploaded H5 files under `outputs/uploads/cses_hpm/<upload_session_id>/raw/`.
- Generated plots are written under `outputs/generated_plots/cses_hpm/<upload_session_id>/`.
- Exports and per-export manifests are written under `outputs/exports/cses_hpm/<upload_session_id>/`.
- Feature-parameter statistics are written under `outputs/statistics/cses_hpm/<upload_session_id>/`.
- CSES HPM magnetic plot is enabled:
  - `HPM_5`: uses `/B_FGM` and plots Bx, By, Bz, and `|B|`.
  - `HPM_6`: uses `/A211` and plots scalar magnetic field.
  - Mixed `HPM_5` and `HPM_6` batch plotting is currently unavailable and returns an explicit reason.
- CSES HPM orbit plot is enabled as an interactive HTML artifact with mouse rotation, latitude/longitude labels, segment colors, and start/end time labels.
- CSES HPM spectrogram is intentionally disabled. No STFT, wavelet, or Pc5 spectrogram is generated in this workflow.
- CSES electric-field and solar-wind views are not implemented in the current upload console.
- CSV, DAT, and H5 export are supported. CDF is visible as TODO/unsupported.
- Descriptive feature statistics are supported for the deduped, sorted, optionally cropped upload-session dataset.
- Existing Cluster datasource/backend APIs remain in the codebase for reference and existing tests, but the current frontend page is upload-only for CSES HPM.
- Raw source files under `/Users/foursoils/Downloads/HPM` or `/Volumes/Elements/HPM` are not moved, deleted, or modified.

`outputs/`, `.env`, and `local_config.json` are ignored by Git.

## Run Backend

```bash
cd /Volumes/Elements/satellite_data_web
PYTHONPATH=/Volumes/Elements/satellite_data_web/backend \
  python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

## Run Frontend

```bash
cd /Volumes/Elements/satellite_data_web/frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Upload Session API

Create an upload session:

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads \
  -F "files=@/Volumes/Elements/HPM/CSES_01_HPM_5_L02_A2_289220_20230419_235533_20230420_003011_000.h5"
```

Upload multiple files:

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads \
  -F "files=@/Volumes/Elements/HPM/file_late.h5" \
  -F "files=@/Volumes/Elements/HPM/file_early.h5"
```

Get session metadata and run log:

```bash
curl -s http://127.0.0.1:8000/api/cses-hpm/uploads/<upload_session_id>
```

Generate magnetic plot:

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads/<upload_session_id>/plot \
  -H 'Content-Type: application/json' \
  -d '{"plot_type":"magnetic","crop_range":{"start":"2023-04-19T23:55:33Z","end":"2023-04-20T00:30:11Z"}}'
```

Generate interactive orbit plot:

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads/<upload_session_id>/plot \
  -H 'Content-Type: application/json' \
  -d '{"plot_type":"orbit"}'
```

Export cropped data:

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads/<upload_session_id>/export \
  -H 'Content-Type: application/json' \
  -d '{"format":"csv","crop_range":{"start":"2023-04-19T23:55:33Z","end":"2023-04-20T00:30:11Z"}}'
```

Compute feature-parameter statistics for the current deduped/sorted upload session:

```bash
curl -s -X POST http://127.0.0.1:8000/api/sessions/<upload_session_id>/statistics \
  -H 'Content-Type: application/json' \
  -d '{"crop_range":{"start":"2023-04-19T23:55:33Z","end":"2023-04-20T00:30:11Z"}}'
```

All plot and export responses include artifact ids that can be opened through:

```text
http://127.0.0.1:8000/api/artifacts/<artifact_id>
```

## Backend Responsibilities

The upload-session service does the following on the backend:

- Accepts one or more H5 files.
- Stores them in the project `outputs/uploads/` tree.
- Reads H5 metadata with `h5py`.
- Infers `HPM_5` or `HPM_6` from file name and available fields.
- Parses `/UTC_TIME` values as compact UTC-like timestamps for this diagnostic workflow.
- Reads quality flag distributions for `/FLAG_MT`, `/FLAG_SHW`, `/FLAG_TBB`, and `/FLAG_N3` when present.
- Sorts uploaded files by parsed time.
- Detects duplicate file content by hash.
- Removes duplicate time samples for merged plotting/export.
- Splits discontinuous data into time segments so plots do not leave large blank gaps.
- Returns `per_file_records`, `merged_time_range`, `segment_ranges`, `quality_flag_summary`, warnings, errors, and run log actions.
- Computes feature-parameter statistics only from the current upload session's backend-merged rows; the frontend does not sort, dedupe, parse H5, or calculate statistics.

Time semantics and CSES HPM variable meanings still require product-document confirmation before scientific conclusions.

## Feature Statistics

`POST /api/sessions/<upload_session_id>/statistics` runs descriptive statistics on the already parsed upload session. The input is the backend session state after `/UTC_TIME` parsing, UTC sorting, duplicate file/time-sample handling, segment splitting, and optional crop. It does not reopen fixed source data directories from the frontend and does not write to original H5 locations.

The JSON response includes:

- `processing_summary`: uploaded/unique/duplicate file counts, raw and final sample counts, duplicate time samples removed, crop range, segment count, and sorting/deduping flags.
- `overall_statistics`: time coverage, cadence and large-gap summary, magnetic variables, position variables, and quality flags.
- `per_file_statistics`: file-level time/cadence/magnetic/position/quality summaries.
- `per_segment_statistics`: the same descriptive statistics split by continuous time segment.
- `product_type_status`: `single`, `mixed`, or unavailable status. Mixed `HPM_5`/`HPM_6` batches still return per-file statistics, but overall magnetic statistics are marked unavailable with reason `mixed_product_types_not_supported_for_overall_magnetic_stats`.
- `artifacts`: download ids for `statistics.json`, `statistics_summary.csv`, and `manifest.json`.

Magnetic statistics:

- `HPM_5`: `/B_FGM` is summarized as `Bx`, `By`, `Bz`, and `B_abs`.
- `HPM_6`: `/A211` is summarized as `scalar_B`; no synthetic vector components are produced.

Position statistics include available `GEO_LAT`, `GEO_LON`, `ALTITUDE`, `MAG_LAT`, and `MAG_LON` fields. Quality flags include available `/FLAG_MT`, `/FLAG_SHW`, `/FLAG_TBB`, and `/FLAG_N3`; first version only reports distributions and does not apply automatic quality filtering.

Statistics output files:

```text
outputs/statistics/cses_hpm/<upload_session_id>/<digest>/statistics.json
outputs/statistics/cses_hpm/<upload_session_id>/<digest>/statistics_summary.csv
outputs/statistics/cses_hpm/<upload_session_id>/<digest>/manifest.json
```

`statistics_summary.csv` is a flat table for quick spreadsheet viewing with columns such as `scope`, `segment_id`, `variable`, `count`, `min`, `max`, `mean`, `median`, `std`, `q25`, `q75`, `iqr`, and `unit`.

## Frontend Behavior

- The page title is `张衡一号数据分析`.
- `上传文件` is the only way to create a working session.
- Uploading a new set of files clears the previous plot/export state and creates a new session.
- `数据范围` is read from backend `merged_time_range` and segments.
- `裁剪区` uses backend parseable time range; if `/UTC_TIME` cannot be parsed, time crop inputs are disabled.
- `start!` generates the selected plot type.
- `磁场图` and `轨道图` are enabled.
- `频谱图` is disabled with the reason: `频谱图暂未启用：当前 HPM 数据的时频分析规则尚未确认`.
- After `start!`, the frontend also calls the statistics API with the same crop range and displays a compact statistics panel beside the plot preview.
- The statistics panel shows time range, final sample count, segment count, cadence median, duplicate time samples removed, `B_abs` or `scalar_B` summary, `GEO_LAT/GEO_LON/ALTITUDE` ranges, quality flag distributions, and JSON/CSV download links.
- `运行记录` shows file-level records, quality flags, sorted file order, dedupe counts, segments, warnings, errors, and export status.
- Statistics completion appends a concrete run-log line with session id, crop status, final sample count, segment count, duplicate time samples removed, product status, and output path.
- `导出` supports current cropped range and writes a manifest.

## Verify

Backend tests:

```bash
cd /Volumes/Elements/satellite_data_web
PYTHONPATH=/Volumes/Elements/satellite_data_web/backend \
  python -m unittest discover -s backend/tests -v
```

Frontend tests and production build:

```bash
cd /Volumes/Elements/satellite_data_web/frontend
npm test -- --run
npm run build
```

## Real-File Smoke Scenarios

Recommended manual scenarios:

1. Upload one `HPM_5` file and generate magnetic plot and orbit plot.
2. Upload the same file twice and confirm the run log reports duplicate file/sample removal.
3. Upload a later file first and an earlier file second; confirm backend sorting and frontend time range display use the actual parsed time order.
4. Upload non-continuous files and confirm magnetic plot/orbit plot are split by segment instead of leaving empty time gaps.
5. After generating a plot, confirm the statistics panel appears and the JSON/CSV statistics artifacts download.

## Existing Cluster APIs

Cluster datasource APIs and tests still exist. The current upload console does not expose Cluster file/date selection, but Cluster backend routes can still be used directly for existing processed products under `/Volumes/Elements/data/idlpython_v2`.

Cluster production scripts are not run by the web app.

## Known Issues

- Figma contents were not programmatically accessible from this environment, so the current page follows the user-provided screenshot and static assets.
- `/UTC_TIME`, `/B_FGM`, `/A211`, and quality flag meanings are treated as diagnostic upload-session assumptions, not final scientific confirmation.
- Mixed `HPM_5` plus `HPM_6` batch plotting is detected but not plotted.
- Mixed `HPM_5` plus `HPM_6` batch statistics return per-file statistics, but overall magnetic statistics are unavailable until a confirmed mixed-product policy exists.
- Feature statistics are descriptive only. They do not compute spectrograms, STFT, wavelets, Pc5 PSD, disturbance classification, or scientific event identification.
- Spectrogram, Pc5, STFT, wavelet, electric field, and solar-wind products are not enabled for CSES HPM.
- CDF export is reserved/TODO.
- Upload sessions are stored as local output artifacts; there is no persistent database or cleanup scheduler yet.

## Local Config

Optional `local_config.json` at the app root can override:

```json
{
  "cluster_raw_root": "/Volumes/Elements/data/cluster",
  "cluster_processed_root": "/Volumes/Elements/data/idlpython_v2",
  "cses_hpm_root": "/Users/foursoils/Downloads/HPM",
  "outputs_root": "/Volumes/Elements/satellite_data_web/outputs"
}
```

`local_config.json` and `.env` are ignored.
