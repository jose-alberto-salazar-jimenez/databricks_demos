# Metal Surface Defect Diagnostics

Pipe corrosion image diagnostics, **predictive and prescriptive**, on Databricks.

A field engineer uploads a photo of a metal surface to a Streamlit Databricks App. The app:

1. classifies the defect with an image model served on Model Serving,
2. assigns a severity and routes low-confidence results to human review,
3. retrieves the matching, engineer-reviewed **defect playbook** entry, and
4. asks a Foundation Model to write a short diagnostic report (summary, risk, inspection, repair,
   monitoring) **from that playbook entry only**, citing the source.

Pre-written playbooks give the LLM a reviewed baseline, so it rephrases instead of inventing
recommendations.

> Status: Phase 1 (foundation) released in 1.1.0; Phase 2 (data and playbook) released in 1.2.0; Phase 3 (model) in progress. See `PLAN.md`.

## Architecture at a glance

```mermaid
flowchart LR
  VOL["UC Volume"] --> AL["Auto Loader -> Delta"] --> TR["Train (CPU) + MLflow"] --> REG["UC Model Registry"] --> MS["Model Serving"]
  USER["Field engineer"] --> APP["Databricks App"]
  APP --> MS
  APP --> PB[("Playbook index")]
  APP --> LLM["Foundation Model"]
```

Details, diagrams and component descriptions: [ARCHITECTURE.md](ARCHITECTURE.md).

## Dataset

[NEU Surface Defect Database](https://www.kaggle.com/datasets/kaustubhdikshit/neu-surface-defect-database):
1,800 grayscale 200x200 images of hot-rolled steel, 300 per class.

| Class | Pipeline-context category |
| --- | --- |
| crazing | Surface cracking network / stress-related |
| inclusion | Material / manufacturing imperfection |
| patches | Corrosion / oxidation area |
| pitted_surface | Pitting corrosion |
| rolled-in_scale | Mill scale / surface contamination |
| scratches | Mechanical surface damage |

The pipeline-context mapping is an illustrative POC assumption.

## Tech stack

Unity Catalog (volume, tables, model), Auto Loader, Lakeflow Jobs (serverless), PyTorch +
torchvision, MLflow, Model Serving, Foundation Model API
(`databricks-meta-llama-3-3-70b-instruct`), Databricks Apps (Streamlit), Declarative
Automation Bundles.

## Repository layout

```
metal_surface_defect_diagnostics/
  databricks.yml     # bundle definition and variables
  resources/         # schema, volume, job, app
  src/pipeline/      # ingest, train, playbook, evaluate, deploy notebooks
  src/playbook/      # SME defect playbook (YAML)
  src/app/           # Streamlit app
  README.md  ARCHITECTURE.md  CHANGELOG.md  PLAN.md
```

## Prerequisites

* Premium Azure Databricks workspace with Unity Catalog, serverless compute, Model Serving and
  Databricks Apps enabled.
* Catalog `poc_metal_surface_defect_diagnostics` (or another catalog you can create schemas in;
  override with `--var catalog=<name>`).
* Access to the Foundation Model endpoint `databricks-meta-llama-3-3-70b-instruct` and a SQL
  warehouse (default `demo_serverles`; override with `--var warehouse_id=<id>`).
* Databricks CLI (web terminal or local) or the workspace bundle UI.

## Getting started

Run from this folder (the bundle root).

1. Validate and deploy the foundation (schema and volume):

   ```
   databricks bundle validate --strict --target dev
   databricks bundle deploy --target dev
   ```

2. Download the NEU zip from Kaggle and upload it, as is, to the `raw` volume (root or `zip/`)
   via Catalog Explorer > volume > Upload, or the Files API. The schema name depends on the target:

   | Target | Volume path |
   | --- | --- |
   | dev | `/Volumes/poc_metal_surface_defect_diagnostics/dev_<your_user>_metal_surface_defects/raw/` |
   | prod | `/Volumes/poc_metal_surface_defect_diagnostics/metal_surface_defects/raw/` |

   Development mode prefixes the schema with `dev_<user>_` so personal deployments do not collide
   with prod. The Kaggle archive contains `NEU-DET/{train,validation}/images/<class>/*.jpg`
   (1,800 images, 300 per class) plus Pascal VOC XML annotations, which this POC does not use.

3. Deploy again (to pick up the job) and run the build job:

   ```
   databricks bundle deploy --target dev
   databricks bundle run msd_training --target dev
   ```

   Tasks: `ingest` (extract zip, Auto Loader into `image_bronze`, split into `image_index`:
   240 train / 30 val / 30 test per class), `playbook` (validate the YAML and load
   `defect_playbook`), `train` (CPU transfer learning, about 5 minutes of training plus the
   isolated serving-readiness check, registers a new model version), `evaluate` (test metrics into
   `model_eval_metrics`, sets `@champion` at test accuracy >= 90%) and `deploy_endpoint`
   (creates or updates the serving endpoint for `@champion`; the first creation takes about 15
   minutes). Endpoint names: `msd-defect-classifier-dev` (dev), `msd-defect-classifier` (prod).

4. Start the app (available from Phase 4):

   ```
   databricks bundle run msd_app --target dev
   ```

5. Open the app URL, upload a test image (for example from `raw/images/pitted_surface/`), and
   review the classification card, the AI diagnostic report and the playbook reference.

## Configuration

All names are bundle variables in `databricks.yml` (catalog, schema, volume, model name, serving
endpoint, LLM endpoint, warehouse, confidence threshold). See ARCHITECTURE.md section 8.

## Updating the playbook

Edit `src/playbook/defect_playbook.yaml`, bump `playbook_version`, add a CHANGELOG entry, open a
PR for engineer review, then re-run the job (the playbook task reloads the table).

## Contributing and versioning

Work on a branch, add entries under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md), and promote
them to a new version when the PR is merged (Semantic Versioning).

## Disclaimer

This is a proof of concept. NEU images are steel strip defects, not in-service pipeline images,
and the playbook content must be reviewed by qualified integrity engineers before any
operational use.
