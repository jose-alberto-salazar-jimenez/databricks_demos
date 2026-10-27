# cicd_dabs__data_eng__supply_chain

CI/CD demo with **Declarative Automation Bundles** and **GitHub Actions**: simulated supply chain sources are ingested by a
**Lakeflow Spark Declarative Pipeline** (bronze -> silver -> gold) and orchestrated by a **Lakeflow Job**, promoted from a
dev workspace to a prod workspace.

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
