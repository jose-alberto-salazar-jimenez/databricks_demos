# Weather Forecast Warning Comms - Build Plan

End-to-end Databricks solution: weather forecasts, extreme events and ENSO signals turned into
location-specific, multilingual, preventive communications, with a citizen-feedback loop.
Scoped to meet the FE Bar build requirements (Lakeflow, Unity Catalog, Lakebase, ML/GenAI,
Genie Agent, Databricks App, evidence readable as text, public/synthetic data only, no secrets).

Status: PLAN (v0.2, 2026-11-11). Refresh, coverage, app framework and LLM decided.

## 1. Customer problem (industry framing)

* Industry: Public sector - national meteorological / civil protection agencies.
* Customer persona: a civil protection agency (e.g. Costa Rica CNE, Panama SINAPROC,
  Peru INDECI-style) that must warn citizens and farmers before floods, landslides,
  heatwaves and droughts, and today sends generic, one-language bulletins.
* Pain: generic warnings are ignored; no feedback on whether forecasts matched what people
  experienced; ENSO-driven seasonal risk is not translated into local action.
* KPIs: warning lead time, % users served in their language/user type, citizen-reported
  forecast accuracy, feedback volume per event.
* User types: citizens, farmers, municipalities.

## 2. Pilot region

Peru, Ecuador, Colombia, Panama, Costa Rica. Contrasting ENSO impacts: El Nino floods coastal
Peru/Ecuador, dries Colombia and the Pacific side of Costa Rica/Panama (Dry Corridor).
Languages: Spanish, English (extensible).

Coverage (decided): land grid + all towns/cities.
* Grid: 20 km for PE/CO/EC (6,788 points), 10 km for CR/PA (1,272 points), land only.
  Counted in phase 2 with a Natural Earth land mask.
* Towns: all GeoNames populated places (CC-BY), each mapped to its nearest grid cell, so any
  town or coordinate resolves to a cell.
* Budget: 8,060 points/day fits Open-Meteo's free tier (10,000 calls/day, non-commercial).
  1 call/point (<=10 vars, <=14 days): +/-11 days (past from stored runs); deep history (ERA5
  archive) is a one-off backfill spread over several days.

## 3. Data sources (all public or synthetic, no API keys)

| Source | Content | Use |
| --- | --- | --- |
| Open-Meteo Historical + Forecast API | Daily/hourly temp, precip, wind, 11-day forecast | Past, current, future trends |
| NOAA CPC ONI index | Monthly ENSO index / phase | Seasonal context |
| GDACS alerts (RSS/JSON) | Floods, cyclones, droughts | Extreme events |
| GeoNames dumps | Towns/cities, admin areas, population | Location search |
| Synthetic (Python/LLM) | Event impact history, citizen feedback seed | Labels, demo realism |
| Lakebase (app) | Live citizen feedback, user profiles | Citizen data loop |

Note: repo already has `api_autoloader__data_eng__open_meteo_weather`; its landing logic can be
adapted (own prior work), but this project is self-contained.

## 4. Architecture (one integrated data journey)

```
APIs -> UC Volume -> Lakeflow SDP: bronze -> silver -> gold
 gold -> Genie Agent (analysts)
 gold -> ML (MLflow, UC) -> Serving endpoint
 gold -> LLM advisories (AI Gateway) -> gold.advisories
 gold -> synced tables -> Lakebase -> Databricks App
App feedback -> Lakebase -> sync -> bronze -> silver/gold -> retraining
```

## 5. Unity Catalog layout

Catalog: `weather_forecast_warnings_comms` (created). Schemas: `bronze`, `silver`, `gold` (created).
Volume: `bronze.landing` for raw API files.

| Layer | Tables (planned) |
| --- | --- |
| bronze | `open_meteo_history_raw`, `open_meteo_forecast_raw`, `enso_oni_raw`, `gdacs_events_raw`, `synthetic_impacts_raw`, `citizen_feedback_raw` |
| silver | `dim_location`, `weather_observed_daily`, `weather_forecast_daily`, `enso_phase_monthly`, `extreme_events`, `citizen_feedback` |
| gold | `location_weather_summary` (last 11d / today / next 11d), `forecast_vs_observed_skill`, `risk_features`, `risk_scores`, `advisories`, `feedback_metrics` |

Governance: table/column comments, tags (`pii`, `domain`), column mask on feedback contact
fields, grants for an app service principal and an analysts group, lineage visible in UC.
Data quality: SDP expectations (valid coordinates, plausible ranges, non-null dates).

## 6. Ingestion - Lakeflow

* Lakeflow Job task 1: Python notebook calls APIs per location, writes JSON to the volume.
* Task 2: Spark Declarative Pipeline (SQL/Python) - `read_files` streaming tables in bronze,
  materialized views in silver/gold, expectations for quality.
