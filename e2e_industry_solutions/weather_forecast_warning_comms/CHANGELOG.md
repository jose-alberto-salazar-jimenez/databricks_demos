# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH).

How to use:

* Every pull request adds its entries under `[Unreleased]` (Added, Changed, Fixed, Removed).
* The last commit of the same PR moves them under the new version with the expected merge date
  (no separate changelog PRs): MAJOR for breaking changes (e.g. table or API contract), MINOR for
  new features, PATCH for fixes and configuration.

## [Unreleased]

## [1.4.0] - 2026-11-28

### Added

* Risk flags in `gold.location_weather_summary` (next 3 days): heavy rain >= 50 mm/day, extreme
  heat (apparent) >= 41 C, strong wind (gusts) >= 60 km/h, plus 3-day maxima and `warnings`.
* `silver.dim_town`: 109 main towns (GeoNames) mapped to the nearest land cell.
* `gold.advisories`: `ai_query` advisories per town, language (ES/EN) and user type, fallback model
  on failure, `numbers_ok` guardrail column and `numbers_from_forecast` expectation.
* `evidence/phase3_advisories.md` with counts, guardrail results and a reviewed sample.

### Changed

* LLM variables use Unity Catalog model service names (`system.ai.qwen3-next-80b-a3b-instruct`,
  fallback `system.ai.gpt-oss-20b`) and are passed to the pipeline configuration.
