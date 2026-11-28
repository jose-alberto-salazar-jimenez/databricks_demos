-- Main towns (GeoNames populated places, CC-BY 4.0): population >= 100,000 plus the 5 largest per
-- country, so small countries are covered. Each town maps to its nearest land grid cell; used for
-- advisories and the app's town picker.
CREATE OR REFRESH MATERIALIZED VIEW ${silver_schema}.dim_town (
  CONSTRAINT mapped_to_cell EXPECT (cell_id IS NOT NULL)
)
COMMENT 'Main towns (GeoNames) mapped to the nearest land grid cell'
AS
WITH places AS (
  SELECT geonameid, name, lat, lon, cc, pop,
         row_number() OVER (PARTITION BY cc ORDER BY pop DESC) AS pop_rank
  FROM read_files('${landing_path}/geonames/*.txt', format => 'csv', sep => '\t', header => false,
    quote => '', schema => 'geonameid BIGINT, name STRING, asciiname STRING, alternatenames STRING,
      lat DOUBLE, lon DOUBLE, fclass STRING, fcode STRING, cc STRING, cc2 STRING, a1 STRING, a2 STRING,
      a3 STRING, a4 STRING, pop BIGINT, elevation STRING, dem STRING, tz STRING, moddate STRING')
  WHERE fclass = 'P'
),
towns AS (
  SELECT p.*, c.iso3, c.country_name
  FROM places p
  JOIN (VALUES ('PE', 'PER', 'Peru'), ('EC', 'ECU', 'Ecuador'), ('CO', 'COL', 'Colombia'),
               ('PA', 'PAN', 'Panama'), ('CR', 'CRI', 'Costa Rica')) AS c(cc, iso3, country_name)
    ON p.cc = c.cc
  WHERE p.pop >= 100000 OR p.pop_rank <= 5
),
near AS (
  SELECT t.*, g.cell_id,
         sqrt(pow(g.lat - t.lat, 2) + pow(g.lon - t.lon, 2)) * 111 AS km_to_cell,
         row_number() OVER (PARTITION BY t.geonameid
                            ORDER BY pow(g.lat - t.lat, 2) + pow(g.lon - t.lon, 2)) AS rk
  FROM towns t
  LEFT JOIN ${silver_schema}.dim_location g
    ON g.iso3 = t.iso3 AND abs(g.lat - t.lat) <= 0.5 AND abs(g.lon - t.lon) <= 0.5
)
SELECT geonameid AS town_id, name AS town, iso3 AS country, country_name, lat, lon,
       pop AS population, pop_rank, cell_id, round(km_to_cell, 1) AS km_to_cell
FROM near
WHERE rk = 1;
