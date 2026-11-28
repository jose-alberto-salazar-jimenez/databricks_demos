-- Location dimension: land grid cells from the ingestion reference data.
-- Each cell_id is a deterministic id from rounded lat/lon and grid size. v2 excludes lake cells;
-- path kept in sync with source_registry.GRID_DIR.
CREATE OR REFRESH MATERIALIZED VIEW ${silver_schema}.dim_location
COMMENT 'Land grid cells (lakes excluded): 20 km for PE/CO/EC, 10 km for CR/PA'
AS
SELECT
  cell_id,
  iso3,
  grid_km,
  grid_step_deg,
  lat,
  lon
FROM read_files(
  '${landing_path}/reference/grid_cells_v2',
  format => 'json'
);
