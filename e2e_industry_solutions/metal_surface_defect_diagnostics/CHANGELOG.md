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

## [1.3.0] - 2026-11-18

Phase 3 - model (branch `feature/msd-phase3-model`).

### Added

* `src/pipeline/02_train.ipynb`: MobileNetV3-Small transfer learning on serverless CPU (CPU
  PyTorch 2.5.1 / torchvision 0.20.1, AdamW + cosine, 8 epochs, best-val checkpoint), MLflow
  tracking, pyfunc packaging (base64 image in; `predicted_class`, `confidence`, `probabilities`
  out) with signature and input example, isolated `uv` serving-readiness check, and UC
  registration of `msd_defect_classifier`.
* `src/pipeline/04_evaluate.ipynb`: test-split accuracy, per-class precision/recall/F1 and
  confusion matrix logged to the version's MLflow run and appended to `model_eval_metrics`;
  promotion gate sets `@champion` at test accuracy >= `min_test_accuracy` (0.90).
* `src/pipeline/05_deploy_endpoint.ipynb`: create or update the serving endpoint pinned to the
  exact `@champion` version (CPU, Small, scale-to-zero), wait for READY, smoke test.
* `resources/msd.experiment.yml`: per-target MLflow experiment.
* Job tasks `train` -> `evaluate` -> `deploy_endpoint` and parameters `model_name`,
  `experiment_path`, `epochs`, `min_test_accuracy`, `serving_endpoint`; job timeout 2 h.
* Bundle variables `min_test_accuracy` and `train_epochs`.

### Changed

* `dev` target overrides `serving_endpoint` to `msd-defect-classifier-dev` (endpoint names are
  workspace-global and are not prefixed by development mode).

### Fixed

* Model serving requirements pin `torch==2.5.1` / `torchvision==0.20.1` without the `+cpu` local
  tag. The `+cpu` builds exist only for x86_64, so the isolated serving-readiness check failed
  whenever serverless placed the `train` task on an aarch64 machine.
* Experiment resource key renamed to `msd_classifier` (bundle resource keys must be unique across
  resource types; `msd` is the schema).

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
