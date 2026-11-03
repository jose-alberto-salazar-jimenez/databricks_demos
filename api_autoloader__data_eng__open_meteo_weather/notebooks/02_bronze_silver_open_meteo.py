# Databricks notebook source
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # Open-Meteo: landing -> bronze -> silver
# MAGIC
# MAGIC **All settings are widgets / job parameters** (see the Parameters cell). Only `catalog` is required.
# MAGIC
# MAGIC | Group | Parameters |
# MAGIC | --- | --- |
# MAGIC | Location | `catalog` (required), `schema`, `volume`, `landing_subdir`, `checkpoint_subdir` |
# MAGIC | Tables | `bronze_table`, `silver_table` |
# MAGIC | Data | `daily_variables` (same list as the landing notebook; silver columns get unit suffixes, new variables are added via schema evolution) |
# MAGIC | Data quality | `landing_task_key`, `fail_on_dq_error` |
# MAGIC
# MAGIC 1. **Bronze** (`bronze_table`, default `bronze_open_meteo_daily`): Auto Loader (`availableNow`) appends new raw JSON files from the landing volume, with `_source_file` and `_ingested_at`. Raw responses, append-only.
# MAGIC 2. **Silver** (`silver_table`, default `silver_open_meteo_daily`): incremental read of new bronze rows, flattened to one row per grid point per day, MERGE on (`grid_latitude`, `grid_longitude`, `weather_date`); the latest `run_id` wins (handles reruns and data revisions).
# MAGIC
# MAGIC Checkpoints live in `/Volumes/<catalog>/<schema>/<volume>/<checkpoint_subdir>`. If you change the landing folder or table names on an existing deployment, also use a new `checkpoint_subdir`.

# COMMAND ----------

# DBTITLE 1,Parameters
# ---------- Unity Catalog location (must match 01_land_open_meteo_daily) ----------
dbutils.widgets.text("catalog", "", "01 Catalog (required)")
dbutils.widgets.text("schema", "open_meteo", "02 Schema")
dbutils.widgets.text("volume", "raw", "03 Volume")
dbutils.widgets.text("landing_subdir", "landing/daily", "04 Landing folder inside volume")
dbutils.widgets.text("checkpoint_subdir", "_checkpoints", "05 Checkpoint folder inside volume")

# ---------- Tables ----------
dbutils.widgets.text("bronze_table", "bronze_open_meteo_daily", "10 Bronze table name")
dbutils.widgets.text("silver_table", "silver_open_meteo_daily", "11 Silver table name")

# ---------- Data ----------
DEFAULT_DAILY_VARIABLES = (
    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,rain_sum,"
    "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,shortwave_radiation_sum,weather_code"
)
dbutils.widgets.text("daily_variables", DEFAULT_DAILY_VARIABLES, "20 Daily variables (comma-separated)")

# ---------- Data quality ----------
dbutils.widgets.text("landing_task_key", "land_open_meteo", "30 Landing task key (job only, for DQ)")
dbutils.widgets.dropdown("fail_on_dq_error", "true", ["true", "false"], "31 Fail run on DQ error")

# COMMAND ----------

# DBTITLE 1,Parse parameters and column mapping
import re
from pyspark.sql import functions as F, Window

w = dbutils.widgets.get

def ident(name):
    v = w(name).strip()
    if not v:
        raise ValueError(f"Parameter '{name}' is required")
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", v):
        raise ValueError(f"Parameter '{name}' has invalid characters: {v!r}")
    return v

CATALOG, SCHEMA, VOLUME = ident("catalog"), ident("schema"), ident("volume")
BASE = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
LANDING = f"{BASE}/{w('landing_subdir').strip().strip('/')}"
# Note: checkpoints track what was already processed. Changing landing/table names on an existing
# deployment should come with a new checkpoint_subdir.
CKPT = f"{BASE}/{w('checkpoint_subdir').strip().strip('/')}"
BRONZE = f"`{CATALOG}`.`{SCHEMA}`.`{ident('bronze_table')}`"
SILVER = f"`{CATALOG}`.`{SCHEMA}`.`{ident('silver_table')}`"
DAILY_VARS = [v.strip() for v in w("daily_variables").split(",") if v.strip()]
FAIL_ON_DQ = w("fail_on_dq_error").lower() == "true"
assert DAILY_VARS, "daily_variables must not be empty"

