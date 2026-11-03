# Open-Meteo weather ingestion: REST API -> Auto Loader -> bronze / silver

Incremental, daily batch ingestion of **yesterday's weather** from the free [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) for a regular latitude/longitude grid, landed in Unity Catalog and loaded with Auto Loader into a bronze and a silver Delta table, orchestrated by a Lakeflow Job.

The default area is **Costa Rica +/-10 degrees** (latitude -2 to 21, longitude -96 to -72) on a **1 degree grid (600 points)**, but every setting is a notebook widget / job parameter, so you can point it at any region.

## What it shows

* How to ingest a **REST API** incrementally with a *land-then-load* pattern, so Auto Loader can be used even though the source is not files.
* **Idempotent, rerunnable** loads: reruns, backfills and upstream data revisions never create duplicates.
* A **parameterized** two-task Lakeflow Job on serverless compute that can be shared and reused as-is.

## Architecture

```
 Open-Meteo API  --(1) 01_land_open_meteo_daily-->  UC volume: /Volumes/<catalog>/<schema>/<volume>/landing/daily/
 (HTTP, JSON)        one request per 100 points         start_date=YYYY-MM-DD/<run_id>_batchNNN.jsonl   (raw, immutable)
                                                                 |
                                   (2) 02_bronze_silver_open_meteo  |  Auto Loader (availableNow)
                                                                 v
                                     <catalog>.<schema>.bronze_open_meteo_daily   (append-only raw responses)
                                                                 |
                                                                 |  incremental stream + foreachBatch MERGE
                                                                 v
                                     <catalog>.<schema>.silver_open_meteo_daily   (1 row per grid point per day)
```

### Why land files first instead of writing straight to a table?

Auto Loader reads **files** from cloud storage; it cannot call an API. Landing the raw API responses in a volume first gives you:

* **Replayability**: the raw responses are kept, so you can rebuild bronze/silver (new columns, bug fixes) without calling the API again.
* **Decoupling**: the API call (slow, rate-limited, can fail) is separate from the Spark load (fast, retryable).
* **Exactly-once loading for free**: Auto Loader tracks which files were already ingested via its checkpoint.
* **Auditability**: every bronze row carries `_source_file` and `_ingested_at`.

For small payloads a single notebook that MERGEs directly into a Delta table also works; this pattern scales better and is easier to operate.

## Folder contents

| Path | Description |
| --- | --- |
| [notebooks/01_land_open_meteo_daily.py](notebooks/01_land_open_meteo_daily.py) | Builds the grid, calls Open-Meteo in batches (with retries and rate-limit backoff), writes raw JSON Lines to the landing volume. Optionally creates the schema and volume. |
| [notebooks/02_bronze_silver_open_meteo.py](notebooks/02_bronze_silver_open_meteo.py) | Auto Loader into bronze, incremental MERGE into silver, data quality checks. |
| [job/open_meteo_daily_ingestion_job.json](job/open_meteo_daily_ingestion_job.json) | Lakeflow Job definition (Jobs API 2.2 format) wiring the two notebooks, with all parameters. |

## Prerequisites

