# Synthetic admin analytics API â€” phase 1

Base: `/api/v1/admin/analytics/`. Every endpoint requires an active, email-verified administrator through the existing cookie authentication. POST requires the existing CSRF header/cookie. No endpoint returns patient IDs, source keys, names, contact details, notes, individual coordinates, or ground-truth labels.

All results explicitly describe **synthetic station-area distributions**, not outbreaks, incidence, transmission or diagnosis. A displayed patient count from 1â€“4 is `null` with `suppressed: true`; zero is reported as zero. Cluster geometry is absent for groups below five. Overlapping line memberships mean line totals must not be added.

## Filters and defaults

Use the same flat object for summary query parameters and run POST JSON:

```json
{"dataset_id":"mumbai_stations_v1","disease_code":"DENGUE","line":"","station_id":"","date_from":"2026-09-01","date_to":"2026-09-29"}
```

`disease_code`, `line`, `station_id` use `""` for all in summaries. Clustering/evaluation require one disease (`DENGUE` default). Lines are `Central`, `Western`, `Harbour`; station membership must match a selected line. Dates are inclusive UTC calendar days; maximum window 366 days. Unknown fields and invalid filters return 400 using the existing `{code,detail,errors?,request_id}` envelope. An unimported dataset returns 404.

## GET catalog/

```json
{"synthetic":true,"suppression_threshold":5,"datasets":[{"dataset_id":"mumbai_stations_v1","as_of":"2026-09-29","observation_start":"2025-09-30","generator_version":"1.0.0","patient_count":1000}],"diseases":[{"disease_code":"DENGUE","label":"Dengue"}],"stations":[{"station_id":"KURLA","station_name":"Kurla","lines":["Central","Harbour"],"latitude":19.0,"longitude":72.8}],"lines":["Central","Western","Harbour"],"defaults":{"dataset_id":"mumbai_stations_v1","disease_code":"DENGUE","line":"","station_id":"","date_from":"2026-09-01","date_to":"2026-09-29","radius_km":0.5,"min_samples":5}}
```

Catalog accepts optional `dataset_id`; station anchors are public reference coordinates, never patient points. Empty deployment returns empty arrays and defaults.

## GET summary/

Summary permits all diseases (default `disease_code=""`). Response:

```json
{"synthetic":true,"dataset_id":"mumbai_stations_v1","filters":{},"suppression_threshold":5,"counts":{"distinct_patients":151,"observations":300,"patient_disease_pairs":151,"missing_coordinates":0,"first_recorded_episodes_in_window":150},"diseases":[{"disease_code":"DENGUE","label":"Dengue","patient_count":151,"suppressed":false}],"stations":[{"station_id":"KURLA","station_name":"Kurla","lines":["Central","Harbour"],"patient_count":50,"suppressed":false}],"lines":[{"line":"Central","patient_count":50,"suppressed":false}],"age_bands":[{"age_band":"20s","patient_count":25,"suppressed":false}],"notes":["Line memberships overlap; do not add line totals."]}
```

Counts mean patients with recorded observations. Deduplication is latest observation per patient/disease within the filter window. First-recorded episode counts derive first observations from complete batch history before applying the window. All count fields may be null for small cells.

`weekly` is an additional array of `{week_start, patient_count, suppressed, first_recorded_episode_count}`. Week starts are Mondays; the first/last weeks include only the selected date range. Patient counts are distinct within each week and are not additive. Episode counts use complete-history first-observed dates.

## POST cluster-runs/

Body: filters plus `radius_km` (0.1â€“3; default 0.5) and `min_samples` (3â€“30; default 5). Synchronous, bounded to 5,000 deduplicated points. Returns 201 for a new run, 200 for reuse.

