"""Helpers for src/ingestion/ingest_sources: HTTP retries, free-tier rate limiting, landing writers
and one function per source. Every function writes raw files under `root` (the landing volume)."""
import datetime as dt
import io
import json
import os
import time
import zipfile

import requests

GRID_STEP = {"PER": 0.18, "ECU": 0.18, "COL": 0.18, "PAN": 0.09, "CRI": 0.09}  # ~20 km / ~10 km
ISO2 = {"PER": "PE", "ECU": "EC", "COL": "CO", "PAN": "PA", "CRI": "CR"}
NAMES = {"PER": "Peru", "ECU": "Ecuador", "COL": "Colombia", "PAN": "Panama", "CRI": "Costa Rica"}
DAILY_VARS = ["weather_code", "temperature_2m_max", "temperature_2m_min", "apparent_temperature_max",
              "precipitation_sum", "precipitation_probability_max", "wind_speed_10m_max",
              "wind_gusts_10m_max", "uv_index_max", "et0_fao_evapotranspiration"]  # keep <= 10

NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
          "ne_10m_admin_0_countries.geojson")
GEONAMES_URL = "https://download.geonames.org/export/dump/{iso2}.zip"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def http_get(url, params=None, tries=5, timeout=120):
    """GET with exponential backoff on 429/5xx and network errors."""
    for i in range(tries):
        status = None
        try:
            r = requests.get(url, params=params, timeout=timeout)
            status = r.status_code
            if status in (200, 204):
                return r
            if status not in (429, 500, 502, 503, 504):
                r.raise_for_status()
            print(f"retry {i + 1}: HTTP {status}")
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"retry {i + 1}: {e}")
        if i < tries - 1:
            time.sleep(min(60 * 2 ** i, 600) if status == 429 else 5 * 2 ** i)
    raise RuntimeError(f"failed after {tries} tries: {url}")


class RateLimiter:
    """Sliding-window limits in weighted API calls, kept under the Open-Meteo free tier."""

    def __init__(self, per_min=550, per_hour=4800):
        self.limits, self.log = [(60, per_min), (3600, per_hour)], []

    def acquire(self, n):
        while True:
            now = time.time()
            self.log = [(t, k) for t, k in self.log if now - t < 3600]
            waits = []
            for win, cap in self.limits:
                in_win = [(t, k) for t, k in self.log if now - t < win]
                if in_win and sum(k for _, k in in_win) + n > cap:
                    waits.append(win - (now - min(t for t, _ in in_win)))
            if not waits:
                self.log.append((now, n))
                return
            time.sleep(max(waits) + 1)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_jsonl(path, records):
    write_text(path, "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")


def calls_per_point(days, n_vars=len(DAILY_VARS)):
    """Open-Meteo weighting: >14 days or >10 variables per location count as fractional extra calls."""
    return max(1, days / 14) * max(1, n_vars / 10)


def land_reference(spark, root):
    """Boundaries, GeoNames dumps and the land grid; each is created only if missing."""
    ne_path, grid_dir = f"{root}/reference/natural_earth/ne_10m_admin_0_countries.geojson", f"{root}/reference/grid_cells"
    if not os.path.exists(ne_path):
        write_text(ne_path, http_get(NE_URL).text)
    for iso2 in ISO2.values():
        path = f"{root}/geonames/{iso2}.txt"
        if not os.path.exists(path):
            z = zipfile.ZipFile(io.BytesIO(http_get(GEONAMES_URL.format(iso2=iso2)).content))
            write_text(path, z.read(f"{iso2}.txt").decode("utf-8"))
    if not os.path.exists(grid_dir):
        with open(ne_path, encoding="utf-8") as f:
            ne = json.load(f)
        rows = [(p["ADM0_A3"], GRID_STEP[p["ADM0_A3"]], json.dumps(feat["geometry"]))
                for feat in ne["features"] if (p := feat["properties"]).get("ADM0_A3") in GRID_STEP]
        spark.createDataFrame(rows, "iso3 string, step double, geojson string").createOrReplaceTempView("countries")
        # Global lattice (multiples of step) keeps cell ids stable across runs; land points only.
        spark.sql("""
          WITH b AS (SELECT iso3, step, st_geomfromgeojson(geojson) g FROM countries),
          e AS (SELECT *, cast(floor(st_xmin(g) / step) AS int) i0, cast(ceil(st_xmax(g) / step) AS int) i1,
                          cast(floor(st_ymin(g) / step) AS int) j0, cast(ceil(st_ymax(g) / step) AS int) j1 FROM b),
          p AS (SELECT iso3, step, g, round(i * step, 4) lon, round(j * step, 4) lat FROM e
                LATERAL VIEW explode(sequence(i0, i1)) AS i LATERAL VIEW explode(sequence(j0, j1)) AS j)
          SELECT concat(iso3, '_', cast(round(step * 111) AS int), 'km_',
                        format_string('%.2f_%.2f', lat, lon)) AS cell_id,
                 iso3, cast(round(step * 111) AS int) AS grid_km, step AS grid_step_deg, lat, lon
          FROM p WHERE st_contains(g, st_point(lon, lat, 4326))""").write.mode("overwrite").json(grid_dir)
    return grid_dir


