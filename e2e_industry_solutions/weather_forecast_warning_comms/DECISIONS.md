# Decisions and Trade-offs - Weather Forecast Warning Comms

Log of design decisions (owner: Jose Alberto Salazar Jimenez). See PLAN.md for the build plan.

| # | Decision | Alternatives considered | Why |
| --- | --- | --- | --- |
| 1 | Public sector (civil protection) framing | Insurance, agriculture, utilities | Clearest citizen-facing value; farmers covered as a user type |
| 2 | Region: PE, EC, CO, PA, CR | Single country, global | Contrasting ENSO impacts (Pacific vs Caribbean, coast vs Andes) |
| 3 | One refresh per day (batch) | Hourly / streaming | Enough for preventive advisories; keeps API use in free tier and cost low |
| 4 | Grid 20 km (PE/CO/EC), 10 km (CR/PA) + all GeoNames towns mapped to nearest cell | Uniform 10 km; town list only | 8,060 points/day fits Open-Meteo free quota; any town/coordinate resolves |
| 5 | Dash (Plotly) + dash-leaflet app | Streamlit (rejected by owner), FastAPI + React | Python only, explicit callbacks, horizontal scaling on gunicorn, few files (scorer limit) |
| 6 | LLM: databricks-qwen3-next-80b-a3b-instruct, fallback databricks-gpt-oss-20b | Frontier paid models | Open-weight, low cost at ~8k cells x languages x user types; good Spanish in smoke test |
| 7 | Cached batch advisories in gold | On-demand generation per request | Cost and latency control; on-demand only for free-text Q&A |
| 8 | Lakebase for app reads/writes | App querying a SQL warehouse | Low-latency reads and OLTP writes for feedback |
| 9 | Citizen feedback as weak labels | Treat as ground truth | Noisy and biased; used for skill metrics and features, not sole labels |
| 10 | Horizon +/- 11 days: daily request = yesterday + today + 11 days (13 days); past 11 days built from stored runs, one-off backfill | Request 11 past + 12 ahead every day (23 days); 16 days, hourly data | 23 days costs 1.64 calls/point = 13.2k/day, over the 10k free limit; 13 days keeps 1 call/point (8,060/day) |
| 11 | Land mask from Natural Earth 10m boundaries on a global lattice | Bounding boxes, H3 cells | No ocean points wasted; stable cell ids across runs |
| 12 | Backfills: one-off past 11 days for all cells (forecast API) + 2-year ERA5 history for a sample (GDACS-event cells + 60 random per country) | 91-day daily window; full-grid ERA5 | 91 days daily = 59k calls/day; full-grid 2-year ERA5 ~420k calls. Sample keeps real events for ML at ~a few days of quota |
| 13 | Every row tagged `data_source`, `source_model`, `request_mode` + `dim_data_source` from one registry | Infer source from folder only | Sources mix (forecast past days vs ERA5 reanalysis); lineage must stay visible in silver/gold and the app |