```json
{"id":"uuid","kind":"cluster","status":"completed","reused":false,"created_at":"ISO timestamp","synthetic":true,"dataset_id":"mumbai_stations_v1","filters":{},"parameters":{"radius_km":0.5,"min_samples":5},"runtime_ms":25,"versions":{"service":"1.0.0","scikit_learn":"...","numpy":"..."},"result":{"counts":{"eligible_patients":null,"with_coordinates":null,"missing_coordinates":0,"clustered_patients":150,"noise_patients":null,"cluster_count":3},"metrics":{"noise_fraction":null,"silhouette":{"value":0.9,"reason":null,"sample_size":150,"coverage":null}},"clusters":[{"cluster":0,"patient_count":50,"suppressed":false,"centroid":{"latitude":19.0,"longitude":72.8},"bounds":{"south":18.9,"north":19.1,"west":72.7,"east":72.9},"stations":[{"station_id":"KURLA","station_name":"Kurla","patient_count":50,"suppressed":false}]}],"notes":[]}}
```

Related cohort totals and ratios can also be null when subtracting them would reveal a small noise or missing-coordinate count. For a suppressed cluster: count null, suppressed true, centroid/bounds null, stations empty. Centroids/bounds are rounded to three decimals. Silhouette value is null plus a reason for empty/tiny/all-noise/one-cluster/undefined cohorts; sampled pairwise work is bounded. No planted truth is loaded for ordinary clustering. The examples illustrate shape only, not expected numeric results.

Ratios and related totals may also be null when they would directly reconstruct a suppressed small cell. For example, a one-patient noise group suppresses `noise_fraction`, silhouette `coverage`, and the related eligible/coordinate totals. `metrics.noise_fraction_reason` explains an unavailable ratio. These safeguards do not provide formal privacy against combinations of overlapping filters; this release remains restricted to explicitly synthetic data.

## GET cluster-runs/<uuid>/ and GET evaluation-runs/<uuid>/

Returns the saved envelope above (`reused: true`). GET never fits a model. A run of the wrong kind or missing ID returns 404.

## POST evaluation-runs/

Same filters and optional selected `radius_km` / `min_samples`. Optional `seed` (0â€“2147483647; default 20260929), `stability_repeats` (3â€“8; default 3). Evaluates a fixed 16-combination grid: radius `[0.3,0.5,0.8,1.2]` and min_samples `[4,5,8,12]`. Returns a saved/reused run envelope with `kind: "evaluation"` and:

```json
{"grid":[{"radius_km":0.5,"min_samples":5,"cluster_count":3,"noise_fraction":null,"silhouette":{"value":0.9,"reason":null,"sample_size":150,"coverage":null}}],"selected":{"radius_km":0.5,"min_samples":5},"stability":{"seed":20260929,"subsample_fraction":0.8,"perturbation_km":0.03,"repeats":[{"repeat":1,"shared_patients":120,"retained_fraction":0.8,"noise_fraction":0.0,"adjusted_rand_index":{"value":0.98,"reason":null}}],"mean_adjusted_rand_index":{"value":0.98,"reason":null}},"synthetic_pattern_recovery":{"adjusted_rand_index":{"value":0.98,"reason":null},"evaluated_patients":151,"coverage":1.0,"background_convention":"BACKGROUND is one reference group; all DBSCAN noise is one predicted group.","reason":null},"counts":{},"notes":[]}
```

Ground truth is used only after fitting and only for patients whose primary disease matches the selected disease. ARI is synthetic pattern recovery, never diagnostic accuracy. Stability compares shared retained patients across seeded 80% subsets with 30m coordinate perturbations. No automatic best-parameter or deployment claim. The default September scenario is deliberately easy; independent seed/harder scenarios remain necessary for generalization evidence.

## Project wiring

The project includes `analytics.apps.AnalyticsConfig` in INSTALLED_APPS and `path("api/v1/admin/analytics/", include("analytics.urls"))` in config URLs. Pinned scikit-learn and NumPy dependencies are in the backend requirements. Run analytics migrations on the dedicated synthetic target. After clinical import, run `import_synthetic_analytics` (dry-run by default, `--apply` explicit) using its default manifest/sidecar/clinical mapping paths.
