# Evidence - Phase 3: Medallion pipeline

Run date: 2026-11-27. Dev catalog `weather_forecast_warnings_comms_dev`, serverless SDP pipeline
`medallion`, fed by `ingest_sources` with `countries=CRI`, `max_points=50`. Workspace ids omitted.

## Pipeline update (validate, then full update): COMPLETED

| Layer | Dataset | Type | Rows |
| --- | --- | --- | --- |
| bronze | `open_meteo_forecast_raw` | streaming table | 50 |
| bronze | `enso_oni_raw` | streaming table | 922 |
| bronze | `gdacs_events_raw` | streaming table | 2 |
| silver | `dim_location` | materialized view | 8,060 |
| silver | `weather_forecast_daily` | materialized view | 650 |
| silver | `enso_phase_monthly` | materialized view | 921 |
| silver | `extreme_events` | materialized view | 2 |
| gold | `location_weather_summary` | materialized view | 50 |

Checks: 650 = 50 cells x 13 days (yesterday + today + 11); 921 = 922 ONI lines - header;
8,060 = phase 2 grid count; gold has one row per forecast cell.

## Expectations

All passed with 0 dropped rows, except `valid_coords` on bronze forecast: 9 of 50 warned. Cause:
the first bounding box (lon >= -85) cut off the Nicoya peninsula (CR cells reach -85.86); the
grid also reaches -91.6 (Galapagos) and 12.2N (San Andres). The box is now lat -19..13,
lon -92.5..-66.

## Gold sample (CRI, run_date 2026-11-27)

| cells | today temp max (C) | avg next-days max precip (mm) | max wind (km/h) | ENSO |
| --- | --- | --- | --- | --- |
| 50 | 13.8 - 33.0 | 31.0 | 26.9 | El Nino, ONI +2.46 (ASO 2026) |

Nulls in today / past columns: 0.

## Job wiring

`daily_refresh`: `ingest_sources` -> `medallion` (pipeline task). End-to-end run: SUCCESS. The
re-run skipped the already landed forecast batch (same fingerprint), so row counts stayed the
same: loads are idempotent per `run_date`.

## Full-grid run (all 5 countries, run_date 2026-11-27)

`daily_refresh` with defaults: SUCCESS. `ingest_sources` 67.8 min (8,060 points, 8,060 calls,
81 batches landed, 0 remaining; 34 GDACS events), then `medallion` 1.5 min.

| Dataset | Rows | Check |
| --- | --- | --- |
| bronze `open_meteo_forecast_raw` | 8,110 | 8,060 + 50 from the earlier test subset |
| silver `weather_forecast_daily` | 104,780 | 8,060 x 13 days; 0 duplicate keys; 13 days per cell |
| bronze / silver GDACS events | 34 / 32 | multi-country events deduplicated |
| gold `location_weather_summary` | 8,060 | every grid cell present |

Silver keeps the latest ingest per cell, run_date and request_mode, so overlapping re-runs
(test subset, then full grid) do not double-count. No expectation warnings or drops.

| Country | Cells | Today max temp (C) | Max daily precip next 11d (mm) | Max wind (km/h) |
| --- | --- | --- | --- | --- |
| COL | 2,861 | 8.5 - 39.1 | 117 | 45 |
| CRI | 520 | 12.0 - 35.6 | 131 | 47 |
| ECU | 632 | 6.5 - 34.3 | 136 | 23 |
| PAN | 752 | 11.3 - 35.6 | 84 | 31 |
| PER | 3,295 | -10.4 - 37.7 | 161 | 40 |

ENSO (sampled per country): El Nino, ONI +2.46. No null `today_temp_max` in any country.
GDACS events (silver): 26 earthquakes (Green), 4 floods (Green), 2 droughts (Orange).
Open item (resolved below): Lake Titicaca cells. `PER_20km_-16.02_-69.30` (3,809 m = lake level) has max -8.7 to
-11.7 C on all 13 days in the raw API response; 3 more cells within 0.4 deg do the same, while the
other 9 cells there show 14.8 to 18.7 C. A live call gives about -10 C with best_match, GFS and
ICON, and 16 C with ECMWF IFS (nearest grid point -16.0, -69.5). The values come from the source,
likely the lake surface in those models; the pipeline passes them through unchanged.

## Fix: lake cells removed (grid v2)

Natural Earth 10m lakes subtracted from the land grid. Preview vs. a grid-wide outlier scan (today's
high > 15 C below the median of cells within 0.4 deg): all 5 Titicaca outliers fall in a lake; the
mask also drops 14 water cells with normal values (9 Titicaca, 5 Lago Gatun, all at lake level).
The 3 outliers outside lakes are mountains (4,480 / 3,268 / 3,071 m) and stay.

Rebuild (`daily_refresh`, `sources=reference`, no Open-Meteo calls): SUCCESS. Grid 8,060 -> 8,041;
removed set = preview set (19), 0 added, other cell ids unchanged. PER 3,281, PAN 747, others as
before. `dim_location` and gold: 8,041 rows; 0 cells with a high below 0 C (PER min +1.5 C).

## Known issue

One run failed while GDACS answered HTTP 400 and then timed out for an unchanged query that had
succeeded an hour before. A GDACS outage currently fails the whole daily run.
