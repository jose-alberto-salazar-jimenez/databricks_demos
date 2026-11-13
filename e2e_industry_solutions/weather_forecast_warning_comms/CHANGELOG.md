# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH).

How to use:

* Every pull request adds its entries under `[Unreleased]` (Added, Changed, Fixed, Removed).
* When the PR is merged, the `[Unreleased]` entries move under a new version with the date:
  MAJOR for breaking changes (e.g. table or API contract), MINOR for new features, PATCH for fixes.

## [Unreleased]

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
