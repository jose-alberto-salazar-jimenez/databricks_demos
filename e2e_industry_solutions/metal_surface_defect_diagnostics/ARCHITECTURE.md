# Metal Surface Defect Diagnostics - System Architecture

This document explains how the solution and the codebase are structured: components, data flows,
data model, configuration, security and how to extend it. For setup and usage see `README.md`;
for scope and phases see `PLAN.md`; for history see `CHANGELOG.md`.

## 1. Overview

The solution follows the reference architecture **"Pipe corrosion image diagnostics"** on Azure
Databricks (serverless). It has two planes, both governed by Unity Catalog:

* **Build plane** (Lakeflow Jobs): ingest labelled images, train and register an image classifier,
  load the SME playbook index, evaluate, and publish the model to Model Serving.
* **Serve plane** (Databricks App): a field engineer uploads a photo, the app gets the predicted
  defect class and confidence from Model Serving, retrieves the matching playbook entry, and a
  Foundation Model writes a grounded prescription from that entry.

Design principle: **playbooks are written up front with integrity engineers; the LLM only
rephrases what it retrieves**, cites the source entry, and flags low confidence or no matching
playbook for human review.

## 2. System context

```mermaid
flowchart LR
  subgraph BUILD["Build - ingest, train, register (Lakeflow Jobs)"]
    VOL["UC Volume raw<br/>zip/ + images/class/"] -->|new files| AL["Auto Loader -> Delta<br/>binaryFile + labels"]
    AL -->|train set| TR["Training (serverless CPU)<br/>PyTorch + MLflow runs"]
    TR -->|register| REG["UC Model Registry<br/>versions + champion alias"]
    YAML["defect_playbook.yaml<br/>(repo, PR-reviewed)"] -->|load| PB
  end
  subgraph SERVE["Serve - inference app + grounded prescription"]
    USER["Field engineer<br/>photo in, diagnosis out"] -->|upload| APP["Databricks App (Streamlit)<br/>upload + result page"]
    APP -.->|result| USER
    APP -->|POST image| MS["Model Serving<br/>msd-defect-classifier"]
    MS -.->|class + score| APP
    APP -->|retrieve via SQL warehouse| PB[("Playbook index<br/>defect_playbook (Delta)")]
    APP -->|generate| LLM["Foundation Model API<br/>llama-3-3-70b-instruct"]
  end
  REG -->|champion| MS
  UC{{"Unity Catalog governs volumes, tables, models, endpoints, app access"}}
```

Legend (as in the reference): governed assets are the volume, tables, model, endpoint and app;
compute steps are the job tasks, Model Serving and the LLM; stored data is the volume and Delta
tables; people/input is the field engineer. Solid arrows are calls, dotted arrows are responses.

## 3. Components

| Component | Databricks service | Bundle resource / code | Responsibility |
| --- | --- | --- | --- |
| Raw volume | UC managed volume | `resources/msd.volume.yml` | Holds the uploaded NEU zip (`zip/`) and extracted images (`images/<class>/`) |
| Schema | UC schema | `resources/msd.schema.yml` | Container for all tables, the volume and the registered model |
| Ingest | Lakeflow Job task, serverless | `src/pipeline/01_ingest.ipynb` | Extract zip, Auto Loader `binaryFile` into `image_bronze`, label from folder name, stratified split into `image_index` |
| Train | Lakeflow Job task, serverless CPU | `src/pipeline/02_train.ipynb` | Transfer learning (MobileNetV3-Small), MLflow tracking, pyfunc packaging, isolated serving-readiness check, register a new UC model version |
| Experiment | MLflow experiment | `resources/msd.experiment.yml` | One experiment per target; training runs and evaluation artifacts |
| Playbook load | Lakeflow Job task | `src/pipeline/03_playbook.ipynb`, `src/playbook/defect_playbook.yaml` | Validate the YAML and overwrite the `defect_playbook` Delta table |
| Evaluate | Lakeflow Job task | `src/pipeline/04_evaluate.ipynb` | Test-set accuracy, per-class metrics, confusion matrix; append `model_eval_metrics`; promotion gate sets the `champion` alias |
| Deploy endpoint | Lakeflow Job task | `src/pipeline/05_deploy_endpoint.ipynb` | Create or update the serving endpoint pinned to the exact `champion` version; wait for READY; smoke test |
| Classifier endpoint | Model Serving (CPU, Small, scale-to-zero) | created by task 05 | REST inference: base64 image in; `predicted_class`, `confidence`, `probabilities` out. `msd-defect-classifier` (prod), `msd-defect-classifier-dev` (dev) |
| Web app | Databricks Apps (Streamlit) | `resources/msd_app.app.yml`, `src/app/` | Upload, result page, severity, human-review routing, report and playbook tabs |
| Playbook index | Delta table via SQL warehouse | `defect_playbook` | Retrieval of the SME entry for the predicted class |
| LLM | Foundation Model API (pay-per-token) | `databricks-meta-llama-3-3-70b-instruct` | Rephrase the retrieved playbook entry into the diagnostic report |

