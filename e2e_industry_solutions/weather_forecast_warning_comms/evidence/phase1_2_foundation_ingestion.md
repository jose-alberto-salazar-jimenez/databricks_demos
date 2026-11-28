# Evidence - Phases 1 and 2: Foundation, ingestion and medallion pipeline

Phase 1 and the first ingestion test ran 2026-11-11 in the original workspace (since deleted);
everything was rebuilt and re-run in the current workspace on 2026-11-27. Identifiers omitted.

## Phase 1: Foundation

Catalogs `weather_forecast_warnings_comms` (prod) and `..._dev` (dev), each with `bronze`, `silver`,
`gold`. `bundle validate --strict` passes for `dev` and `prod`; `bundle deploy -t dev` created the
managed `bronze.landing` volume (jobs and pipeline were added in phase 2).

## Phase 2: Sources and limits

All sources answered HTTP 200 from serverless (GDACS: 204 when no events). Open-Meteo free tier
(terms and pricing pages): <10,000 calls/day, 5,000/hour, 600/min, 300,000/month, non-commercial,
CC-BY 4.0; more than 10 variables or 14 days per location count as extra calls.
GeoNames populated places: CR 5,901 | PA 13,267 | CO 35,945 | EC 11,458 | PE 47,493.
Multi-country GDACS events repeat across country files, so silver deduplicates by event id.

## Full-grid run (`daily_refresh`, run_date 2026-11-27): SUCCESS

`ingest_sources` 67.8 min (8,060 points, 8,060 calls, 81 batches, 34 GDACS events), then the
`medallion` pipeline 1.5 min. Grid v1 then; v2 below.

| Dataset | Rows | Check |
| --- | --- | --- |
| bronze `open_meteo_forecast_raw` | 8,110 | 8,060 + 50 from an earlier test |
| silver `weather_forecast_daily` | 104,780 | 8,060 x 13 days; 0 duplicate keys |
| bronze / silver ENSO | 922 / 921 | ONI lines minus header |
| bronze / silver GDACS events | 34 / 32 | multi-country events deduplicated |
| gold `location_weather_summary` | 8,060 | every grid cell present |

Silver keeps the latest ingest per cell, run_date and request_mode, and a re-run of a
`run_date` skips landed batches, so loads are idempotent. ENSO: El Nino, ONI +2.46.

| Country | Cells | Today max temp (C) | Max daily precip next 11d (mm) | Max wind (km/h) |
| --- | --- | --- | --- | --- |
| COL | 2,861 | 8.5 - 39.1 | 117 | 45 |
| CRI | 520 | 12.0 - 35.6 | 131 | 47 |
| ECU | 632 | 6.5 - 34.3 | 136 | 23 |
| PAN | 752 | 11.3 - 35.6 | 84 | 31 |
| PER | 3,295 | -10.4 - 37.7 | 161 | 40 |

## Expectations

`valid_coords` warned on 9 of 50 test rows: the first box (lon >= -85) cut off Nicoya (Costa Rica
reaches -85.86); the grid also reaches -91.6 (Galapagos) and 12.2N (San Andres). The box is now
lat -19..13, lon -92.5..-66. All other expectations: 0 warned, 0 dropped.

## Lake cells (grid v2)

Peru's -10.4 C came from Lake Titicaca: cell `PER_20km_-16.02_-69.30` (3,809 m = lake level) had
raw API highs of -8.7 to -11.7 C on all 13 days; 3 more cells within 0.4 deg did the same, while
the other 9 there showed 14.8 to 18.7 C. A live call gives
about -10 C with best_match, GFS and ICON and 16 C with ECMWF IFS: source values, likely the
lake surface in those models. Fix: Natural Earth 10m lakes removed from the grid. All 5
Titicaca outliers fall in a lake; 14 more water cells go (9 Titicaca, 5 Lago Gatun); the 3
outliers outside lakes are mountains (4,480 / 3,268 / 3,071 m) and stay. Rebuild: 8,060 ->
8,041 (PER 3,281, PAN 747); removed = preview set (19), 0 added, other ids unchanged; gold
8,041 rows, 0 highs below 0 C.

Merging the bronze SQL into one file kept table and flow names: the next update reprocessed
nothing (all 8 tables kept their row counts).

## Known issue

One run failed while GDACS answered HTTP 400 and then timed out; a GDACS outage fails the whole
daily run.
