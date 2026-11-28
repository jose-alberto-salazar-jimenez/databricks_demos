-- Daily weather values: one row per cell, run_date, forecast_date.
-- Explodes nested arrays from bronze.open_meteo_forecast_raw. Re-runs of the same run_date with
-- other batch splits (e.g. a test subset, then the full grid) land the same cell twice; keep
-- the latest ingest per cell, run_date and request_mode.
CREATE OR REFRESH MATERIALIZED VIEW ${silver_schema}.weather_forecast_daily (
  CONSTRAINT valid_cell EXPECT (cell_id IS NOT NULL),
  CONSTRAINT valid_date EXPECT (forecast_date IS NOT NULL),
  CONSTRAINT plausible_temp EXPECT (temperature_2m_max BETWEEN -50 AND 60)
)
COMMENT 'Exploded daily weather: one row per cell x run_date x forecast_date'
AS
SELECT
  cell_id,
  CAST(run_date AS DATE) AS run_date,
  data_source,
  request_mode,
  source_model,
  latitude,
  longitude,
  elevation,
  CAST(d.forecast_date AS DATE) AS forecast_date,
  daily.temperature_2m_max[d.pos] AS temperature_2m_max,
  daily.temperature_2m_min[d.pos] AS temperature_2m_min,
  daily.apparent_temperature_max[d.pos] AS apparent_temperature_max,
  daily.precipitation_sum[d.pos] AS precipitation_sum,
  daily.precipitation_probability_max[d.pos] AS precipitation_probability_max,
  daily.wind_speed_10m_max[d.pos] AS wind_speed_10m_max,
  daily.wind_gusts_10m_max[d.pos] AS wind_gusts_10m_max,
  daily.weather_code[d.pos] AS weather_code,
  daily.uv_index_max[d.pos] AS uv_index_max,
  daily.et0_fao_evapotranspiration[d.pos] AS et0_fao_evapotranspiration
FROM (
  SELECT * FROM ${bronze_schema}.open_meteo_forecast_raw
  QUALIFY row_number() OVER (PARTITION BY cell_id, run_date, request_mode
                             ORDER BY ingested_at DESC) = 1
) r
LATERAL VIEW posexplode(r.daily.time) d AS pos, forecast_date;