## 4. Build plane

### 4.1 Job DAG

```mermaid
flowchart LR
  I["01_ingest"] --> T["02_train"]
  I --> P["03_playbook"]
  T --> E["04_evaluate"]
  E --> D["05_deploy_endpoint"]
  P --> D
```

One job (`msd_training`, `resources/msd_training.job.yml`) runs the whole build on serverless
compute, with a 2-hour job timeout and one concurrent run. Tasks are parameterised from bundle
variables (catalog, schema, volume, model name, experiment, epochs, promotion gate, endpoint
name), so the same code runs in `dev` and `prod`. `train` passes the exact registered version to
`evaluate` through a task value.

Typical end-to-end run in dev: about 21 minutes. `ingest` takes about 2 minutes (no new files),
`playbook` 1, `train` 7 (about 4 of them training), `evaluate` 1, and `deploy_endpoint` about 11
when a new version is promoted (Model Serving builds and rolls out the model container). When
the endpoint already serves the `champion` version, the deploy task finishes in seconds.

### 4.2 Ingestion

1. The user uploads the Kaggle zip, unchanged, to `/Volumes/<catalog>/<schema>/raw/` (root or
   `zip/`). Every `*.zip` found there is processed.
2. `01_ingest` extracts the images (not the XML annotations) from
   `NEU-DET/<split>/images/<class>/` to
   `/Volumes/<catalog>/<schema>/raw/images/<source_split>/<class>/<file>.jpg`. Files already
   present with the same size are skipped.
3. Auto Loader (`cloudFiles.format = binaryFile`, `availableNow` trigger, checkpoint in
   `raw/_checkpoints/image_bronze`) appends new images to `image_bronze`; `label` is the parent
   folder and `source_split` the grandparent folder. Re-runs only pick up new files.
4. `image_index` is rebuilt each run with a deterministic split that keeps the dataset's
   published split: Kaggle `train` (240 per class) -> `train`; Kaggle `validation` (60 per class)
   -> 30 `val` + 30 `test` per class, ordered by `xxhash64(file_name)`.
5. Checks fail the task on unexpected classes, duplicate paths or an empty split.

### 4.3 Training and registration

* Backbone: torchvision MobileNetV3-Small pretrained on ImageNet; classifier head replaced with 6
  outputs; grayscale images replicated to 3 channels, resized to 224x224, ImageNet normalisation,
  augmentation with horizontal and vertical flips.
* Optimisation: AdamW (lr 3e-4, weight decay 1e-4), cosine learning-rate schedule, 8 epochs
  (`train_epochs`), batch 32, seed 42. The checkpoint with the best validation accuracy is kept.
  On serverless CPU an epoch takes about 30 seconds with PyTorch's default thread count. Switching
  to serverless GPU only changes the task compute.
* Dependencies: CPU PyTorch 2.5.1 / torchvision 0.20.1 from the PyTorch CPU index, installed
  with `%pip` in the task. The model's serving requirements pin `torch==2.5.1` and
  `torchvision==0.20.1` without a `+cpu` tag, because that build exists only for x86_64 while
  serverless can schedule the task on aarch64.
* Packaging: MLflow pyfunc wrapper (weights and class list as artifacts). Input: DataFrame column
  `image` with base64-encoded image bytes. Output: `predicted_class`, `confidence` (top-1
  probability) and `probabilities` (JSON string class -> probability). Signature and input
  example are logged.
* Serving-readiness gate: before registration, the logged artifact is loaded and scored with
  `mlflow.models.predict(..., env_manager="uv")`, which installs the declared requirements from
  scratch in an isolated environment, as Model Serving will.
* Registration: a new version of `<catalog>.<schema>.msd_defect_classifier` in Unity Catalog. The
  `champion` alias is set later by `04_evaluate`.

### 4.4 Evaluation and promotion

* `04_evaluate` loads the exact version from Unity Catalog and scores the held-out `test` split
  (30 images per class) through the same pyfunc interface the endpoint uses.
