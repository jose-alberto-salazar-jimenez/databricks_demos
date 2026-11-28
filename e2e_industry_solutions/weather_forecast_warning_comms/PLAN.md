# Weather Forecast Warning Comms - PoC Plan

Proof of concept of what a civil protection agency would buy: weather forecasts, extreme events
and ENSO turned into location-specific, multilingual, preventive advisories, with citizen
feedback. Every FE Bar stage is built end to end at its smallest working size; the full product
is the roadmap (section 7). Public data only, no secrets, evidence readable as text.

Status: phases 1-2 built in dev (ingestion + medallion pipeline, full grid); see CHANGELOG.md.

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

Coverage (decided): land grid + towns.
* Grid: 20 km for PE/CO/EC (6,774 cells), 10 km for CR/PA (1,267), land only, lakes excluded
  (8,041 total; measured, see DECISIONS.md #4 and #11).
* Towns: GeoNames populated places (CC-BY), each mapped to its nearest grid cell, so any town
  or coordinate resolves to a cell (PoC: main towns only).
* Budget: fits Open-Meteo's free tier at 1 call/point; limits and horizon in ARCHITECTURE.md
  section 8, backfills in DECISIONS.md #12.

## 3. PoC scope by FE Bar stage

| Stage | PoC deliverable | Status |
| --- | --- | --- |
| Lakeflow | `daily_refresh` job: landing notebook (Open-Meteo, NOAA ONI, GDACS, reference data) -> SDP pipeline bronze/silver/gold with expectations | Built, full grid |
| Unity Catalog | Dev/prod catalogs, table comments, lineage; add `domain`/`pii` tags and a gold-only grant for the app service principal | Built; tags and grant to add |
| GenAI | Rule-based risk flags in gold + `gold.advisories` from `ai_query` (2 languages x 3 user types) | To build |
| Lakebase | Synced tables from the gold summary and advisories; `citizen_feedback` table written by the app | To build |
| Genie Agent | Space over the gold tables for agency analysts, with instructions and sample questions | To build |
| App | One-page Dash app: pick a town, see 13 days, risk flags, ENSO and the advisory; send feedback | To build |

## 4. Risk flags and advisories (GenAI)

* Flags per cell and day in `gold.location_weather_summary`: heavy rain, heat, strong wind
  (initial thresholds, tuned on the data: rain >= 50 mm/day, apparent max >= 35 C, gusts >= 60 km/h).
* Advisories only for flagged cells and the main towns, in ES/EN for citizens, farmers and
  municipalities; cached per cell, day, language and user type (DECISIONS #7).
* Model: `databricks-qwen3-next-80b-a3b-instruct`, fallback `databricks-gpt-oss-20b` (DECISIONS #6).
* Guardrails: prompts get values from gold only; no invented numbers or causes (the smoke test
  attributed rain to La Nina). A reviewed sample is kept as evidence.

## 5. App, Lakebase and Genie

* The app reads Lakebase only (synced tables) and writes feedback: location, date, observed
  condition, forecast rating 1-5, comment. Auth: app service principal, OAuth to Lakebase.
* Genie sample questions: "Which cells have heavy-rain flags in the next 3 days in Peru?",
  "Where does El Nino add drought risk?". Separate from the app.

## 6. Evidence plan

Pipeline and job run summaries (done), advisory samples (2 languages x 3 user types), Lakebase
feedback round trip, Genie Q&A samples, app walkthrough; one text file per phase in `evidence/`.

## 7. Out of scope for the PoC (roadmap)

| Item | Why deferred |
| --- | --- |
| Trained 72h risk model + serving endpoint | Needs labelled history; ERA5 backfill (code exists) and citizen feedback provide it |
| Feedback sync to bronze, forecast skill metrics | Needs feedback volume; the PoC shows the write path |
| User profiles, map picker, SMS channels | UX scale-out; town search covers the demo |
| Prod deployment by a service principal | Demo runs in one workspace (DECISIONS #14) |

## 8. Phases

| # | Phase | Done when |
| --- | --- | --- |
| 1 | Foundation (done) | `bundle validate` passes |
| 2 | Ingestion + SDP medallion (done) | Gold populated for all 5 countries |
| 3 | Risk flags + advisories | Advisories in ES/EN for 3 user types, sample reviewed |
| 4 | Lakebase + app | Feedback sent from the app lands in Lakebase for a chosen town |
| 5 | Genie + governance | Genie answers the sample questions; tags and grant applied |
| 6 | Evidence, deck, push | Scorer limits met (30 files, 9k chars/file, 90k total), no secrets |

## 9. Open items

* Confirm the LLM endpoints exist in the new workspace before phase 3.
* File budget: 24 of 30 used. Removing the ERA5 backfill code (`history_lib.py`,
  `backfill_sources`, `backfill.job.yml`) from the submitted folder would free 3 files (~11k chars).
* Confirm Open-Meteo free-tier terms (non-commercial) fit the demo use.

Decisions and trade-offs: DECISIONS.md. Architecture and data model: ARCHITECTURE.md.