* PLAN.md rewritten as the PoC scope: every FE Bar stage at its smallest working size, GenAI
  advisories on rule-based risk flags, deferred items with reasons (DECISIONS.md #15).
* `ingest_sources` notebook in source format (`.py`, same cells; was `.ipynb`).
* ARCHITECTURE.md and README.md describe the PoC as built (no model endpoint, risk scores,
  feedback sync or column masks); evidence for phases 1-2 merged into one file.

### Removed

* History backfills (FE Bar size limits): `history_lib.py`, `backfill_sources`, `backfill.job.yml`,
  the `backfill_*` variables and the ERA5 source entry; last version in commit 7a9aad3.
* `evidence/phase3_pipeline.md`, merged into `evidence/phase1_2_foundation_ingestion.md`.

## [1.3.0] - 2026-11-28

### Added

* Medallion pipeline (`resources/medallion.pipeline.yml`, serverless SDP, SQL in `src/pipeline/`):
  bronze streaming tables `open_meteo_forecast_raw`, `enso_oni_raw`, `gdacs_events_raw` (Auto Loader
  on the landing volume); silver `dim_location`, `weather_forecast_daily` (daily arrays exploded),
  `enso_phase_monthly` (ONI parsed, phase at +/-0.5), `extreme_events` (deduplicated); gold
  `location_weather_summary` (today, past and next-days stats, latest ENSO phase). Expectations on
  ids, dates, coordinates and plausible ranges.
* `daily_refresh` job: `medallion` pipeline task after `ingest_sources`.
* `evidence/phase3_pipeline.md` with the Costa Rica test run, the full-grid run and the lake fix.

### Changed

* Workspace host moved to the new workspace (`dbc-9ce31297-2bf5`); catalogs and schemas recreated.
* Land grid v2 (`reference/grid_cells_v2`, `source_registry.GRID_DIR`): Natural Earth 10m lakes are
  removed, 8,060 -> 8,041 cells (14 Lago Titicaca, 5 Lago Gatun). Most forecast models gave Titicaca
  cells lake-surface highs near -10 C. Other cell ids are unchanged; v1 is kept for audit. New source
  `natural_earth_lakes`; backfills build the grid if it is missing.

### Fixed

* Silver forecast keeps the latest ingest per cell, run_date and request_mode, so overlapping
  re-runs of a run_date (test subset, then full grid) no longer duplicate cells.

### Removed

* To stay within the 30-file limit: the three bronze SQL files are merged into
  `src/pipeline/bronze/raw_sources.sql` (same tables and flows, so no reprocessing), and
  `evidence/phase1_foundation.md` + `phase2_ingestion.md` into `evidence/phase1_2_foundation_ingestion.md`.

### Known issues

* A GDACS outage (HTTP 400 / timeouts) fails `ingest_sources` and therefore the whole daily run.

## [1.2.1] - 2026-11-20

### Changed

* Backfill job: optional daily schedule at 11:00 America/Bogota via `backfill_pause_status`, and
  scheduled-run mode via `backfill_default_mode`. Prod: `UNPAUSED` + `history` during the history
  backfill window; dev and the default stay `PAUSED`.
* Changelog process: version bump is the last commit of each feature PR.

## [1.2.0] - 2026-11-20

### Added

* Phase 2 ingestion: `src/ingestion/ingest_sources` notebook landing Natural Earth boundaries,
  a land grid (8,060 cells), GeoNames towns, NOAA ONI, GDACS events and Open-Meteo daily
  forecasts into the landing volume, with retries, free-tier rate limiting and resumable batches.
* `resources/daily_refresh.job.yml`: daily job (05:00 America/Bogota) running the ingestion task.
* `evidence/phase2_ingestion.md` with the Costa Rica test run.
* Backfills: `src/ingestion/backfill_sources` notebook and `resources/backfill.job.yml` (manual).
  `mode=recent`: past 11 days + today for all cells (forecast API). `mode=history`: 2-year ERA5
  reanalysis (Open-Meteo archive API) for GDACS-event cells + 60 random cells per country. Runs
  stop at `max_calls` and resume on the next run.
* Data-source lineage: `source_registry.py` (sources, licenses, resolution); every landed row has
  `data_source`, `source_url`, `source_model`, `request_mode`; manifest
  `reference/data_sources/sources.jsonl` for a `dim_data_source` table. GDACS queries now page.

### Changed

* Dev target uses its own catalog `weather_forecast_warnings_comms_dev` (bronze/silver/gold); the
  dev landing volume is now `landing` there (was `dev_<user>_landing` in the prod catalog).
* New `refresh_pause_status` variable; prod daily schedule starts PAUSED during the backfill window.
* Forecast horizon is +/- 11 days (was 16 days ahead): daily request = yesterday + today + 11 days
  (1 Open-Meteo call per point); past 11 days built from stored runs plus a one-off backfill.
* Ingestion notebook and job: new `past_days`, `forecast_days` and `daily_call_budget` parameters;
  weighted call count and a guard that stops runs over the daily budget.
* Grid counts in docs replaced with measured values (8,060 points).
* Ingestion helpers (HTTP retry, rate limiter, writers, call weighting) and per-source functions
  moved from the notebook to `src/ingestion/ingest_lib.py`; the notebook keeps parameters and
  orchestration only (notebook 15.1k -> 6.6k chars, module 8.1k, both under the 9k read limit).
* Ingestion code split into `ingest_lib.py` (core + generic Open-Meteo downloader with a
  `stop` budget mode and shared rate limiter), `context_lib.py` (grid, GeoNames, ENSO, GDACS) and
  `history_lib.py` (ERA5 sample); `ingest_lib` keeps compatible `land_reference/enso/gdacs` names.

### Fixed

* Forecast resume skipped batches by index only, so a re-run on the same `run_date` with other
  countries or `max_points` skipped the wrong cells. Batch files are now named
  `batch_<index>_<fingerprint>.jsonl` (hash of horizon + cell ids) and only identical requests skip.
* Landing files are written to `.tmp` and renamed, so an interrupted run leaves no partial file.

## [1.1.0] - 2026-11-12

### Added

* Bundle skeleton: `databricks.yml` (variables for catalog, schemas, refresh schedule, LLM
  endpoints; `dev` and `prod` targets) and `resources/landing.volume.yml`.
* Managed landing volume in `bronze` (dev: `dev_<user>_landing`, prod: `landing`).
* `evidence/phase1_foundation.md` with validate/deploy output.

## [1.0.0] - 2026-11-11

### Added

* Project folder `e2e_industry_solutions/weather_forecast_warning_comms`.
* Unity Catalog catalog `weather_forecast_warnings_comms` with `bronze`, `silver`, `gold` schemas.
* Documentation: README.md, ARCHITECTURE.md, PLAN.md, DECISIONS.md, CHANGELOG.md.
* Decisions: daily refresh; 20 km / 10 km grid plus all towns; Dash app; open low-cost LLM.