* It computes accuracy, macro F1, per-class precision/recall/F1/support and the confusion matrix.
  Metrics and CSV artifacts (`evaluation/confusion_matrix.csv`,
  `evaluation/per_class_metrics.csv`) are logged to the version's MLflow run, and one row per
  class is appended to `model_eval_metrics`.
* Gate: the version gets the `champion` alias (and a `test_accuracy` version tag) only if test
  accuracy >= `min_test_accuracy` (default 0.90). Otherwise the previous champion stays.
* Current dev result: 98.33% test accuracy (177/180), macro F1 0.984. The three errors are two
  `inclusion` images and one `patches` image predicted as `pitted_surface`; two test images
  score below the 0.70 confidence threshold and would be routed to human review.

### 4.5 Endpoint deployment

* `05_deploy_endpoint` resolves `champion` to an exact version and never serves "latest".
* It checks that the workspace supports `CPU` / `Small`, creates the endpoint if absent, or
  updates it when the served version differs. It refuses to modify an endpoint that serves a
  different model.
* Settings: `CPU` workload (4 GB per concurrency), `Small` size (4 concurrent requests),
  scale-to-zero enabled (the first request after idle has a cold start). No route optimisation.
* It waits for `READY` (fails on `UPDATE_FAILED` / `UPDATE_CANCELED`, times out after 45 minutes),
  then smoke-tests one test image per class and requires at least 5 of 6 correct.
* The endpoint name is workspace-global and not prefixed by development mode, so the `dev`
  target overrides it to `msd-defect-classifier-dev`.

### 4.6 Playbook index

`src/playbook/defect_playbook.yaml` is the source of truth (v1.0.0, status `draft`, pending SME
review). `03_playbook` validates it (exactly the six NEU classes, unique `playbook_id`, required
text and list fields non-empty, `base_severity` in Low/Medium/High) and overwrites
`defect_playbook`; validation errors fail the task so an invalid playbook never reaches the app. Content changes go through a pull request and a CHANGELOG entry.

## 5. Serve plane

### 5.1 Inference sequence

```mermaid
sequenceDiagram
  actor U as Field engineer
  participant A as Databricks App (Streamlit)
  participant M as Model Serving (msd-defect-classifier)
  participant W as SQL warehouse (defect_playbook)
  participant L as Foundation Model API
  U->>A: Upload image
  A->>M: POST base64 image
  M-->>A: predicted_class, confidence, probabilities
  A->>A: top-k, severity, human-review flag
  A->>W: SELECT playbook entry for top-1 (and top-2 if low confidence)
  W-->>A: playbook rows
  alt playbook found
    A->>L: system prompt + prediction context + playbook entry
    L-->>A: grounded report with citation
  else no matching playbook
    A->>A: skip LLM, route to human review
  end
  A-->>U: classification card, report tab, playbook tab
```

### 5.2 Severity and human review

| Condition | Severity | Human review |
| --- | --- | --- |
| top-1 confidence < threshold (default 0.70) | Low (unconfirmed) | Yes; report covers top-2 classes |
| confidence >= threshold | class base weight (Low / Medium / High) | No |
| confidence >= 0.95 and base weight High | Critical | No |
| no playbook entry or lookup failure | as above | Yes; LLM not called |

Base weights per class are in the playbook (`base_severity`), so they are reviewed together with
the content.

### 5.3 Grounded generation

* The system prompt restricts the model to the provided playbook entry, requires the fixed
  sections (Defect Summary, Risk Assessment, Recommended Inspection, Recommended Repair,
  Monitoring and Escalation) and a final `Source: <playbook_id> v<playbook_version>` line.
* The user prompt carries the prediction context (class, category, confidence, severity, review
  flag) and the playbook entry as structured text.
* Low temperature, bounded `max_tokens`. If the LLM call fails, the app shows the playbook entry
  directly so the user always gets the reviewed baseline.

### 5.4 App modules

| Module | Purpose |
| --- | --- |
| `app.py` | Streamlit layout: sidebar config, uploader, classification card, tabs |
| `lib/classifier_client.py` | Calls the serving endpoint with the Databricks SDK |
| `lib/severity.py` | Pure functions for severity and human-review rules (unit-testable) |
| `lib/playbook.py` | Reads `defect_playbook` through the SQL warehouse; YAML fallback |
| `lib/prompt.py` | Builds system and user prompts |
| `lib/llm_client.py` | Calls the Foundation Model API (OpenAI-compatible chat) |

## 6. Data model

