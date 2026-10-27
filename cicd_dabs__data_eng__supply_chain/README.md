# cicd_dabs__data_eng__supply_chain

CI/CD demo with **Declarative Automation Bundles** and **GitHub Actions**: simulated supply chain sources are ingested by a
**Lakeflow Spark Declarative Pipeline** (bronze -> silver -> gold) and orchestrated by a **Lakeflow Job**, promoted from a
dev workspace to a prod workspace.

## What is a Declarative Automation Bundle (DAB)?

A **Declarative Automation Bundle** (formerly *Databricks Asset Bundle*) is Databricks' infrastructure-as-code format
for data and AI projects. One folder in Git holds:

- the **source code** (notebooks, Python files, SQL, pipeline transformations),
- the **resource definitions** (jobs, pipelines, schemas, dashboards, ...) as YAML (or Python),
- the **environment settings** (`targets` such as `dev` and `prod`, with variables, permissions and workspace hosts),
- and optionally **tests** and **build artifacts** (Python wheels, JARs).

The Databricks CLI then validates, deploys and runs the whole project as one unit:
`databricks bundle validate | deploy | run | destroy -t <target>`. Because everything is plain files, the same
project can be code reviewed, tested and promoted between workspaces by CI/CD, which is what this demo shows.

Reference: [What are Declarative Automation Bundles?](https://docs.databricks.com/aws/en/dev-tools/bundles/index/)

### What a bundle can manage (reference)

Resource types you can declare under `resources:` (from the
[bundle resources reference](https://docs.databricks.com/aws/en/dev-tools/bundles/resources/); the list grows with
new CLI releases, so check it for the current set). Some types can only reference an existing object rather than
create one; see the docs for each type. Names below are as in the docs; in YAML the mapping is plural, e.g.
`resources: { jobs: ..., pipelines: ..., schemas: ... }`.

| Area | Resource key(s) | What it is | In this demo |
| --- | --- | --- | --- |
| Orchestration | `job` | Lakeflow Jobs (tasks, schedules, triggers, parameters) | Yes |
| Orchestration | `job_run` | A job run | |
| Data engineering | `pipeline` | Lakeflow Spark Declarative Pipelines, and managed ingestion pipelines (connectors such as Salesforce, SQL Server, Workday) | Yes |
| Data quality | `quality_monitor` | Data quality monitoring on a table | |
| Unity Catalog | `catalog`, `schema`, `volume` | Catalogs, schemas and volumes | `schema`, `volume` |
| Unity Catalog | `external_location` | External storage locations | |
| Unity Catalog | `registered_model` | Models registered in Unity Catalog | |
| Unity Catalog | `secret` | Unity Catalog secrets | |
| Analytics / BI | `dashboard` | AI/BI dashboards | |
| Analytics / BI | `genie_spaces` | Genie agents (natural-language Q&A over tables) | |
| Analytics / BI | `alert` | Databricks SQL alerts | |
| Analytics / BI | `sql_warehouse` | SQL warehouses | |
| Apps | `app` | Databricks Apps | |
| Machine learning / AI | `experiment` | MLflow experiments | |
| Machine learning / AI | `model` | Legacy workspace models | |
| Machine learning / AI | `model_serving_endpoint` | Model Serving endpoints | |
| Machine learning / AI | `model_service`, `model_provider_service` | Model services and model provider services | |
| Machine learning / AI | `mcp_service` | MCP services | |
| Machine learning / AI | `vector_search_endpoint`, `vector_search_index` | Vector search endpoints and indexes | |
| Lakebase (Postgres) | `postgres_project`, `postgres_branch`, `postgres_endpoint`, `postgres_database`, `postgres_role`, `postgres_catalog`, `postgres_synced_table`, `postgres_snapshot_schedule` | Lakebase Postgres projects and their parts | |
| Lakebase (Postgres) | `database_instance`, `database_catalog`, `synced_database_table` | Database instances, database catalogs and synced tables | |
| Compute | `cluster`, `cluster_policy`, `instance_pool` | Classic compute and its policies | |
| Security | `secret_scope` | Workspace secret scopes | |

Besides `resources:`, a bundle also handles:

| Bundle section | What it does | In this demo |
| --- | --- | --- |
| `sync` / source files | Uploads notebooks, Python files and SQL to the workspace on deploy | Yes |
| `artifacts` | Builds and uploads Python wheels or JARs used by jobs and pipelines | |
| `variables` | Per-environment values (catalog, schedule, warehouse IDs, ...) | Yes |
| `targets` | Environments (`dev`, `prod`) with their own mode, workspace, variables and permissions | Yes |
| `permissions` | Who can view, run or manage the deployed resources | Yes (prod) |

Tip: `databricks bundle generate` turns an existing job, pipeline, dashboard or app built in the UI into bundle YAML.

## Architecture

```
 Simulated sources (job task 1)          Pipeline (job task 2)                                  Job task 3
 ------------------------------          ---------------------------------------------------    -------------
 Salesforce  accounts, opps   (JSON) -->  bronze_sf_*            --> silver_accounts             validate_gold
 Excel       sales targets    (xlsx) -->  bronze_excel_*         --> silver_opportunities  --+   (smoke tests)
 ERP         orders, inventory (CSV) -->  bronze_erp_*           --> silver_sales_targets    |
 Logistics   shipments        (JSON) -->  bronze_logistics_*     --> silver_orders           +-> gold_sales_performance
 Plant IoT   machine telemetry(JSON) -->  bronze_mfg_*           --> silver_inventory        +-> gold_delivery_performance
                                          (Auto Loader, UC volume)   silver_shipments        +-> gold_inventory_coverage
                                                                     silver_machine_telemetry+-> gold_machine_oee
```

| Layer | What it does |
| --- | --- |
| Bronze | Incremental Auto Loader ingestion from `/Volumes/<catalog>/<schema>/landing/<source>/...`, with lineage columns |
| Silver | Typed, de-duplicated entities with data quality expectations (drop / warn) |
| Gold | Sales vs. target attainment, on-time delivery, inventory days of cover, machine OEE |

## Layout

```
cicd_dabs__data_eng__supply_chain/
  databricks.yml                     # bundle, variables, dev/prod targets
  resources/
    supply_chain.schema.yml          # UC schema
    landing.volume.yml               # UC volume for raw source files
    supply_chain.pipeline.yml        # serverless SDP pipeline
    supply_chain.job.yml             # generate -> pipeline -> validate
  src/
    supply_chain_sim/generators.py         # pure-Python source simulators (unit tested)
    data_generator/generate_sources.py     # notebook: lands one batch per run
    pipeline/transformations/{bronze,silver,gold}.py
    quality/validate_gold.py               # notebook: post-pipeline checks
  tests/test_generators.py
.github/workflows/cicd_dabs__data_eng__supply_chain_{ci,cd}.yml   # at repo root
```

## Environments

| Target | Workspace | Catalog | Mode | Deployed by |
| --- | --- | --- | --- | --- |
| `dev` (default) | dbc-3fb58c7d-ac94 | `dev_demo` | development (prefixed names, paused schedule) | you (laptop / Cursor) or the dev service principal (CI) |
| `prod` | dbc-df52510d-0fb6 | `prod_demo` | production (daily 06:00 UTC schedule) | prod service principal from GitHub Actions only |

## CI/CD flow

1. Feature branch -> pull request: **CI** runs pytest and `bundle validate --strict -t dev`.
2. Merge to `main`: **CD** deploys to dev and runs the job end to end (fails if any gold check fails).
3. Approval on the `prod` GitHub environment: **CD** deploys to prod and runs the job once.

GitHub environments `dev` and `prod` each need the secrets `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`,
`DATABRICKS_CLIENT_SECRET` (service principal OAuth).

## Local demo (Cursor / terminal)

```bash
cd cicd_dabs__data_eng__supply_chain
databricks auth login --host https://dbc-3fb58c7d-ac94.cloud.databricks.com --profile dev
pip install pytest && pytest -v
databricks bundle validate -t dev -p dev
databricks bundle deploy   -t dev -p dev
databricks bundle run supply_chain_job -t dev -p dev
databricks bundle summary  -t dev -p dev
```

Demo ideas: add a new gold KPI or a stricter expectation on a branch, open a PR, watch CI, merge, approve prod.
See [DEMO.md](DEMO.md) for the full step-by-step talk track.

## Branch protection

`main` is protected by the `protect-main` ruleset: changes land only through pull requests, and the
`Unit tests` and `Validate bundle (dev)` checks from the CI workflow must pass before merging.