def land_enso(root, run_date):
    oni = http_get(ONI_URL).text
    write_text(f"{root}/enso_oni/run_date={run_date}/oni.ascii.txt", oni)
    return len(oni.splitlines())


def land_gdacs(root, run_date, countries, ingested_at, lookback_days=30):
    """One file per country; a marker row when there are no events so every run is auditable."""
    start, n = (dt.date.fromisoformat(run_date) - dt.timedelta(days=lookback_days)).isoformat(), 0
    for iso3 in countries:
        r = http_get(GDACS_URL, params={"eventlist": "FL;TC;DR;EQ;WF;VO", "alertlevel": "Green;Orange;Red",
                                        "country": NAMES[iso3], "fromdate": start, "todate": run_date})
        feats = r.json().get("features", []) if r.status_code == 200 else []  # 204 = no events
        meta = {"query_iso3": iso3, "run_date": run_date, "ingested_at": ingested_at}
        write_jsonl(f"{root}/gdacs/run_date={run_date}/{iso3}.jsonl",
                    [{**meta, **f} for f in feats] or [{**meta, "type": "no_events"}])
        n += len(feats)
    return n


def land_forecast(root, run_date, points, past_days, forecast_days, ingested_at, budget, batch=100):
    """Rate-limited, resumable Open-Meteo download; `points` are rows with cell_id, lat, lon."""
    cpp = calls_per_point(past_days + forecast_days)
    if len(points) * cpp > budget:
        raise ValueError(f"{len(points)} points x {cpp:.2f} calls = {len(points) * cpp:.0f} > budget "
                         f"{budget:.0f}; reduce days, points or countries")
    out_dir, limiter, calls, skipped = f"{root}/open_meteo_forecast/run_date={run_date}", RateLimiter(), 0, 0
    for b in range(0, len(points), batch):
        chunk, path = points[b:b + batch], f"{out_dir}/batch_{b // batch:04d}.jsonl"
        if os.path.exists(path):
            skipped += 1
            continue
        limiter.acquire(len(chunk) * cpp)
        body = http_get(OPEN_METEO_URL, params={
            "latitude": ",".join(str(p.lat) for p in chunk), "longitude": ",".join(str(p.lon) for p in chunk),
            "daily": ",".join(DAILY_VARS), "past_days": past_days, "forecast_days": forecast_days,
            "timezone": "auto"}).json()
        body = body if isinstance(body, list) else [body]
        assert len(body) == len(chunk), f"expected {len(chunk)} locations, got {len(body)}"
        write_jsonl(path, [{"cell_id": p.cell_id, "req_lat": p.lat, "req_lon": p.lon, "run_date": run_date,
                            "ingested_at": ingested_at, **loc} for p, loc in zip(chunk, body)])
        calls += len(chunk) * cpp
    return {"forecast_points": len(points), "forecast_api_calls": round(calls, 1),
            "forecast_batches_skipped": skipped, "past_days": past_days, "forecast_days": forecast_days}
