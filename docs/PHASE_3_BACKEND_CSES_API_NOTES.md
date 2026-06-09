# Phase 3 Backend CSES API Notes

Last updated: 2026-06-04

## Scope

Phase 3 implemented the first backend datasource abstraction and CSES HPM minimal API. It uses the phase-2 inspection summaries and reads bounded samples from raw H5 files only when requested by `file_id` and dataset path.

Implemented now:

- config loader
- datasource base class and registry
- registered datasource summaries for `cluster` and `cses_hpm`
- CSES file listing from `inspection_index.json`
- CSES metadata from per-file `summary.json`
- CSES variable descriptors from inspection candidates
- CSES sample-index subset preview from raw H5
- FastAPI health and datasource routes

Not implemented in this phase:

- Cluster processed-output endpoints
- CSES time parsing
- CSES time-range subset
- plot/export/stats jobs
- frontend

## Added Files

```text
backend/app/main.py
backend/app/core/config.py
backend/app/datasources/base.py
backend/app/datasources/registry.py
backend/app/datasources/cluster.py
backend/app/datasources/cses_hpm.py
backend/app/api/routes_health.py
backend/app/api/routes_datasources.py
backend/tests/test_cses_datasource_api.py
```

Existing phase-2 files were reused:

```text
backend/app/services/cses_h5_inspector.py
backend/scripts/inspect_cses_hpm.py
```

## API Endpoints Implemented

```text
GET  /api/health
GET  /api/datasources
GET  /api/datasources/{name}/files
GET  /api/datasources/{name}/metadata
GET  /api/datasources/{name}/variables
POST /api/datasources/{name}/subset
```

Current CSES subset support is `sample_index` only. If a request uses `time` mode, the datasource returns an unsupported response because `/UTC_TIME` parsing has not been confirmed.

## Verification Commands

Unit/API tests:

```bash
PYTHONPATH=<repo>/backend \
python -m unittest discover \
  -s <repo>/backend/tests \
  -p 'test_*.py' \
  -v
```

Result:

```text
Ran 2 tests in 0.035s
OK
```

Real CSES inspection refresh after candidate-rule update:

```bash
python <repo>/backend/scripts/inspect_cses_hpm.py \
  --input-root <local_cses_hpm_root> \
  --output-root <repo>/outputs/cses_hpm_inspection \
  --max-preview 8 \
  --sample-size 2048
```

Result:

```json
{
  "file_count": 656,
  "ok_count": 656,
  "error_count": 0
}
```

Real API smoke command:

```bash
PYTHONPATH=<repo>/backend python - <<'PY'
from fastapi.testclient import TestClient
from app.main import create_app

client = TestClient(create_app())
print(client.get("/api/health").status_code)
print([d["name"] for d in client.get("/api/datasources").json()["datasources"]])
files = client.get("/api/datasources/cses_hpm/files", params={"limit": 1}).json()["files"]
file_id = files[0]["file_id"]
print(file_id)
print(len(client.get("/api/datasources/cses_hpm/variables", params={"file_id": file_id}).json()["variables"]))
print(client.post(
    "/api/datasources/cses_hpm/subset",
    json={
        "file_id": file_id,
        "variables": ["/UTC_TIME"],
        "range": {"mode": "sample_index", "start_index": 0, "end_index": 3},
        "preview_limit": 3,
    },
).json()["range"])
PY
```

Result summary:

- `/api/health`: `200`, status `ok`
- `/api/datasources`: `cluster`, `cses_hpm`
- first real CSES file listed
- first real CSES variables count: `15`
- sample-index subset preview returned 3 samples

## Candidate Rule Update

During phase 3, the inspector time-candidate rule was corrected to recognize paths like `/UTC_TIME` and `/VERSE_TIME`, not only names separated by word boundaries.

After refreshing all reports:

- `/UTC_TIME` is the top inferred time candidate in real summaries.
- `/VERSE_TIME` is also listed as an inferred time-like support candidate where present.

These remain inferred candidates, not confirmed final time semantics.

## Safety Notes

- CSES file access resolves `file_id` under the configured `cses_hpm_root`.
- Absolute-path style traversal outside the root is rejected.
- The frontend/API should pass stable relative file IDs, not arbitrary paths.
- Sample previews read only the requested sample-index interval and selected variables.
- No raw H5/HDF5/HE5/CDF files were copied into the app source tree.

## Next Phase

Phase 4 should connect Cluster existing processed outputs:

- list processed Cluster dates from `daily_full`, `daily_compact`, quicklook, and manifests
- expose metadata for one date
- expose variable descriptors from `daily_full` keys and `daily_compact` columns
- return existing B/E/POS quicklook paths through a controlled artifact route
- keep production reruns disabled unless a later explicit administrative endpoint is designed
