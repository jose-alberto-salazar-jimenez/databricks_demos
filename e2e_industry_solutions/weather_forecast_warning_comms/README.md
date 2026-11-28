# Weather Forecast Warning Comms

Location-aware, multilingual early-warning communications for weather, extreme events and
ENSO, built end to end on Databricks for civil protection agencies in Peru, Ecuador,
Colombia, Panama and Costa Rica.

Version: see [CHANGELOG.md](CHANGELOG.md) | Status: proof of concept ([PLAN.md](PLAN.md)); ingestion, medallion pipeline and LLM advisories running in dev; Lakebase, Genie and app pending

## The problem

Civil protection agencies publish generic, one-language bulletins that many people ignore,
and they get no signal back on whether the forecast matched what people lived through.
Seasonal ENSO risk (El Nino / La Nina) is rarely translated into local, practical action.

## What the solution does

A citizen, farmer or municipal officer picks a town and gets:

* Yesterday, today and the next 11 days (rain, temperature, wind); the past 11 days build up from daily runs.
* Heavy-rain, heat and wind warnings for the next 3 days (rule-based) and the current ENSO phase.
* A preventive advisory written for their user type and language (LLM).
* A form to report what they experienced and rate the forecast, stored in Lakebase (later:
  forecast skill metrics and a trained risk model; see PLAN.md section 7).

Agency analysts ask questions in natural language through a Genie Agent over the gold tables.

## Databricks capabilities used

| Stage | Capability | Role |
| --- | --- | --- |
| Ingest | Lakeflow Jobs + Spark Declarative Pipelines | Daily API landing, bronze/silver/gold |
| Govern | Unity Catalog | Catalogs per environment, lineage, tags, grants |
| Intelligence | `ai_query` on `system.ai` models | Multilingual, user-type advisories with a numbers guardrail |
| Serve | Lakebase | Low-latency app reads, citizen feedback writes |
| Ask | Genie Agent | Natural-language analytics for agency analysts |
| Surface | Databricks Apps (Dash) | Citizen-facing application |
| Deploy | Declarative Automation Bundles + GitHub | Reproducible dev/prod deployment |

## Data (public or synthetic only)

Open-Meteo (forecast), NOAA CPC ONI (ENSO), GDACS (extreme-event alerts), GeoNames (towns),
Natural Earth (boundaries, lakes) and demo citizen feedback. No customer data and no
credentials are stored in this repository.

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
  resources/          Job, pipeline, volume, app, Lakebase
  src/ingestion/      API landing to the UC volume
  src/pipeline/       SDP bronze / silver / gold
  src/app/            Dash application
  evidence/           Run outputs as text
  *.md                Documentation
```

## Getting started

1. Install the Databricks CLI and authenticate to your workspace (OAuth, no tokens in files).
2. From this folder: `databricks bundle validate -t dev`, then `databricks bundle deploy -t dev`.
3. Run the daily job once (ingestion, then the medallion pipeline):
   `databricks bundle run -t dev daily_refresh`.
4. Query `gold.location_weather_summary` in the target catalog (app: later phase).

## Contributing

Work on a feature branch, add your change under `[Unreleased]` in CHANGELOG.md, and open a
pull request. On merge, the `[Unreleased]` entries are moved under a new version number.
