"""Single place that describes every data source, plus shared grid / variable constants.

Each landed JSONL row carries `data_source` (a key of SOURCES), `source_model` and `request_mode`
(daily | backfill_recent | backfill_history). `land_sources_manifest` writes SOURCES to
reference/data_sources/ so the pipeline can build a `dim_data_source` table and keep the source
visible in silver and gold (e.g. observed history from ERA5 vs forecast-API past days)."""

GRID_STEP = {"PER": 0.18, "ECU": 0.18, "COL": 0.18, "PAN": 0.09, "CRI": 0.09}  # ~20 km / ~10 km
ISO2 = {"PER": "PE", "ECU": "EC", "COL": "CO", "PAN": "PA", "CRI": "CR"}
NAMES = {"PER": "Peru", "ECU": "Ecuador", "COL": "Colombia", "PAN": "Panama", "CRI": "Costa Rica"}

# Forecast API: keep <= 10 variables so one location stays one call.
DAILY_VARS = ["weather_code", "temperature_2m_max", "temperature_2m_min", "apparent_temperature_max",
              "precipitation_sum", "precipitation_probability_max", "wind_speed_10m_max",
              "wind_gusts_10m_max", "uv_index_max", "et0_fao_evapotranspiration"]
# ERA5 archive: uv_index_max and precipitation_probability_max come back empty, so they are dropped.
ERA5_DAILY_VARS = [v for v in DAILY_VARS if v not in ("uv_index_max", "precipitation_probability_max")]

SOURCES = {
    "open_meteo_forecast": {
        "provider": "Open-Meteo", "product": "Forecast API (best_match models)",
        "url": "https://api.open-meteo.com/v1/forecast", "license": "CC-BY 4.0 (free tier, non-commercial)",
        "resolution": "model native, 1-11 km; snapped to grid cell", "kind": "forecast + recent past days",
        "landing_dirs": ["open_meteo_forecast", "open_meteo_forecast_backfill"]},
    "open_meteo_era5": {
        "provider": "Open-Meteo / ECMWF Copernicus", "product": "Historical Weather API, ERA5 reanalysis",
        "url": "https://archive-api.open-meteo.com/v1/archive", "license": "CC-BY 4.0 (free tier, non-commercial)",
        "resolution": "0.25 deg (~28 km)", "kind": "observed-like history, ~7-day lag",
        "landing_dirs": ["open_meteo_era5"]},
    "noaa_cpc_oni": {
        "provider": "NOAA Climate Prediction Center", "product": "Oceanic Nino Index (ONI)",
        "url": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt", "license": "US public domain",
        "resolution": "Nino 3.4 region, 3-month seasons", "kind": "climate index", "landing_dirs": ["enso_oni"]},
    "gdacs": {
        "provider": "GDACS (UN / European Commission JRC)", "product": "Event list API",
        "url": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
        "license": "GDACS terms of use, attribution", "resolution": "event point / area",
        "kind": "extreme events (FL, TC, DR, EQ, WF, VO)", "landing_dirs": ["gdacs"]},
    "geonames": {
        "provider": "GeoNames", "product": "Country dumps (populated places)",
        "url": "https://download.geonames.org/export/dump/{iso2}.zip", "license": "CC-BY 4.0",
        "resolution": "point", "kind": "towns and cities", "landing_dirs": ["geonames"]},
    "natural_earth": {
        "provider": "Natural Earth", "product": "Admin-0 countries 1:10m",
        "url": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
               "ne_10m_admin_0_countries.geojson",
        "license": "Public domain", "resolution": "1:10m", "kind": "boundaries, land mask",
        "landing_dirs": ["reference/natural_earth", "reference/grid_cells"]},
}

REQUEST_MODES = ("daily", "backfill_recent", "backfill_history")


def url(source_id, **kw):
    return SOURCES[source_id]["url"].format(**kw)


def tags(source_id, request_mode, source_model=None):
    """Columns added to every landed record so lineage survives into bronze, silver and gold."""
    assert source_id in SOURCES and request_mode in REQUEST_MODES, (source_id, request_mode)
    return {"data_source": source_id, "source_url": SOURCES[source_id]["url"],
            "source_model": source_model, "request_mode": request_mode}
