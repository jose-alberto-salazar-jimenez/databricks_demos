# Evidence - Phase 2: Ingestion

Run date: 2026-11-11. Test run of `src/ingestion/ingest_sources` on the dev landing volume with
`countries=CRI`, `max_points=150` (full reference data, partial forecast).

## Source checks (from serverless)

All reachable with HTTP 200: Open-Meteo forecast (multi-location), NOAA CPC `oni.ascii.txt`,
GDACS `geteventlist/SEARCH` (204 when no events), GeoNames country dumps, Natural Earth 10m.

Open-Meteo free tier, read from its terms and pricing pages: <10,000 calls/day, 5,000/hour,
600/min, 300,000/month, non-commercial, CC-BY 4.0. More than 10 variables or 14 days per
location counts as extra (fractional) calls.

## Notebook exit summary

```
{"run_date": "2026-11-11", "enso_oni_lines": 922, "gdacs_events": 4,
 "forecast_points": 150, "forecast_api_calls": 150, "forecast_batches_skipped": 0}
```

## Landing volume layout

```
enso_oni/run_date=2026-11-11/
gdacs/run_date=2026-11-11/
geonames/  CO.txt CR.txt EC.txt PA.txt PE.txt
open_meteo_forecast/run_date=2026-11-11/
reference/ grid_cells/ natural_earth/
```

## Land grid (reference/grid_cells)

| iso3 | grid_km | cells |
| --- | --- | --- |
| COL | 20 | 2,861 |
| CRI | 10 | 520 |
| ECU | 20 | 632 |
| PAN | 10 | 752 |
| PER | 20 | 3,295 |

Total 8,060 rows, 8,060 distinct `cell_id`. Sanity check against country area / cell area:
Peru ~3,200, Colombia ~2,850, Costa Rica ~510, Panama ~750 expected.

## Forecast batch check (Spark read of the landed JSONL)

| rows | distinct cells | days per row | first day | last day | max lat snap (deg) | rows with null precip |
| --- | --- | --- | --- | --- | --- | --- |
| 150 | 150 | 14 | 2026-11-10 | 2026-11-23 | 0.078 | 0 |

## GDACS (Costa Rica, last 30 days query)

4 events: 2 droughts (multi-country, Green and Orange), 1 flood (Green), 1 earthquake (Green).
Multi-country events repeat across country files, so silver must deduplicate by event id.

## GeoNames populated places (feature class P)

CR 5,901 | PA 13,267 | CO 35,945 | EC 11,458 | PE 47,493

## Bundle

`bundle validate --strict` passes for `dev` and `prod` with `resources/daily_refresh.job.yml`.
