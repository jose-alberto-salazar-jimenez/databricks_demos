-- Bronze: raw landing files as streaming tables (Auto Loader), one per source. One file for all
-- three keeps the repo within the 30-file limit; table and flow names are unchanged.

-- Raw Open-Meteo forecast: daily runs land in open_meteo_forecast/.
-- Nested daily arrays are exploded in silver.weather_forecast_daily.
CREATE OR REFRESH STREAMING TABLE ${bronze_schema}.open_meteo_forecast_raw (
  CONSTRAINT valid_cell_id EXPECT (cell_id IS NOT NULL),
  -- pilot-region extent incl. Galapagos (-91.6) and San Andres (12.2N), with margin
  CONSTRAINT valid_coords EXPECT (latitude BETWEEN -19 AND 13 AND longitude BETWEEN -92.5 AND -66),
  CONSTRAINT valid_run_date EXPECT (run_date IS NOT NULL)
)
COMMENT 'Raw Open-Meteo forecast API responses (daily + backfill_recent)';

CREATE FLOW forecast_daily
AS INSERT INTO ${bronze_schema}.open_meteo_forecast_raw BY NAME
SELECT * FROM STREAM(read_files(
  '${landing_path}/open_meteo_forecast',
  format => 'json'
));

-- NOAA CPC Oceanic Nino Index: raw text file, one line per record.
-- Parsed into structured columns in silver.enso_phase_monthly.
CREATE OR REFRESH STREAMING TABLE ${bronze_schema}.enso_oni_raw (
  CONSTRAINT non_empty EXPECT (value IS NOT NULL AND length(trim(value)) > 0)
)
COMMENT 'Raw NOAA CPC ONI text lines';

CREATE FLOW enso_daily
AS INSERT INTO ${bronze_schema}.enso_oni_raw BY NAME
SELECT * FROM STREAM(read_files(
  '${landing_path}/enso_oni',
  format => 'text'
));

-- GDACS extreme-event alerts (GeoJSON features). Deduplicated and
-- flattened in silver.extreme_events.
CREATE OR REFRESH STREAMING TABLE ${bronze_schema}.gdacs_events_raw (
  CONSTRAINT valid_type EXPECT (type IS NOT NULL)
)
COMMENT 'Raw GDACS event GeoJSON features and no_events markers';

CREATE FLOW gdacs_daily
AS INSERT INTO ${bronze_schema}.gdacs_events_raw BY NAME
SELECT * FROM STREAM(read_files(
  '${landing_path}/gdacs',
  format => 'json'
));
