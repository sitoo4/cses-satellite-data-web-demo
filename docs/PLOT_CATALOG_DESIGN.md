# Plot Catalog Design

Last updated: 2026-06-05

## Goal

The frontend must not hard-code one fixed plot toolbar for every datasource. Cluster and CSES HPM have different instruments, file formats, field semantics, and scientific boundaries. The backend owns the plot capability declaration through:

```text
GET /api/datasources/{name}/plot-catalog?file_id=<id>
```

## Response Shape

Each catalog item includes:

- `plot_type`
- `display_name`
- `description`
- `enabled`
- `disabled_reason`
- `required_fields`
- `confirmed_fields`
- `inferred_fields`
- `output_group`

The datasource response also includes `datasource_type`, such as:

- `Cluster CDF multi-instrument datasource`
- `CSES-01 HPM magnetometer-only H5 datasource`

## Frontend Behavior

The frontend renders catalog cards from the backend response. Enabled items get a generate button. Disabled items show the backend disabled reason and keep the button disabled.

This prevents CSES HPM from appearing to support Cluster-only products such as electric-field or solar-wind context plots. It also prevents Cluster from relying on old quicklook PNGs as formal Web output.

## Current Cluster Catalog

- `cluster_magnetic_overview`: enabled when `segment_B_MFA_after_delete` is available
- `cluster_electric_overview`: enabled when `segment_E_MFA` is available
- `cluster_spectrogram_overview`: enabled when B/E PSD arrays and axes are available
- `cluster_solar_wind_overview`: disabled/unavailable until processed solar-wind/context fields are validated
- `cluster_orbit_overview`: enabled when `segment_MLT`, `segment_MLAT`, and `segment_L` are available

## Current CSES HPM Catalog

- `cses_hpm_magnetic_overview`: enabled from inspector-inferred HPM magnetic vector fields
- `cses_hpm_quality_overview`: enabled from inspector-inferred quality flags such as `/FLAG_MT`
- `cses_hpm_trajectory_overview`: enabled only when direct geographic lat/lon/alt fields are present
- `cses_hpm_cadence_overview`: enabled when an inferred time field such as `/UTC_TIME` is present
- `cses_hpm_batch_statistics_overview`: enabled as a statistics endpoint workflow
- `cses_hpm_spectrogram_overview`: disabled until time semantics, cadence, magnetic variable, and quality masking are confirmed
- `cses_hpm_electric_field_overview`: disabled because HPM is magnetometer-only
- `cses_hpm_solar_wind_overview`: disabled because HPM files do not contain OMNI/solar-wind context

## Error And Gap Semantics

Expected gaps return structured responses rather than crashes:

- `unsupported`: not a feature of this datasource
- `unavailable`: expected fields or processed arrays are missing for this file/date
- `disabled_reason`: pre-flight catalog reason shown by the frontend
- `missing_fields`: plot request reason for a specific file/date

Successful plot responses include the Web-owned artifact path and a processing log.
