-- Cleaned and deduplicated GDACS extreme events.
CREATE OR REFRESH MATERIALIZED VIEW ${silver_schema}.extreme_events (
  CONSTRAINT valid_event_id EXPECT (event_id IS NOT NULL),
  CONSTRAINT valid_event_type EXPECT (event_type IS NOT NULL)
)
COMMENT 'GDACS extreme events: floods, cyclones, droughts, earthquakes, wildfires, volcanoes'
AS
SELECT DISTINCT
  properties.eventid AS event_id,
  properties.eventtype AS event_type,
  properties.alertlevel AS alert_level,
  CAST(properties.alertscore AS INT) AS alert_score,
  properties.name AS event_name,
  properties.country AS country,
  properties.iso3 AS iso3,
  CAST(properties.fromdate AS TIMESTAMP) AS from_date,
  CAST(properties.todate AS TIMESTAMP) AS to_date,
  properties.severitydata.severity AS severity_value,
  properties.severitydata.severitytext AS severity_text,
  properties.severitydata.severityunit AS severity_unit,
  geometry.coordinates[1] AS lat,
  geometry.coordinates[0] AS lon,
  data_source,
  request_mode,
  run_date
FROM ${bronze_schema}.gdacs_events_raw
WHERE type = 'Feature'
  AND properties.eventid IS NOT NULL;