# Silver column = Open-Meteo variable + unit suffix (unknown variables keep their name;
# their units are kept in bronze `daily_units`).
UNIT_SUFFIX = {
    "temperature_2m_max": "_c", "temperature_2m_min": "_c", "temperature_2m_mean": "_c",
    "apparent_temperature_max": "_c", "apparent_temperature_min": "_c", "apparent_temperature_mean": "_c",
    "precipitation_sum": "_mm", "rain_sum": "_mm", "showers_sum": "_mm", "snowfall_sum": "_cm",
    "precipitation_hours": "_h", "sunshine_duration": "_s", "daylight_duration": "_s",
    "wind_speed_10m_max": "_kmh", "wind_gusts_10m_max": "_kmh", "wind_direction_10m_dominant": "_deg",
    "shortwave_radiation_sum": "_mj_m2", "et0_fao_evapotranspiration": "_mm",
    "relative_humidity_2m_mean": "_pct", "cloud_cover_mean": "_pct", "pressure_msl_mean": "_hpa",
}
INT_VARS = {"weather_code"}
TIMESTAMP_VARS = {"sunrise", "sunset"}

def sql_type(v):
    return "INT" if v in INT_VARS else "TIMESTAMP" if v in TIMESTAMP_VARS else "DOUBLE"

VARS = {v: v + UNIT_SUFFIX.get(v, "") for v in DAILY_VARS}
print(f"Landing {LANDING}\nBronze  {BRONZE}\nSilver  {SILVER}\nColumns {list(VARS.values())}")

# COMMAND ----------

# DBTITLE 1,Bronze: Auto Loader ingest
schema_hints = (
    "grid_latitude DOUBLE, grid_longitude DOUBLE, latitude DOUBLE, longitude DOUBLE, elevation DOUBLE, "
    "daily STRUCT<time: ARRAY<STRING>, "
    + ", ".join(f"{v}: ARRAY<{'STRING' if v in TIMESTAMP_VARS else 'DOUBLE'}>" for v in DAILY_VARS)
    + ">"
)

bronze_q = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", f"{CKPT}/bronze_schema")
    .option("cloudFiles.inferColumnTypes", "true")
    .option("cloudFiles.schemaHints", schema_hints)
    .option("cloudFiles.schemaEvolutionMode", "addNewColumns")  # new fields stop the stream once; job retry picks them up
    .load(LANDING)
    .withColumn("_source_file", F.col("_metadata.file_path"))
    .withColumn("_ingested_at", F.current_timestamp())
    .writeStream
    .option("checkpointLocation", f"{CKPT}/bronze")
    .option("mergeSchema", "true")
    .trigger(availableNow=True)
    .toTable(BRONZE.replace("`", ""))
)
bronze_q.awaitTermination()
print("Bronze rows in last batch:", bronze_q.lastProgress and bronze_q.lastProgress.get("numInputRows"))

# COMMAND ----------

