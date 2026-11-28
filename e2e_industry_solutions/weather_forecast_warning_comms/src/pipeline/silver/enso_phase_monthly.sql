-- NOAA CPC Oceanic Nino Index parsed into structured monthly records.
CREATE OR REFRESH MATERIALIZED VIEW ${silver_schema}.enso_phase_monthly (
  CONSTRAINT valid_year EXPECT (year BETWEEN 1950 AND 2030),
  CONSTRAINT valid_anomaly EXPECT (anomaly BETWEEN -4 AND 4)
)
COMMENT 'ENSO Oceanic Nino Index: season, year, SST anomaly, phase'
AS
WITH parsed AS (
  SELECT
    trim(split(trim(value), ' +')[0]) AS season,
    CAST(trim(split(trim(value), ' +')[1]) AS INT) AS year,
    CAST(trim(split(trim(value), ' +')[2]) AS DOUBLE) AS total_sst,
    CAST(trim(split(trim(value), ' +')[3]) AS DOUBLE) AS anomaly
  FROM ${bronze_schema}.enso_oni_raw
  WHERE trim(value) NOT LIKE '%SEAS%'
    AND length(trim(value)) > 0
)
SELECT
  season,
  year,
  total_sst,
  anomaly,
  CASE
    WHEN anomaly >= 0.5 THEN 'El Nino'
    WHEN anomaly <= -0.5 THEN 'La Nina'
    ELSE 'Neutral'
  END AS enso_phase
FROM parsed
WHERE year IS NOT NULL AND season IS NOT NULL;
