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
