# CSES HPM Inspection Notes

Last updated: 2026-06-05

## Scope

Phase 2 created and ran the CSES HPM H5 inspection module against the configured local HPM directory:

```text
<local_cses_hpm_root>
```

The inspection is metadata-first and bounded:

- It recursively finds H5/HDF5/HE5 files.
- It walks HDF5 groups and datasets.
- It records attrs, shape, dtype, storage/chunk/compression metadata, head/tail preview, and bounded sample statistics.
- It does not copy raw H5 files into the app directory.
- It does not full-load large arrays.
- All semantic field candidates are marked `inferred` unless their information comes directly from H5 attrs.

## Implemented Files

```text
backend/app/services/cses_h5_inspector.py
backend/scripts/inspect_cses_hpm.py
backend/tests/test_cses_h5_inspector.py
```

The script writes reports under:

```text
<repo>/outputs/cses_hpm_inspection
```

Per H5 file output:

- `h5_tree.json`
- `h5_tree.txt`
- `summary.json`
- `report.md`

Batch output:

- `inspection_index.json`

## Command Run

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

Verification checks:

- Missing per-file outputs: `0`.
- Project raw-data copy check: `0` H5/HDF5/HE5/CDF files under `<repo>`.
- Logical size of non-AppleDouble inspection outputs: about `33.32 MB`.
- Non-AppleDouble inspection file count: `2625`.

## Test Command

```bash
PYTHONPATH=<repo>/backend \
python -m unittest discover \
  -s <repo>/backend/tests \
  -p 'test_*.py' \
  -v
```

Result:

```text
Ran 1 test in 0.026s
OK
```

## Observed H5 Structure

Across 656 files:

- 328 files have 15 datasets.
- 328 files have 10 datasets.
- All inspected files have one root-level group context in the report model; datasets are root-level paths.

Candidate presence by file:

| Candidate type | Files with candidate | Top candidate path |
|---|---:|---|
| time | 656 | `/UTC_TIME` |
| magnetic_vector | 328 | `/B_FGM` |
| latitude | 656 | `/GEO_LAT` |
| longitude | 656 | `/GEO_LON` |
| altitude | 656 | `/ALTITUDE` |
| orbit/context | 656 | `/ALTITUDE`, with lat/lon also listed |
| quality_flag | 656 | `/FLAG_MT` |

Important boundary:

- `/UTC_TIME`, `/VERSE_TIME`, `/B_FGM`, `/GEO_LAT`, `/GEO_LON`, `/ALTITUDE`, and `/FLAG_MT` are currently inferred candidates.
- The web metadata endpoint now reports a mechanically parsed `/UTC_TIME` `time_summary` when parseable, including UTC start/end and cadence min/median/max. This remains `inferred` and does not replace product documentation.
- The web metadata endpoint also reports a `/FLAG_MT` `quality_summary` distribution when readable. This counts observed values only; it does not interpret quality-flag meanings.
- The inspector has not yet confirmed CSES time encoding, coordinate frame semantics, or quality flag bit meanings.

## Example 15-Dataset File

Example report:

```text
outputs/cses_hpm_inspection/
  demo_hpm_inspection_sample/
    report.md
```

Observed datasets in that example include:

- `/UTC_TIME`
- `/VERSE_TIME`
- `/B_FGM`
- `/A221`, `/A222`, `/A223`
- `/GEO_LAT`, `/GEO_LON`
- `/MAG_LAT`, `/MAG_LON`
- `/ALTITUDE`
- `/FLAG_MT`, `/FLAG_SHW`, `/FLAG_TBB`
- `/q_SIM_ECI`

The top magnetic-vector candidate is `/B_FGM`, inferred from shape `[N, 3]`, magnetic/frame-like naming, and nT units in attrs.

## Example 10-Dataset File

Observed 10-dataset files include:

- `/UTC_TIME`
- `/VERSE_TIME`
- `/A211`
- `/GEO_LAT`, `/GEO_LON`
- `/MAG_LAT`, `/MAG_LON`
- `/ALTITUDE`
- `/FLAG_MT`, `/FLAG_N3`

The inspector does not currently promote `/A211` to a vector magnetic field because it is shaped `[N, 1]`. It may be a scalar or single-axis product, but that needs product documentation or deeper metadata confirmation.

## Open Questions

These items must be resolved before CSES plotting/statistics are treated as scientifically reliable:

1. Confirm `/UTC_TIME` encoding scientifically. The web backend now mechanically parses compact `YYYYMMDDHHMMSSmmm` and `YYYYMMDDHHMMSS.mmm` values for bounded time-range reads, but the field remains an inferred candidate until product documentation or mission semantics are verified.
2. Confirm whether `/VERSE_TIME` is mission time, onboard time, or another support time.
3. Confirm `/B_FGM` component order and coordinate frame.
4. Confirm whether `/A221`, `/A222`, `/A223`, and `/A211` are calibrated sensor axes, model components, scalar channels, or intermediate quantities.
5. Confirm meaning of `/FLAG_MT`, `/FLAG_SHW`, `/FLAG_TBB`, and `/FLAG_N3`. The current web quality summary is a value-count display only.
6. Confirm whether `GEO_*` or `MAG_*` should be default trajectory coordinates for the frontend.
7. Confirm sampling cadence and gap policy from parsed time plus product documentation, not from filename duration alone. The current web cadence summary is mechanical context only.

## Next Implementation Step

Phase 3 should build the backend datasource abstraction and the CSES minimal API on top of these inspection summaries:

- list CSES files and inspection status
- read per-file metadata from `summary.json`
- list candidate variables with confidence/evidence
- provide sample-index preview for selected datasets
- keep `/UTC_TIME` parser confidence as `inferred` until product documentation confirms semantics, cadence, and edge cases
