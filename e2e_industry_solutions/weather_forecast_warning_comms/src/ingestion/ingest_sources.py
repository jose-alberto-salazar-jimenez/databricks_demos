# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest sources -> landing volume (bronze input)
# MAGIC Daily task of the `daily_refresh` job. Lands raw files, one folder per source and `run_date`:
# MAGIC reference data if missing (Natural Earth boundaries and lakes, land grid `reference/grid_cells_v2/`,
# MAGIC GeoNames), then daily NOAA ONI, GDACS (last 30 days) and Open-Meteo (10 daily vars, yesterday +
# MAGIC today + 11 days, 1 call/point). Folders, free-tier limits and the `daily_call_budget` guard:
# MAGIC ARCHITECTURE.md sections 4 and 8. Landed batches for a `run_date` are skipped, so runs resume.
# MAGIC Code lives next to this notebook: `ingest_lib.py` (Open-Meteo, rate limiter, writers),
# MAGIC `context_lib.py` (grid, GeoNames, ENSO, GDACS), `source_registry.py` (sources, licenses, tags).
# MAGIC Every JSONL row carries `data_source`, `source_model` and `request_mode` (here: `daily`).

# COMMAND ----------

# DBTITLE 1,Parameters
import datetime as dt, json
import context_lib as ctx  # grid, GeoNames, ENSO, GDACS (same folder)
import ingest_lib as lib   # Open-Meteo downloader, rate limiter, writers
import source_registry as reg  # GRID_DIR and source metadata

dbutils.widgets.text("catalog", "weather_forecast_warnings_comms")
dbutils.widgets.text("schema", "bronze")
dbutils.widgets.text("volume", "landing")
dbutils.widgets.text("run_date", "")          # blank = today (UTC)
dbutils.widgets.text("countries", "PER,ECU,COL,PAN,CRI")
dbutils.widgets.text("max_points", "0")       # 0 = all grid points (testing: e.g. 50)
dbutils.widgets.text("sources", "reference,enso,gdacs,forecast")
dbutils.widgets.text("past_days", "1")       # yesterday
dbutils.widgets.text("forecast_days", "12")   # today + 11 days ahead
dbutils.widgets.text("daily_call_budget", "9500")  # stay under the 10k/day free tier

w = dbutils.widgets.get
ROOT = f"/Volumes/{w('catalog')}/{w('schema')}/{w('volume')}"
RUN_DATE = w("run_date") or dt.datetime.now(dt.timezone.utc).date().isoformat()
COUNTRIES = [c.strip() for c in w("countries").split(",") if c.strip()]
MAX_POINTS = int(w("max_points"))
SOURCES = set(s.strip() for s in w("sources").split(","))
PAST_DAYS, FORECAST_DAYS = int(w("past_days")), int(w("forecast_days"))
DAILY_CALL_BUDGET = float(w("daily_call_budget"))
INGESTED_AT = dt.datetime.now(dt.timezone.utc).isoformat()
summary = {"run_date": RUN_DATE}
print(ROOT, RUN_DATE, COUNTRIES, MAX_POINTS, SOURCES, PAST_DAYS, FORECAST_DAYS)

# COMMAND ----------

# DBTITLE 1,Reference: boundaries, land grid, GeoNames
GRID_DIR = f"{ROOT}/{reg.GRID_DIR}"
if "reference" in SOURCES:
    ctx.land_reference(spark, ROOT)  # source manifest; boundaries, lakes, GeoNames, land grid (if missing)

grid = spark.read.json(GRID_DIR).where(f"iso3 IN ({','.join(repr(c) for c in COUNTRIES)})")
display(grid.groupBy("iso3", "grid_km").count().orderBy("iso3"))

# COMMAND ----------

# DBTITLE 1,ENSO (NOAA ONI) and GDACS events
if "enso" in SOURCES:
    summary["enso_oni_lines"] = ctx.land_enso(ROOT, RUN_DATE)
if "gdacs" in SOURCES:
    summary["gdacs_events"] = ctx.land_gdacs(ROOT, RUN_DATE, COUNTRIES, INGESTED_AT)
print(summary)

# COMMAND ----------

# DBTITLE 1,Open-Meteo daily forecast (rate-limited, resumable)
if "forecast" in SOURCES:
    pts = grid.select("cell_id", "lat", "lon").orderBy("cell_id")
    pts = (pts.limit(MAX_POINTS) if MAX_POINTS else pts).collect()  # <= ~8k small rows
    summary.update(lib.land_forecast(ROOT, RUN_DATE, pts, PAST_DAYS, FORECAST_DAYS, INGESTED_AT, DAILY_CALL_BUDGET))

print(json.dumps(summary))
dbutils.notebook.exit(json.dumps(summary))
