# System Architecture

How the solution and the codebase are structured. Diagrams use Mermaid (rendered by GitHub).
Status: target design for v1.x; sections are updated as components are built.

## 1. Context

```mermaid
flowchart LR
  citizen[Citizen / farmer / municipality] -->|select location, read advisory, send feedback| app[Databricks App]
  analyst[Agency analyst] -->|natural-language questions| genie[Genie Agent]
  apis[Public APIs: Open-Meteo, NOAA ONI, GDACS, GeoNames] --> platform[Databricks platform]
  platform --> app
  platform --> genie
```

## 2. Logical architecture

```mermaid
flowchart TB
  subgraph Ingest[Lakeflow Job - daily]
    land[src/ingestion: call APIs per grid point] --> vol[(UC Volume bronze.landing)]
  end
  subgraph Medallion[Spark Declarative Pipeline]
    b[bronze: raw streaming tables] --> s[silver: cleaned, conformed, location-matched]
    s --> g[gold: summaries, skill, risk features]
  end
  vol --> b
  g --> train[src/ml: train risk model - MLflow + UC registry]
  train --> serve[Model Serving endpoint]
  serve --> scores[gold.risk_scores]
  g --> llm[ai_query via AI Gateway - open LLM]
  scores --> llm
  llm --> adv[gold.advisories]
  g --> genie[Genie Agent]
  subgraph Lakebase[Lakebase Postgres]
    synced[synced tables: summary, risk, advisories]
    oltp[user_profile, citizen_feedback]
  end
  g --> synced
  scores --> synced
  adv --> synced
  synced --> app[Dash app]
  app --> oltp
  oltp -->|daily sync| b
```

## 3. Daily run sequence

One Lakeflow Job, scheduled once per day (early morning, UTC-5):

```mermaid
sequenceDiagram
  participant J as Job
  participant API as Public APIs
  participant V as UC Volume
  participant P as SDP pipeline
  participant M as Model endpoint
  participant L as LLM (AI Gateway)
  participant LB as Lakebase
  J->>LB: export new citizen feedback to bronze
  J->>API: fetch ~8.1k grid points (past 92d + 16d forecast), ONI, GDACS
  API-->>V: JSON files (one folder per source/date)
  J->>P: update bronze -> silver -> gold
  J->>M: score risk per cell and hazard
  J->>L: generate advisories (cell x language x user type)
  J->>LB: refresh synced tables
```

Retraining runs weekly as a separate task once enough feedback and events accumulate.

## 4. Data model (Unity Catalog)

Catalog `weather_forecast_warnings_comms`, schemas `bronze`, `silver`, `gold`.

```mermaid
erDiagram
  dim_location ||--o{ weather_observed_daily : cell_id
  dim_location ||--o{ weather_forecast_daily : cell_id
  dim_location ||--o{ extreme_events : cell_id
  dim_location ||--o{ citizen_feedback : cell_id
  dim_location ||--o{ risk_scores : cell_id
  dim_location ||--o{ advisories : cell_id
  enso_phase_monthly ||--o{ risk_features : month
  dim_location {
    string cell_id PK
    string country
    double lat
    double lon
    int grid_km
  }
  risk_scores {
    string cell_id
    date run_date
    string hazard
    double p_72h
  }
  advisories {
    string cell_id
    date run_date
    string language
    string user_type
    string advisory_text
  }
```

* Grain: one row per grid cell per day (forecasts: per cell, run date, target date).
* `cell_id`: deterministic id from rounded lat/lon and grid size (20 km PE/CO/EC, 10 km CR/PA).
* Towns (GeoNames) map to their nearest `cell_id`; any coordinate resolves the same way.
* Governance: comments on all tables, tags (`domain`, `pii`), column mask on feedback
  contact fields, app service principal has SELECT on gold only.

## 5. Codebase structure

| Path | Responsibility | Runs on |
| --- | --- | --- |
| `databricks.yml` | Bundle root: variables (catalog, schemas), dev/prod targets | CLI |
| `resources/*.yml` | Job, pipeline, serving endpoint, app, Lakebase definitions | Bundle deploy |
| `src/ingestion/` | Grid generation, API calls with retry/backoff, writes to volume | Serverless job |
| `src/pipeline/` | SDP tables and expectations, bronze to gold | Serverless pipeline |
| `src/ml/` | Features, training, registration, batch scoring, advisory prompts | Serverless job |
| `src/app/` | Dash pages, callbacks, Lakebase data access | Databricks Apps |
| `evidence/` | Text outputs that prove each stage ran | Committed manually |

Conventions: lowercase snake_case names; configuration through bundle variables, never
hard-coded workspace ids; one module per concern; files kept under 9,000 characters.

## 6. Application design

```mermaid
flowchart LR
  ui[Dash layout: search, map, charts, advisory, feedback form] --> cb[callbacks]
  cb --> dal[data access layer]
  dal -->|read| synced[(Lakebase synced tables)]
  dal -->|insert| fb[(Lakebase citizen_feedback)]
```

* Stateless app instances behind Databricks Apps; scales by adding instances.
* Reads hit Lakebase only (no SQL warehouse on the request path).
* Auth: app service principal with OAuth tokens to Lakebase; no secrets in code.
* Language and user type come from the user profile or the UI selector.

## 7. Environments and deployment

| Target | Catalog | Purpose |
| --- | --- | --- |
| dev | `weather_forecast_warnings_comms` (dev prefix on resources) | Development, per-user deploys |
| prod | `weather_forecast_warnings_comms` | Scheduled daily run, shared app |

Flow: feature branch -> PR (bundle validate in CI) -> merge to main -> deploy prod.

## 8. Non-functional design

* Cost: daily batch, serverless compute, open low-cost LLM, cached advisories.
* Limits: ~8.1k points/day within Open-Meteo free tier (10k calls/day).
* Reliability: idempotent daily loads keyed by run date; failed days can be re-run.
* Quality: SDP expectations (coordinates, ranges, nulls); model compared to rule baseline.
* LLM safety: values injected from gold, no invented numbers or causes, sampled evaluation.
