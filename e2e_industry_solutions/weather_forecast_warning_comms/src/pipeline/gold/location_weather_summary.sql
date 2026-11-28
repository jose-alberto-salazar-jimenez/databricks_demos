-- Per-cell weather summary with today, past, and future outlook plus ENSO, and rule-based risk
-- flags over the next 3 days (today + 2), the PoC stand-in for the deferred ML model. Thresholds:
-- rain >= 50 mm/day; apparent max >= 41 C ("danger" band of the NWS heat index, a similar index;
-- 35 C flagged most tropical lowland cells); gusts >= 60 km/h.
CREATE OR REFRESH MATERIALIZED VIEW ${gold_schema}.location_weather_summary
COMMENT 'Per-cell summary: today + past avg + future outlook + 3-day risk flags + ENSO context'
AS
WITH latest AS (
  SELECT MAX(run_date) AS run_date FROM ${silver_schema}.weather_forecast_daily
),
daily AS (
  SELECT
    w.cell_id, w.run_date, w.forecast_date,
    w.temperature_2m_max, w.temperature_2m_min, w.precipitation_sum,
    w.precipitation_probability_max, w.wind_speed_10m_max,
    w.wind_gusts_10m_max, w.weather_code, w.uv_index_max, w.apparent_temperature_max,
    w.forecast_date BETWEEN w.run_date AND date_add(w.run_date, 2) AS next3,
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
),
agg AS (
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
  ROUND(MAX(CASE WHEN next3 THEN precipitation_sum END), 1) AS rain_3d_max_mm,
  ROUND(MAX(CASE WHEN next3 THEN apparent_temperature_max END), 1) AS heat_3d_max_c,
  ROUND(MAX(CASE WHEN next3 THEN wind_gusts_10m_max END), 1) AS gust_3d_max_kmh,
  MAX(e.enso_phase) AS enso_phase,
  MAX(e.anomaly) AS enso_anomaly
FROM daily d
INNER JOIN ${silver_schema}.dim_location loc ON d.cell_id = loc.cell_id
CROSS JOIN enso e
GROUP BY ALL
)
SELECT *,
  coalesce(rain_3d_max_mm >= 50, false) AS flag_heavy_rain,
  coalesce(heat_3d_max_c >= 41, false) AS flag_extreme_heat,
  coalesce(gust_3d_max_kmh >= 60, false) AS flag_strong_wind,
  coalesce(nullif(concat_ws(', ',
    CASE WHEN rain_3d_max_mm >= 50 THEN 'heavy rain' END,
    CASE WHEN heat_3d_max_c >= 41 THEN 'extreme heat' END,
    CASE WHEN gust_3d_max_kmh >= 60 THEN 'strong wind' END), ''), 'none') AS warnings
FROM agg;
