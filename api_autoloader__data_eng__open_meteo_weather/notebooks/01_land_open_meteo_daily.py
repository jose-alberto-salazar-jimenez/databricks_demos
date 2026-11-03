# Databricks notebook source
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # Land Open-Meteo daily weather (raw JSON)
# MAGIC
# MAGIC Calls the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (free, no API key) for a regular lat/lon grid over a configurable bounding box and writes the raw responses as JSON Lines to a Unity Catalog volume. Auto Loader picks them up in `02_bronze_silver_open_meteo`.
# MAGIC
# MAGIC **All settings are widgets / job parameters** (see the Parameters cell). Only `catalog` is required; the default box is Costa Rica +/-10 degrees on a 1 degree grid.
# MAGIC
# MAGIC | Group | Parameters |
# MAGIC | --- | --- |
# MAGIC | Location | `catalog` (required), `schema`, `volume`, `landing_subdir`, `create_if_missing` |
# MAGIC | Window | `start_date`, `end_date`, `lookback_days` |
# MAGIC | Area | `lat_min`, `lat_max`, `lon_min`, `lon_max`, `grid_step_deg` |
# MAGIC | API | `api_url`, `daily_variables`, `timezone`, `api_key_secret_scope` + `api_key_secret_key` (paid plans), `locations_per_request`, `request_pause_seconds`, `max_retries`, `http_timeout_seconds` |
# MAGIC
# MAGIC Use the **same** `catalog`, `schema`, `volume`, `landing_subdir` and `daily_variables` values in `02_bronze_silver_open_meteo` (in a job, set them once as job parameters).
# MAGIC
# MAGIC * Default window: **yesterday** (in `timezone`). Set `start_date` / `end_date` to backfill.
# MAGIC * `lookback_days` > 1 re-pulls recent days (Open-Meteo revises recent data as ERA5 reanalysis lands ~5 days later). Silver MERGE keeps the latest version.
# MAGIC * Each run writes new files named `<run_id>_batchNNN.jsonl`, so reruns are picked up by Auto Loader and resolved in silver.
# MAGIC * Free tier limits: 10,000 calls/day, 600/min; one location = one call (more if > 10 variables or > 14 days per request). The notebook prints an estimate before calling the API. The free tier is for non-commercial use; commercial users need an Open-Meteo API plan (set `api_url` accordingly).

# COMMAND ----------

# DBTITLE 1,Parameters
# ---------- Unity Catalog location ----------
dbutils.widgets.text("catalog", "", "01 Catalog (required)")
dbutils.widgets.text("schema", "open_meteo", "02 Schema")
dbutils.widgets.text("volume", "raw", "03 Volume")
dbutils.widgets.text("landing_subdir", "landing/daily", "04 Landing folder inside volume")
dbutils.widgets.dropdown("create_if_missing", "true", ["true", "false"], "05 Create schema/volume if missing")

# ---------- Time window ----------
dbutils.widgets.text("start_date", "", "10 Start date YYYY-MM-DD (blank = auto)")
dbutils.widgets.text("end_date", "", "11 End date YYYY-MM-DD (blank = yesterday)")
dbutils.widgets.text("lookback_days", "1", "12 Lookback days (used when start_date blank)")

# ---------- Area / grid (default: Costa Rica +/-10 degrees) ----------
dbutils.widgets.text("lat_min", "-2", "20 Latitude min")
dbutils.widgets.text("lat_max", "21", "21 Latitude max")
dbutils.widgets.text("lon_min", "-96", "22 Longitude min")
dbutils.widgets.text("lon_max", "-72", "23 Longitude max")
dbutils.widgets.text("grid_step_deg", "1.0", "24 Grid step (degrees)")

# ---------- API ----------
DEFAULT_DAILY_VARIABLES = (
    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,rain_sum,"
    "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,shortwave_radiation_sum,weather_code"
)
dbutils.widgets.text("api_url", "https://archive-api.open-meteo.com/v1/archive", "30 API URL")
dbutils.widgets.text("daily_variables", DEFAULT_DAILY_VARIABLES, "31 Daily variables (comma-separated)")
dbutils.widgets.text("timezone", "GMT", "32 Timezone for daily aggregation")
dbutils.widgets.text("api_key_secret_scope", "", "33 API key secret scope (paid plans only)")
dbutils.widgets.text("api_key_secret_key", "", "34 API key secret key (paid plans only)")
dbutils.widgets.text("locations_per_request", "100", "35 Locations per request")
dbutils.widgets.text("request_pause_seconds", "1", "36 Pause between requests (s)")
dbutils.widgets.text("max_retries", "6", "37 Max retries per request")
dbutils.widgets.text("http_timeout_seconds", "120", "38 HTTP timeout (s)")

# COMMAND ----------

# DBTITLE 1,Parse and validate parameters
import datetime as dt, math, re
from zoneinfo import ZoneInfo

w = dbutils.widgets.get

def ident(name):
    v = w(name).strip()
    if not v:
        raise ValueError(f"Parameter '{name}' is required")
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", v):
        raise ValueError(f"Parameter '{name}' has invalid characters: {v!r}")
    return v

CATALOG, SCHEMA, VOLUME = ident("catalog"), ident("schema"), ident("volume")
LANDING_SUBDIR = w("landing_subdir").strip().strip("/")
CREATE_IF_MISSING = w("create_if_missing").lower() == "true"
LANDING = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{LANDING_SUBDIR}"

# API
API_URL = w("api_url").strip()
DAILY_VARS = [v.strip() for v in w("daily_variables").split(",") if v.strip()]
TZ = w("timezone").strip() or "GMT"
BATCH = int(w("locations_per_request"))
PAUSE = float(w("request_pause_seconds"))
MAX_RETRIES = int(w("max_retries"))
HTTP_TIMEOUT = int(w("http_timeout_seconds"))
API_KEY = (dbutils.secrets.get(w("api_key_secret_scope"), w("api_key_secret_key"))
           if w("api_key_secret_scope") and w("api_key_secret_key") else None)