# DBTITLE 1,Silver table DDL
var_cols = ",\n  ".join(f"{dst} {sql_type(src)}" for src, dst in VARS.items())
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {SILVER} (
  grid_latitude DOUBLE COMMENT 'Requested grid latitude',
  grid_longitude DOUBLE COMMENT 'Requested grid longitude',
  weather_date DATE COMMENT 'Day (in the landing timezone)',
  model_latitude DOUBLE COMMENT 'Latitude of the model cell Open-Meteo used',
  model_longitude DOUBLE COMMENT 'Longitude of the model cell Open-Meteo used',
  elevation_m DOUBLE,
  {var_cols},
  run_id STRING COMMENT 'Landing run that produced this version',
  _source_file STRING,
  _ingested_at TIMESTAMP,
  _updated_at TIMESTAMP
)
CLUSTER BY (weather_date)
COMMENT 'Open-Meteo daily weather per grid point. One row per grid point per day; latest run wins.'
""")

# COMMAND ----------

# DBTITLE 1,Silver: incremental MERGE
def flatten(df):
    """One row per grid point per day, deduped to the latest run within the micro-batch."""
    x = df.select("*", F.posexplode("daily.time").alias("pos", "day"))
    cols = [
        F.col("grid_latitude"), F.col("grid_longitude"), F.to_date("day").alias("weather_date"),
        F.col("latitude").alias("model_latitude"), F.col("longitude").alias("model_longitude"),
        F.col("elevation").alias("elevation_m"),
    ] + [
        F.col(f"daily.{src}")[F.col("pos")].cast(sql_type(src).lower()).alias(dst)
        for src, dst in VARS.items()
    ] + [F.col("run_id"), F.col("_source_file"), F.col("_ingested_at")]
    win = Window.partitionBy("grid_latitude", "grid_longitude", "weather_date").orderBy(
        F.col("run_id").desc(), F.col("_ingested_at").desc())
    return (x.select(*cols)
            .withColumn("_rn", F.row_number().over(win)).filter("_rn = 1").drop("_rn")
            .withColumn("_updated_at", F.current_timestamp()))

def upsert_to_silver(batch_df, batch_id):
    flatten(batch_df).createOrReplaceTempView("silver_updates")
    # WITH SCHEMA EVOLUTION adds columns when daily_variables is extended later
    batch_df.sparkSession.sql(f"""
        MERGE WITH SCHEMA EVOLUTION INTO {SILVER} t
        USING silver_updates s
          ON  t.grid_latitude = s.grid_latitude
          AND t.grid_longitude = s.grid_longitude
          AND t.weather_date = s.weather_date
        WHEN MATCHED AND s.run_id >= t.run_id THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

silver_q = (
    spark.readStream.table(BRONZE.replace("`", ""))
    .writeStream
    .foreachBatch(upsert_to_silver)
    .option("checkpointLocation", f"{CKPT}/silver")
    .trigger(availableNow=True)
    .start()
)
silver_q.awaitTermination()

# COMMAND ----------

# DBTITLE 1,Data quality checks
first_col = next(iter(VARS.values()))
errors = []

display(spark.sql(f"""
  SELECT weather_date, count(*) AS points, count_if({first_col} IS NULL) AS null_{first_col}
  FROM {SILVER} GROUP BY weather_date ORDER BY weather_date DESC LIMIT 7
"""))

dupes = spark.sql(f"""
  SELECT count(*) AS n FROM (
    SELECT grid_latitude, grid_longitude, weather_date FROM {SILVER}
    GROUP BY ALL HAVING count(*) > 1)
""").first()["n"]
if dupes:
    errors.append(f"{dupes} duplicate keys in {SILVER}")

# In a job: every day landed by this run must cover the full grid
run_id = dbutils.jobs.taskValues.get(taskKey=w("landing_task_key"), key="run_id", default="", debugValue="")
grid_points = dbutils.jobs.taskValues.get(taskKey=w("landing_task_key"), key="grid_points", default=0, debugValue=0)
if run_id and grid_points:
    short = spark.sql(f"""
      SELECT weather_date, count(*) AS points FROM {SILVER}
      WHERE run_id = '{run_id}' GROUP BY weather_date HAVING count(*) <> {int(grid_points)}
    """).collect()
    if short:
        errors.append(f"Run {run_id}: dates without {grid_points} points: {[(r.weather_date, r.points) for r in short]}")
    else:
        print(f"Run {run_id}: all dates have {grid_points} points")

if errors:
    msg = "; ".join(errors)
    if FAIL_ON_DQ:
        raise AssertionError(msg)
    print("DQ WARNING:", msg)
else:
    print("DQ checks passed")