* A Unity Catalog-enabled workspace and a catalog where you can `CREATE SCHEMA` and `CREATE VOLUME` (or an existing schema/volume with write access; set `create_if_missing=false`).
* **Serverless compute** (recommended) or a cluster on Databricks Runtime **15.4 LTS or above** (needed for `MERGE WITH SCHEMA EVOLUTION`).
* **Outbound internet access** from the compute to `archive-api.open-meteo.com`. If your workspace restricts egress (serverless network policies or a firewall), allow this host.
* No API key for the free tier. See [API limits and licensing](#api-limits-and-licensing).

## Quick start

1. **Get the code.** In your workspace, create a Git folder from this repo (**Workspace > Create > Git folder**), or import the two notebooks.
2. **Try it interactively (optional).** Open `01_land_open_meteo_daily`, set the `catalog` widget, run all. Then open `02_bronze_silver_open_meteo`, set the same `catalog`, run all.
3. **Create the job.** Edit [job/open_meteo_daily_ingestion_job.json](job/open_meteo_daily_ingestion_job.json):
   * replace `<GIT_FOLDER_PATH>` with the workspace path of your Git folder (for example `/Workspace/Users/you@company.com/databricks_demos`),
   * replace `<CATALOG>` with your catalog name,

   then create it with the Databricks CLI:

   ```bash
   databricks jobs create --json @job/open_meteo_daily_ingestion_job.json
   ```

   With no cluster specified, the tasks run on serverless compute. You can also build the job in the UI: two notebook tasks, `bronze_silver_open_meteo` depending on `land_open_meteo`, plus the job parameters from the JSON.
4. **Run it once** (**Run now**) and check the tables (queries below).
5. **Enable the schedule.** The template ships **paused** at 06:00 UTC daily; unpause it in the job's **Schedules & Triggers**. 06:00 UTC gives Open-Meteo time to close out the previous day.

## Parameters

All parameters are notebook widgets. In a job, define them once as **job parameters**: they are passed to both tasks, which keeps the shared ones (`catalog`, `schema`, `volume`, `landing_subdir`, `daily_variables`) in sync.

### Location (both notebooks)

| Parameter | Default | Description |
| --- | --- | --- |
| `catalog` | *(required)* | Target Unity Catalog catalog. |
| `schema` | `open_meteo` | Target schema. |
| `volume` | `raw` | Volume for raw files and checkpoints. |
| `landing_subdir` | `landing/daily` | Folder inside the volume for raw API responses. |
| `create_if_missing` | `true` | (01) Create the schema and volume if they do not exist. |
| `checkpoint_subdir` | `_checkpoints` | (02) Folder inside the volume for Auto Loader schema and stream checkpoints. |

### Time window (01)

| Parameter | Default | Description |
| --- | --- | --- |
| `start_date` | *(blank)* | First day to fetch, `YYYY-MM-DD`. Blank = `end_date - (lookback_days - 1)`. |
| `end_date` | *(blank)* | Last day to fetch. Blank = **yesterday** in `timezone`. Must not be later than yesterday. |
| `lookback_days` | `1` | Days to (re)fetch when `start_date` is blank. Use `5` to pick up Open-Meteo's revisions of recent days (see below). |

### Area (01)

| Parameter | Default | Description |
| --- | --- | --- |
| `lat_min`, `lat_max` | `-2`, `21` | Latitude bounds (inclusive). |
| `lon_min`, `lon_max` | `-96`, `-72` | Longitude bounds (inclusive). |
| `grid_step_deg` | `1.0` | Grid spacing in degrees. Points = `(lat range / step + 1) x (lon range / step + 1)`. |

### API (01)

| Parameter | Default | Description |
| --- | --- | --- |
| `api_url` | `https://archive-api.open-meteo.com/v1/archive` | Endpoint. Change for a paid plan (`customer-archive-api.open-meteo.com`) or a self-hosted instance. |
| `daily_variables` | 10 variables (below) | Comma-separated [daily variables](https://open-meteo.com/en/docs/historical-weather-api). **Also set in 02.** |
| `timezone` | `GMT` | Timezone that defines a "day" for daily aggregation and for "yesterday" (for example `America/Costa_Rica`). |
| `api_key_secret_scope`, `api_key_secret_key` | *(blank)* | Paid plans only: secret holding the Open-Meteo API key, sent as `apikey`. |
| `locations_per_request` | `100` | Points per HTTP request. |
| `request_pause_seconds` | `1` | Pause between requests. |
| `max_retries` | `6` | Attempts per request (429, 5xx, timeouts and truncated responses are retried with backoff). |
| `http_timeout_seconds` | `120` | HTTP timeout per request. |

### Tables and data quality (02)

| Parameter | Default | Description |
| --- | --- | --- |
| `bronze_table` | `bronze_open_meteo_daily` | Bronze table name. |
| `silver_table` | `silver_open_meteo_daily` | Silver table name. |
| `landing_task_key` | `land_open_meteo` | Task key of the landing task, used to read its task values (`run_id`, `grid_points`) for DQ checks. |
| `fail_on_dq_error` | `true` | Fail the run if DQ checks fail (otherwise only print a warning). |

## Output tables

### `bronze_open_meteo_daily`

One row per grid point per landing run: the raw API response (`daily` struct of arrays, `daily_units`, `latitude`, `longitude`, `elevation`, ...) plus `grid_latitude`, `grid_longitude`, `request_start_date`, `request_end_date`, `run_id`, `_source_file`, `_ingested_at`. Append-only; it keeps every version, including partial runs.

### `silver_open_meteo_daily`

One row per **grid point per day** (key: `grid_latitude`, `grid_longitude`, `weather_date`), liquid-clustered by `weather_date`.

| Column | Description |
| --- | --- |
| `grid_latitude`, `grid_longitude` | Requested grid point. |
| `weather_date` | Day (in `timezone`). |
| `model_latitude`, `model_longitude`, `elevation_m` | Model cell Open-Meteo actually used (it snaps to its own grid). |
| `temperature_2m_max_c`, `temperature_2m_min_c`, `temperature_2m_mean_c` | Air temperature at 2 m, degrees C. |
| `precipitation_sum_mm`, `rain_sum_mm` | Daily precipitation / rain, mm. |
| `wind_speed_10m_max_kmh`, `wind_gusts_10m_max_kmh` | Max wind speed / gusts at 10 m, km/h. |
| `wind_direction_10m_dominant_deg` | Dominant wind direction, degrees. |
| `shortwave_radiation_sum_mj_m2` | Solar radiation, MJ/m2. |
| `weather_code` | [WMO weather code](https://open-meteo.com/en/docs#weather_variable_documentation). |
| `run_id`, `_source_file`, `_ingested_at`, `_updated_at` | Lineage: which landing run and file produced the row. |

Variable columns follow `daily_variables`: known variables get a unit suffix, unknown ones keep the Open-Meteo name (units remain available in bronze `daily_units`).

## How incremental loading works

* **Landing**: every run writes **new** files named `<run_id>_batchNNN.jsonl` (`run_id` = UTC timestamp), so nothing is overwritten and Auto Loader sees reruns as new files.
* **Bronze**: Auto Loader with `trigger(availableNow=True)` processes only files not yet recorded in its checkpoint, then stops: batch cost, streaming bookkeeping.
* **Silver**: a stream over the bronze table processes only new bronze rows. Each micro-batch is flattened (one row per day), deduplicated, and `MERGE`d on the key. A row is only overwritten by a run with the same or a later `run_id`, so **the latest pull always wins** and replays of old data cannot overwrite newer values.
* **Data revisions**: Open-Meteo's recent days are preliminary and get replaced by ERA5 reanalysis about 5 days later. Set `lookback_days=5` to re-pull the last 5 days every run; the MERGE updates them in place.

## Common operations

**Backfill a date range**: run the job with parameters, for example `start_date=2026-01-01`, `end_date=2026-01-31`. Keep each run within the API budget (see the estimate the landing notebook prints); split long backfills into several runs.

**Change the area or grid**: set `lat_*`, `lon_*`, `grid_step_deg`. Existing points stay in silver; new points are added.

**Add variables**: append them to `daily_variables` (job parameter, so both tasks see it). New bronze fields stop the Auto Loader stream once (`addNewColumns` schema evolution) and the task retry picks them up; silver adds the columns via `MERGE WITH SCHEMA EVOLUTION`. Older days have `NULL` for new columns until backfilled.

**Start over**: drop the bronze and silver tables and delete the `<checkpoint_subdir>` folder in the volume (or use a new `checkpoint_subdir`). The raw files stay, so bronze/silver are rebuilt from the landing folder without calling the API. If you rename tables or the landing folder on an existing deployment, also use a new `checkpoint_subdir`.

## Example queries

```sql
-- Coverage and freshness per day
SELECT weather_date, count(*) AS points, round(avg(temperature_2m_mean_c), 1) AS avg_temp_c
FROM <catalog>.open_meteo.silver_open_meteo_daily
GROUP BY weather_date ORDER BY weather_date DESC;

-- Wettest grid points yesterday
SELECT grid_latitude, grid_longitude, precipitation_sum_mm
FROM <catalog>.open_meteo.silver_open_meteo_daily
WHERE weather_date = current_date() - 1
ORDER BY precipitation_sum_mm DESC LIMIT 10;
```

## Data quality checks

`02_bronze_silver_open_meteo` ends with checks that fail the run (unless `fail_on_dq_error=false`):

* no duplicate keys in silver;
* in a job, every day landed by this run has exactly as many points as the grid (`grid_points` task value from the landing task).

It also displays points per day and null counts for the last 7 days.

## API limits and licensing

* Free tier: about **10,000 calls/day, 5,000/hour, 600/minute**. One location counts as one call, weighted up when a request asks for more than 10 variables or more than 2 weeks of data. The default setup uses about 600 calls/day.
* The free API is for **non-commercial use**. Commercial use needs an [Open-Meteo API subscription](https://open-meteo.com/en/pricing): set `api_url` to the customer endpoint and store the key in a [secret scope](https://docs.databricks.com/aws/en/security/secrets/) (`api_key_secret_scope` / `api_key_secret_key`).
* Data is licensed under [CC BY 4.0](https://open-meteo.com/en/license): attribute Open-Meteo when you publish it.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `Parameter 'catalog' is required` / `invalid characters` | Set `catalog` (the job template ships with the placeholder `<CATALOG>`). |
| Connection errors or timeouts on every request | Compute has no egress to `archive-api.open-meteo.com`; allow it in your network policy or firewall. |
| HTTP 429 | Rate limit hit; the notebook backs off and retries. For big backfills, raise `request_pause_seconds` or split the date range. |
| `Non-JSON 200 response ... retrying` in the logs | Open-Meteo occasionally returns truncated bodies under load; retried automatically. |
| Bronze task fails once after adding variables | Expected Auto Loader schema evolution; the task retry continues. |
| DQ error: dates without N points | A landing request returned fewer locations; rerun the job (the MERGE keeps the latest complete data). |

## Clean up

```sql
DROP SCHEMA <catalog>.open_meteo CASCADE;  -- drops tables and the volume (raw files and checkpoints)
```

Then delete the job.
