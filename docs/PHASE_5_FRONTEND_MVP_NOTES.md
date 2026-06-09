# Phase 5 Frontend MVP Notes

Last updated: 2026-06-05

## Scope

Phase 5 adds a Vite + React frontend under `/Volumes/Elements/satellite_data_web/frontend`.

The MVP is a working science dashboard, not a landing page:

- API health indicator.
- Datasource switcher for `cluster` and `cses_hpm`.
- Cluster 2005 processed-date browser.
- Cluster metadata and variable inventory view.
- Cluster B/E/POS quicklook buttons that request existing backend artifacts.
- CSES HPM file browser from inspection index.
- CSES metadata and variable inventory view.
- CSES bounded sample-index preview table for selected variables.
- Data context strip for current file, selected variables, units, sample-index range, and inferred time/quality candidates.
- Processing log area for recent preview/plot/stats/export actions.
- Disabled export/statistics controls with Phase 6 status.

## Frontend Files

- `frontend/package.json`: Vite/React scripts and dependencies.
- `frontend/vite.config.ts`: React plugin, Vitest setup, and `/api` proxy to `http://127.0.0.1:8000`.
- `frontend/src/api.ts`: typed API client for current backend endpoints.
- `frontend/src/lib/format.ts`: UI formatting helpers for artifact URLs, labels, product availability, and preview tables.
- `frontend/src/App.tsx`: main dashboard state and views.
- `frontend/src/styles.css`: responsive scientific dashboard layout.
- `frontend/src/App.test.tsx`: render-level smoke test for the Cluster MVP workspace and datasource-switch regression coverage.
- `frontend/src/lib/format.test.ts`: helper behavior tests.

## Data Boundaries

- The frontend never reads local H5, CDF, NPZ, parquet, or PNG paths directly.
- Cluster quicklooks are requested through `POST /api/datasources/cluster/plot`, then displayed through `GET /api/artifacts/{artifact_id}`.
- CSES preview uses `POST /api/datasources/cses_hpm/subset` with `sample_index` ranges only.
- CSES time parsing, CSES spectrograms, export, and statistics remain future phases.

## Verification

Commands run on 2026-06-05:

```bash
cd /Volumes/Elements/satellite_data_web/frontend
npm test
```

Result:

```text
Test Files  2 passed (2)
Tests  8 passed (8)
```

```bash
cd /Volumes/Elements/satellite_data_web/frontend
npm run build
```

Result:

```text
tsc -b && vite build
1581 modules transformed.
built in 1.49s
```

```bash
cd /Volumes/Elements/satellite_data_web/frontend
npm audit --json
```

Result:

```text
0 vulnerabilities
```

```bash
PYTHONPATH=/Volumes/Elements/satellite_data_web/backend \
  python -m unittest discover -s /Volumes/Elements/satellite_data_web/backend/tests -p 'test_*.py' -v
```

Result:

```text
Ran 3 tests in 0.528s
OK
```

Safety check:

```bash
find /Volumes/Elements/satellite_data_web -type f \( -name '*.h5' -o -name '*.hdf5' -o -name '*.cdf' \) -print
```

Result: no raw H5/CDF files found in the app tree.

## Runtime Notes

The frontend dev server expects the backend on `http://127.0.0.1:8000` and serves the app on `http://127.0.0.1:5173`.

The frontend excludes macOS AppleDouble `._*` sidecar files from Vitest and TypeScript because the project lives on an external volume where these metadata files may be generated.

## Runtime Regression

Browser verification found a stale datasource-switch request: after viewing a Cluster date, switching to CSES briefly requested CSES metadata for the old Cluster date ID.

Fix:

- `frontend/src/App.tsx` now clears selected file/detail state before changing datasource.
- `frontend/src/App.test.tsx` includes a regression test that rejects CSES metadata/variable calls with the prior Cluster date.