* Task 3: scoring + advisory generation. Schedule: once per day (decided), early morning
  local time (UTC-5), after the main model runs are published.

## 7. ML and GenAI

* ML model: gradient boosting classifier for P(extreme event within 72h) per location and
  hazard (heavy rain, heat, wind). Features: forecast values, recent 7/30-day anomalies,
  ENSO phase, location attributes, citizen-reported impacts. Tracked in MLflow, registered in
  UC, served on a Model Serving endpoint. Baseline comparison vs simple threshold rules.
* Optional: forecast bias correction using observed data and citizen feedback.
* GenAI: open-weight, low-cost model on Foundation Model APIs via AI Gateway (decided):
  `databricks-qwen3-next-80b-a3b-instruct` (MoE, ~3B active params: cheap, good Spanish),
  fallback `databricks-gpt-oss-20b`. Both smoke-tested on a Spanish farmer advisory.
  Turns gold summary + risk + ENSO into advisories per user type and language.
* Cost control: generate per cell-day-language-user_type in batch (`ai_query`) and cache
  in `gold.advisories`; generate only for cells with users or elevated risk.
* Guardrails: no invented numbers or causal claims (e.g. smoke test attributed rain to La
  Nina), values injected from gold. Evaluated with MLflow judges on a sample.

## 8. Lakebase - operational serving

* Lakebase project with synced tables from `gold.location_weather_summary`, `gold.risk_scores`,
  `gold.advisories` for low-latency app reads.
* Native OLTP tables: `user_profile` (location, language, user type), `citizen_feedback`
  (location, date, observed condition, forecast rating 1-5, sentiment/free text).
* Feedback written by the app is synced to `bronze.citizen_feedback_raw` (scheduled job or
  Lakehouse sync) and flows through silver/gold into model retraining and skill metrics.

## 9. Genie Agent

Genie space over gold tables for agency analysts, with instructions and sample questions, e.g.
"Which towns had the most flood reports during El Nino months?", "How accurate was the
forecast vs citizen reports last week in Costa Rica?". Separate from the app.

## 10. Databricks App

* Location selection: search city/town, pick on map, or enter coordinates (nearest grid point).
* Views: past 11 days, today, next 11 days; risk badges per hazard; ENSO card;
  personalized advisory (language + user type); feedback form (writes to Lakebase).
* Framework (decided): Dash (Plotly) + dash-leaflet maps. Python only, explicit callbacks,
  multi-page; runs on Flask/gunicorn so it scales horizontally, and REST routes on the same
  server can later feed SMS/mobile channels. Chosen over FastAPI + React: similar scalability
  for this load, far fewer files (30-file scorer limit) and easier to change.
* Auth via app service principal; Lakebase via OAuth tokens.

## 11. Repo and DAB layout

Path: `e2e_industry_solutions/weather_forecast_warning_comms/`

```
databricks.yml             # bundle, dev/prod targets
resources/                 # pipeline, jobs, serving endpoint, app, lakebase, genie notes
src/ingestion/             # API landing notebook
src/pipeline/              # SDP bronze/silver/gold
src/ml/                    # training, registration, advisory generation
src/app/                   # Databricks App
evidence/                  # run outputs as text (<9k chars per file)
README.md, ARCHITECTURE.md, PLAN.md, DECISIONS.md, CHANGELOG.md
```

FE Bar scorer limits: max 30 files, 9,000 chars/file, 90,000 chars total -> keep code files
concise, put key evidence in small text files. No secrets: use secret scopes / service principals.

## 12. Evidence plan

Notebook outputs, pipeline update summary, model metrics, advisories (2 languages x 3 user
types), Lakebase feedback round trip, Genie Q&A samples, app walkthrough.

## 13. Phases

| # | Phase | Done when |
| --- | --- | --- |
| 1 | Foundation: catalog, schemas, volume, bundle skeleton | `bundle validate` passes |
| 2 | Ingestion + SDP medallion | Gold tables populated for all 5 countries |
| 3 | ML model + serving | Endpoint returns scores; beats rules baseline |
| 4 | LLM advisories | Advisories in ES/EN for 3 user types, evaluated |
| 5 | Lakebase + feedback sync | App feedback appears in silver/gold |
| 6 | App + Genie | End-to-end demo works for a chosen town |
| 7 | Evidence, README, deck, push | Repo meets scorer limits, no secrets |

## 14. Key decisions and trade-offs

See DECISIONS.md (decision log with alternatives and rationale).

## 15. Open items

* Confirm Open-Meteo free-tier terms (non-commercial) fit the demo use.
