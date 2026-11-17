# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH).

How to use:

* Every pull request adds its entries under `[Unreleased]` (Added, Changed, Fixed, Removed).
* When the PR is merged, the `[Unreleased]` entries move under a new version with the date:
  MAJOR for breaking changes (e.g. table schema, model signature or app contract), MINOR for new
  features, PATCH for fixes.
* Playbook content changes are always logged here with the new `playbook_version`.

## [Unreleased]

## [1.2.0] - 2026-11-17

Phase 2 - data and playbook (branch `feature/msd-phase2-data`).

### Added

* `src/pipeline/01_ingest.ipynb`: extract the NEU zip into
  `raw/images/<source_split>/<class>/`, Auto Loader (`binaryFile`, `availableNow`) into
  `image_bronze`, deterministic split into `image_index` (Kaggle train -> train; Kaggle
  validation -> 30 val + 30 test per class), and data checks.
* `src/playbook/defect_playbook.yaml`: SME defect playbook `playbook_version` 1.0.0 (draft,
  pending SME review), one entry per NEU class with base severity, inspection, repair,
  monitoring and escalation guidance.
* `src/pipeline/03_playbook.ipynb`: validate the playbook YAML and load the `defect_playbook`
  Delta table (playbook index).
* `resources/msd_training.job.yml`: `msd_training` job (serverless) with `ingest` and `playbook`
  tasks, parameters from bundle variables.

### Changed

* Split strategy: keep the dataset's published train/validation split instead of a hash-based
  70/15/15 split (PLAN, ARCHITECTURE, README updated).

## [1.1.0] - 2026-11-16

Phase 1 - foundation (branch `feature/msd-phase1-foundation`).

### Added

* Bundle skeleton: `databricks.yml` (variables for catalog, schema, raw volume, model name,
  serving endpoint, LLM endpoint, SQL warehouse, confidence threshold; `dev` and `prod` targets).
* `resources/msd.schema.yml`: bundle-owned schema `metal_surface_defects`.
* `resources/msd.volume.yml`: managed volume `raw` (`zip/` upload area, `images/` extraction area).

### Changed

* README: document the dev schema prefix (`dev_<user>_metal_surface_defects`) and the Kaggle
  archive layout (`NEU-DET/{train,validation}/images/<class>/`).

## [1.0.0] - 2026-11-16

### Added

* Project folder `e2e_industry_solutions/metal_surface_defect_diagnostics` in the
  `databricks_demos` repository.
* Approved solution scope and reference architecture (build plane and serve plane).
* Documentation: README.md, ARCHITECTURE.md, PLAN.md, CHANGELOG.md.
* Decisions: NEU dataset (6 classes, manual upload to a UC Volume), Auto Loader ingestion, CPU
  transfer learning with MLflow and UC registry, Model Serving, Streamlit Databricks App,
  `databricks-meta-llama-3-3-70b-instruct` grounded on a versioned SME defect playbook.
