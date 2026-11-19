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

### Documentation

* Planned reviewer access and supervision (not built): roles (field engineer, reviewer group,
  supervisor group), app-side or Unity Catalog-enforced checks, four-eyes sign-off for verdicts
  that change the outcome, audit view (ARCHITECTURE 10.1, PLAN section 13 backlog).
* Recommended enhancements with estimates (PLAN section 13, not built): Phase 5a demo
  reliability (calibration + OOD rejection, vision-model second opinion, asset context, endpoint
  warm-up) and Phase 5b MLOps loop (retrain from reviews, champion-vs-challenger gate, inference
  logging + drift monitoring, MLflow tracing + judges).
* Notes for consideration (PLAN section 13): Genie space for supervisors, CI/CD with a service
  principal, separate dev and prod catalogs, review-image retention; Vector Search and GPU
  training not needed at POC scale.

## [1.4.1] - 2026-11-19

First prod deployment and a review-flow fix.

### Fixed

* **Send to expert review** recorded a verdict instead of opening a case when the user filled
  in the "Review it now" form below it. The Diagnose tab now only requests reviews (optional
  suspected class and note); verdicts are recorded only on the Review cases tab.

### Deployed

* prod: schema `metal_surface_defects`, job `msd_training` (all tasks green; model v1
  `@champion`, test accuracy 1.00 on 180 images), endpoint `msd-defect-classifier`, app
  `msd-diagnostics`.

### Documentation

* README / ARCHITECTURE: two-pass first deployment of a target, app creation needs the
  deployer's own credentials, run bundle commands from the bundle root.

## [1.4.0] - 2026-11-19

Phase 4 - app (branch `feature/msd-phase4-app`).

### Added

* Streamlit Databricks App `resources/msd_app.app.yml` + `src/app/` (`msd-app-dev` in dev,
  `msd-diagnostics` in prod), running as its own service principal with six resources:
  classifier endpoint and LLM (CAN_QUERY), SQL warehouse (CAN_USE), `defect_playbook` (SELECT),
  `diagnosis_feedback` (MODIFY) and the `raw` volume (WRITE_VOLUME).
* Diagnosis flow: classify (scale-to-zero aware, 300 s HTTP timeout), severity and human-review
  rules, playbook lookup through the SQL warehouse, grounded report from the Foundation Model with
  a source line, and the reviewed playbook entry as a fallback when the LLM is unavailable.
* Mobile-first UI: phone-width column, app bar, **Diagnose** and **Review cases** tabs, one image
  per analysis (upload or camera, up to 10 MB) with an explicit **Analyze image** step and
  **New analysis** reset, result card with severity / confidence / review chips and top-3 bars,
  Report / Playbook / Model tabs.
* PDF report download (`lib/report_pdf.py`, fpdf2): summary, unconfirmed banner, image, report,
  source line and disclaimer.
* Human in the loop (`lib/feedback.py`): thumbs rating; review requests that open a case
  (automatic for unconfirmed results, or **Send to expert review**); expert review form
  (confirmed / corrected / inconclusive, reviewer severity, notes) that closes the case; a copy
  of the image in `raw/reviews/<date>/`; submitter from `X-Forwarded-Email`.
* **Review cases** tab: open and reviewed cases (newest 30 each) with image, model output and
  report; review an open case in place.
* `diagnosis_feedback` Delta table (ratings, review requests, expert reviews linked by
  `case_id`), created by `03_playbook` if missing and never overwritten; columns are added
  additively.
* Unit tests: `tests/test_severity.py`, `tests/test_report_and_feedback.py` (19 tests).
* Bundle variable `app_name`.

### Fixed

* The review-volume value is resolved by Databricks Apps as a path (`/Volumes/c/s/v`), not a
  dotted name; both forms are now accepted (expert reviews failed with "Invalid playbook table
  name").
* Review reasons read back from a stored case were split into single characters.
* Streamlit 1.50: `width="stretch"` replaces `use_container_width`.

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