```mermaid
erDiagram
  image_bronze ||--|| image_index : "path"
  image_index }o--|| defect_playbook : "label = defect_class"
  model_eval_metrics }o--|| defect_playbook : "per-class metrics"
  image_bronze {
    string path
    timestamp modificationTime
    long length
    binary content
    string file_name
    string label
    string source_split
    timestamp ingested_at
  }
  image_index {
    string path
    string file_name
    string label
    string source_split
    string split
    long length
  }
  defect_playbook {
    string playbook_id
    string defect_class
    string display_name
    string category
    string base_severity
    string description
    array visual_indicators
    array typical_root_causes
    string risk_assessment
    string progression_if_untreated
    array recommended_inspection
    array recommended_repair
    string monitoring
    array escalation_criteria
    string playbook_version
    string playbook_status
    string approved_by
    string last_reviewed
    string disclaimer
    timestamp loaded_at
  }
  model_eval_metrics {
    string model_version
    string defect_class
    double precision
    double recall
    double f1
    int support
    double accuracy
    double macro_f1
    timestamp evaluated_at
  }
```

All objects live in `poc_metal_surface_defect_diagnostics.metal_surface_defects` together with
the `raw` volume and the registered model `msd_defect_classifier`. `model_eval_metrics` is
append-only: one row per evaluated model version and defect class (`accuracy` and `macro_f1`
repeat the version-level values).

## 7. Codebase structure

```
metal_surface_defect_diagnostics/
  databricks.yml            # bundle name, variables, dev/prod targets
  resources/                # one file per resource: <name>.<type>.yml
    msd.schema.yml
    msd.volume.yml
    msd.experiment.yml      # phase 3
    msd_training.job.yml    # phase 2-3
    msd_app.app.yml         # phase 4
  src/
    pipeline/               # job task notebooks, numbered in execution order
    playbook/               # SME playbook YAML (source of truth for grounding)
    app/                    # Streamlit app source deployed as a Databricks App
  README.md  ARCHITECTURE.md  CHANGELOG.md  PLAN.md
```

Conventions: resource keys are prefixed `msd` and must be unique across resource types (the
schema is `msd`, the experiment `msd_classifier`); all names and endpoints come from bundle variables;
notebooks read parameters from job widgets; no hard-coded catalog or schema in code.

## 8. Configuration

| Variable | Default | Used by |
| --- | --- | --- |
| `catalog` | `poc_metal_surface_defect_diagnostics` | all |
| `schema` | `metal_surface_defects` | all |
| `raw_volume` | `raw` | ingest |
| `model_name` | `msd_defect_classifier` | train, evaluate, deploy |
| `serving_endpoint` | `msd-defect-classifier` (`dev`: `msd-defect-classifier-dev`) | deploy, app |
| `train_epochs` | `8` | train |
| `min_test_accuracy` | `0.90` | evaluate (promotion gate) |
| `llm_endpoint` | `databricks-meta-llama-3-3-70b-instruct` | app |
| `warehouse_id` | `b91f5b2fb518a0b7` (`demo_serverles`) | app |
| `confidence_threshold` | `0.70` | app |

Targets: `dev` (development mode, default, job names prefixed and schedules paused) and `prod`
(production mode, shared root path, owner CAN_MANAGE, `users` CAN_VIEW).

## 9. Security and governance

* Unity Catalog governs the volume, tables, registered model, serving endpoint and app access.
* The app runs as its own service principal. The bundle grants it: `CAN_QUERY` on the classifier
  endpoint and the LLM endpoint, `CAN_USE` on the SQL warehouse, and `SELECT` on
  `defect_playbook` (plus `USE CATALOG` / `USE SCHEMA`).
* Uploaded images are processed in memory and not persisted in v1.0.
* No secrets are stored in code; all Databricks calls use the platform-provided identity.

## 10. Extending the solution

* New defect class or dataset (for example GC10-DET): add images under `images/<class>/`, add a
  playbook entry, retrain; the app reads class names from the model output and the playbook.
* GPU training: change the train task compute; no code change.
* Retrieval at scale: replace the exact-match lookup with a Vector Search index over playbook
  chunks when playbooks become long or multi-document.
* Feedback loop: persist uploads and engineer verdicts to a Delta table for relabelling.

## 11. Known limitations

* NEU images are steel strip defects, not in-service pipeline photos; the pipeline-corrosion
  mapping is illustrative.
* The playbook is POC content and requires integrity-engineer sign-off before real use.
* dev and prod share one workspace and catalog in this POC.
* Every job run trains and registers a new version and promotes it if it clears the 90% gate,
  even when it is not better than the current champion, which triggers an endpoint rollout
  (about 11 minutes).
* Most remaining classifier errors are `inclusion` or `patches` predicted as `pitted_surface`.
* With scale-to-zero, the first request after an idle period waits for the endpoint to start.
