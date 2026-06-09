# CSES HPM Plot Design

Last updated: 2026-06-05

## Policy

CSES HPM plots are designed from H5 inspector output. The public demo exposes only CSES-01 HPM magnetometer plots and sanitized static derivatives.

```text
<local_cses_hpm_root>
```

Generated HPM plot artifacts are written under:

```text
<repo>/outputs/generated_plots/cses_hpm/
```

The backend does not write to `<local_cses_hpm_root>` and does not modify source H5 files.

## Implemented HPM Catalog Plots

### `cses_hpm_magnetic_overview`

- Field basis: inspector `magnetic_vector` candidate, defaulting to `/B_FGM`
- Figure content: B1/B2/B3 components plus `|B_vector|`
- Metadata: field path, unit when present, coordinate system `unconfirmed`, time field and confidence
- Boundary: coordinate system and HPM variable semantics remain inferred unless confirmed by H5 attrs or external documentation

### `cses_hpm_quality_overview`

- Field basis: inspector `quality_flag` candidate, defaulting to `/FLAG_MT`
- Figure content: flag by sample/time and flag distribution
- Boundary: flags are diagnostic only. The current stage does not remove or mask samples automatically.

### `cses_hpm_trajectory_overview`

- Field basis: direct H5 latitude, longitude, and altitude candidates
- Figure content: lon-lat track, altitude over sample/time, lat/lon over sample/time
- Boundary: no derived magnetic-coordinate plot is shown unless a future verified CSES coordinate conversion is added

### `cses_hpm_cadence_overview`

- Field basis: inspector time candidate, defaulting to `/UTC_TIME`
- Figure content: sampling interval sequence, interval histogram, duplicate count, gap count
- Boundary: plot marks time semantics as inferred. It is a diagnostic for whether later spectrogram work is safe.

### `cses_hpm_batch_statistics_overview`

- Workflow: use `POST /api/datasources/cses_hpm/stats` with selected `file_ids`
- Current statistics: sorted/deduplicated candidate time rows, B component statistics, `|B|`, flag distribution, spatial coverage, cadence, and missing ratio
- Boundary: data engineering statistics only; no physical interpretation is added

## Disabled HPM Capabilities

### `cses_hpm_spectrogram_overview`

Disabled reason:

```text
requires confirmed time semantics, cadence, magnetic variable, and quality masking
```

This remains disabled even if `/UTC_TIME` can be mechanically parsed, because parsing is not the same as confirmed mission time semantics or validated quality masking.

### Electric Field And Solar Wind

CSES HPM does not expose electric-field data or external solar-wind context in the current datasource. The catalog items remain disabled with:

```text
not available for CSES HPM magnetometer-only datasource
```

These features remain disabled until product-specific rules and inputs are confirmed.
