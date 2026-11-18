# Weather Forecast Warning Comms

Location-aware, multilingual early-warning communications for weather, extreme events and
ENSO, built end to end on Databricks for civil protection agencies in Peru, Ecuador,
Colombia, Panama and Costa Rica.

Version: see [CHANGELOG.md](CHANGELOG.md) | Status: planning (no code deployed yet)

## The problem

Civil protection agencies publish generic, one-language bulletins that many people ignore,
and they get no signal back on whether the forecast matched what people lived through.
Seasonal ENSO risk (El Nino / La Nina) is rarely translated into local, practical action.

## What the solution does

A citizen, farmer or municipal officer picks a city, town, map point or coordinates and gets:

* The last 11 days, today, and the next 11 days (rain, temperature, wind).
* Risk of extreme events in the next 72 hours (ML model) and the current ENSO phase.
* A preventive advisory written for their user type and language (LLM).
* A form to report what they actually experienced and how they rate the forecast. This
  citizen data flows back into the lakehouse to measure forecast skill and tune the model.

Agency analysts ask questions in natural language through a Genie Agent over the gold tables.

## Databricks capabilities used

| Stage | Capability | Role |
| --- | --- | --- |
| Ingest | Lakeflow Jobs + Spark Declarative Pipelines | Daily API landing, bronze/silver/gold |
| Govern | Unity Catalog | Catalog `weather_forecast_warnings_comms`, lineage, tags, masks, grants |
| Intelligence | MLflow + Model Serving | Extreme-event risk model (72h) |
| Intelligence | Foundation Model APIs via AI Gateway | Multilingual, user-type advisories |
| Serve | Lakebase | Low-latency app reads, citizen feedback writes |
| Ask | Genie Agent | Natural-language analytics for agency analysts |
| Surface | Databricks Apps (Dash) | Citizen-facing application |
| Deploy | Declarative Automation Bundles + GitHub | Reproducible dev/prod deployment |

## Data (public or synthetic only)

Open-Meteo (history + forecast), NOAA CPC ONI (ENSO), GDACS (extreme-event alerts),
GeoNames (towns), and synthetic impact history and citizen feedback. No customer data and
no credentials are stored in this repository.

## Documentation

| Document | Contents |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System and codebase structure, data flow, diagrams |
| [PLAN.md](PLAN.md) | Build plan, phases, scope |
| [DECISIONS.md](DECISIONS.md) | Design decisions, alternatives and trade-offs |
| [CHANGELOG.md](CHANGELOG.md) | Versioned log of changes |

## Repository layout

```
weather_forecast_warning_comms/
  databricks.yml      Bundle definition (dev / prod targets)
  resources/          Jobs, pipeline, serving endpoint, app, Lakebase
  src/ingestion/      API landing to the UC volume
  src/pipeline/       SDP bronze / silver / gold
  src/ml/             Risk model training + advisory generation
  src/app/            Dash application
  evidence/           Run outputs as text
  *.md                Documentation
```

## Getting started (once phase 1 lands)

1. Install the Databricks CLI and authenticate to your workspace (OAuth, no tokens in files).
2. From this folder: `databricks bundle validate -t dev`, then `databricks bundle deploy -t dev`.
3. Run the daily job once: `databricks bundle run -t dev daily_refresh`.
4. Open the app URL shown in the Apps page.

## Contributing

Work on a feature branch, add your change under `[Unreleased]` in CHANGELOG.md, and open a
pull request. On merge, the `[Unreleased]` entries are moved under a new version number.
