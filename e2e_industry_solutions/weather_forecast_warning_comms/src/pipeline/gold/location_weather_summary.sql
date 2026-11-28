-- Per-cell weather summary with today, past, and future outlook plus ENSO.
CREATE OR REFRESH MATERIALIZED VIEW ${gold_schema}.location_weather_summary
COMMENT 'Per-cell summary: today + past avg + future outlook + ENSO context'
AS
WITH latest AS (
  SELECT MAX(run_date) AS run_date FROM ${silver_schema}.weather_forecast_daily
),
daily AS (
  SELECT
    w.cell_id, w.run_date, w.forecast_date,
    w.temperature_2m_max, w.temperature_2m_min, w.precipitation_sum,
    w.precipitation_probability_max, w.wind_speed_10m_max,
    w.wind_gusts_10m_max, w.weather_code, w.uv_index_max,
    CASE
      WHEN w.forecast_date < w.run_date THEN 'past'
      WHEN w.forecast_date = w.run_date THEN 'today'
      ELSE 'future'
    END AS period
  FROM ${silver_schema}.weather_forecast_daily w
  INNER JOIN latest l ON w.run_date = l.run_date
),
enso AS (
  SELECT anomaly, enso_phase
  FROM ${silver_schema}.enso_phase_monthly
  ORDER BY year DESC,
    ARRAY_POSITION(
      ARRAY('DJF','JFM','FMA','MAM','AMJ','MJJ','JJA','JAS','ASO','SON','OND','NDJ'),
      season
    ) DESC
  LIMIT 1
)
SELECT
  d.cell_id,
  loc.iso3 AS country,
  loc.lat, loc.lon, loc.grid_km,
  d.run_date,
  MAX(CASE WHEN period = 'today' THEN temperature_2m_max END) AS today_temp_max,
  MAX(CASE WHEN period = 'today' THEN temperature_2m_min END) AS today_temp_min,
  MAX(CASE WHEN period = 'today' THEN precipitation_sum END) AS today_precip_sum,
  MAX(CASE WHEN period = 'today' THEN wind_speed_10m_max END) AS today_wind_max,
  MAX(CASE WHEN period = 'today' THEN weather_code END) AS today_weather_code,
  ROUND(AVG(CASE WHEN period = 'past' THEN temperature_2m_max END), 1) AS past_avg_temp_max,
  ROUND(AVG(CASE WHEN period = 'past' THEN precipitation_sum END), 1) AS past_avg_precip,
  ROUND(MAX(CASE WHEN period = 'past' THEN precipitation_sum END), 1) AS past_max_precip,
  ROUND(AVG(CASE WHEN period = 'future' THEN temperature_2m_max END), 1) AS future_avg_temp_max,
  ROUND(AVG(CASE WHEN period = 'future' THEN precipitation_sum END), 1) AS future_avg_precip,
  ROUND(MAX(CASE WHEN period = 'future' THEN precipitation_sum END), 1) AS future_max_precip,
  ROUND(MAX(CASE WHEN period = 'future' THEN wind_speed_10m_max END), 1) AS future_max_wind,
  MAX(CASE WHEN period = 'future' THEN precipitation_probability_max END) AS future_max_precip_prob,
  MAX(e.enso_phase) AS enso_phase,
  MAX(e.anomaly) AS enso_anomaly
FROM daily d
INNER JOIN ${silver_schema}.dim_location loc ON d.cell_id = loc.cell_id
CROSS JOIN enso e
GROUP BY ALL;