assert DAILY_VARS, "daily_variables must not be empty"
assert 1 <= BATCH <= 1000, "locations_per_request must be between 1 and 1000"

# Window ("yesterday" is evaluated in the aggregation timezone)
yesterday = dt.datetime.now(ZoneInfo(TZ)).date() - dt.timedelta(days=1)
lookback = int(w("lookback_days") or 1)
assert lookback >= 1, "lookback_days must be >= 1"
END = dt.date.fromisoformat(w("end_date")) if w("end_date") else yesterday
START = dt.date.fromisoformat(w("start_date")) if w("start_date") else END - dt.timedelta(days=lookback - 1)
assert START <= END <= yesterday, f"Invalid window {START}..{END} (must end on or before {yesterday})"
DAYS = (END - START).days + 1

# Area / grid
STEP = float(w("grid_step_deg"))
LAT_MIN, LAT_MAX = float(w("lat_min")), float(w("lat_max"))
LON_MIN, LON_MAX = float(w("lon_min")), float(w("lon_max"))
assert STEP > 0, "grid_step_deg must be > 0"
assert -90 <= LAT_MIN <= LAT_MAX <= 90, "latitude bounds must satisfy -90 <= lat_min <= lat_max <= 90"
assert -180 <= LON_MIN <= LON_MAX <= 180, "longitude bounds must satisfy -180 <= lon_min <= lon_max <= 180"

print(f"Target  : {LANDING}")
print(f"Window  : {START}..{END} ({DAYS} day(s), timezone {TZ})")
print(f"Box     : lat {LAT_MIN}..{LAT_MAX}, lon {LON_MIN}..{LON_MAX}, step {STEP}")
print(f"API     : {API_URL} | {len(DAILY_VARS)} variables | api key: {'yes' if API_KEY else 'no'}")

# COMMAND ----------

# DBTITLE 1,Create schema and volume (optional)
if CREATE_IF_MISSING:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`")
    spark.sql(f"CREATE VOLUME IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`.`{VOLUME}`")
else:
    spark.sql(f"DESCRIBE VOLUME `{CATALOG}`.`{SCHEMA}`.`{VOLUME}`")  # fail fast if it does not exist

# COMMAND ----------

# DBTITLE 1,Build grid and estimate API usage
def frange(a, b, s):
    n = int(math.floor((b - a) / s + 1e-9))
    return [round(a + i * s, 6) for i in range(n + 1)]

POINTS = [(la, lo) for la in frange(LAT_MIN, LAT_MAX, STEP) for lo in frange(LON_MIN, LON_MAX, STEP)]

# Open-Meteo counts one call per location, weighted by >10 variables and >14 days per request
weight = max(1.0, len(DAILY_VARS) / 10) * max(1.0, DAYS / 14)
est_calls = math.ceil(len(POINTS) * weight)
print(f"{len(POINTS)} grid points -> ~{est_calls} API calls")
if est_calls > 10_000:
    print("WARNING: estimate exceeds the free-tier daily limit (10,000). Split the backfill into smaller "
          "windows, use a coarser grid, or use a paid plan.")

# COMMAND ----------

# DBTITLE 1,Fetch from Open-Meteo and land JSON
import json, os, time, requests

session = requests.Session()

def fetch(batch):
    params = dict(
        latitude=",".join(str(p[0]) for p in batch),
        longitude=",".join(str(p[1]) for p in batch),
        start_date=START.isoformat(), end_date=END.isoformat(),
        daily=",".join(DAILY_VARS), timezone=TZ,
    )
    if API_KEY:
        params["apikey"] = API_KEY
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(API_URL, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:  # timeouts / connection resets
            wait = 5 * 2 ** attempt
            print(f"Request error ({e.__class__.__name__}), retrying in {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 200:
            try:
                body = r.json()
            except ValueError:  # occasionally an empty / non-JSON 200 body under load
                wait = 5 * 2 ** attempt
                print(f"Non-JSON 200 response ({len(r.content)} bytes), retrying in {wait}s: {r.text[:200]!r}")
                time.sleep(wait)
                continue
            return body if isinstance(body, list) else [body]
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(60 * (attempt + 1), 300) if r.status_code == 429 else 5 * 2 ** attempt
            print(f"HTTP {r.status_code}, retrying in {wait}s: {r.text[:200]}")
            time.sleep(wait)
            continue
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    raise RuntimeError(f"Open-Meteo request failed after {MAX_RETRIES} attempts")

run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
folder = f"{LANDING}/start_date={START.isoformat()}"
os.makedirs(folder, exist_ok=True)

written, files = 0, []
for i in range(0, len(POINTS), BATCH):
    batch = POINTS[i:i + BATCH]
    results = fetch(batch)
    if len(results) != len(batch):
        raise RuntimeError(f"Expected {len(batch)} locations, got {len(results)}")
    lines = [
        json.dumps({**res, "grid_latitude": p[0], "grid_longitude": p[1],
                    "request_start_date": START.isoformat(), "request_end_date": END.isoformat(),
                    "run_id": run_id})
        for p, res in zip(batch, results)
    ]
    path = f"{folder}/{run_id}_batch{i // BATCH:03d}.jsonl"
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    written += len(lines); files.append(path)
    time.sleep(PAUSE)

print(f"run_id={run_id}: wrote {written} locations x {DAYS} day(s) into {len(files)} files under {folder}")
assert written == len(POINTS)
dbutils.jobs.taskValues.set("run_id", run_id)
dbutils.jobs.taskValues.set("grid_points", len(POINTS))