"""Reference and context sources: data-source manifest, boundaries, land grid, GeoNames towns,
NOAA ENSO index and GDACS events. Weather downloads live in ingest_lib.py."""
import datetime as dt
import io
import json
import os
import zipfile

import source_registry as reg
from ingest_lib import http_get, write_jsonl, write_text


def _bbox(geom):
    """(xmin, xmax, ymin, ymax) of a GeoJSON geometry."""
    pts = []

    def walk(c):
        if isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


def land_reference(spark, root):
    """Source manifest (every run) plus boundaries, lakes, GeoNames dumps and the land grid (if missing).
    Grid = lattice points inside a country and outside Natural Earth 10m lakes: forecast models return
    lake-surface values there (Titicaca highs near -10 C) and nobody lives on the water."""
    ne_dir, grid_dir = f"{root}/reference/natural_earth", f"{root}/{reg.GRID_DIR}"
    ne_path, lakes_path = f"{ne_dir}/ne_10m_admin_0_countries.geojson", f"{ne_dir}/ne_10m_lakes.geojson"
    write_jsonl(f"{root}/reference/data_sources/sources.jsonl",  # manifest -> dim_data_source
                [{"data_source": k, **v} for k, v in reg.SOURCES.items()])
    for path, src in ((ne_path, "natural_earth"), (lakes_path, "natural_earth_lakes")):
        if not os.path.exists(path):
            write_text(path, http_get(reg.url(src)).text)
    for iso2 in reg.ISO2.values():
        path = f"{root}/geonames/{iso2}.txt"
        if not os.path.exists(path):
            z = zipfile.ZipFile(io.BytesIO(http_get(reg.url("geonames", iso2=iso2)).content))
            write_text(path, z.read(f"{iso2}.txt").decode("utf-8"))
    if not os.path.exists(grid_dir):
        with open(ne_path, encoding="utf-8") as f:
            ne = json.load(f)
        with open(lakes_path, encoding="utf-8") as f:
            lakes = json.load(f)
        sel = [feat for feat in ne["features"] if feat["properties"].get("ADM0_A3") in reg.GRID_STEP]
        rows = [(f["properties"]["ADM0_A3"], reg.GRID_STEP[f["properties"]["ADM0_A3"]], json.dumps(f["geometry"]))
                for f in sel]
        boxes = [_bbox(f["geometry"]) for f in sel]  # keep only lakes that overlap the countries
        x0, x1 = min(b[0] for b in boxes), max(b[1] for b in boxes)
        y0, y1 = min(b[2] for b in boxes), max(b[3] for b in boxes)
        lk = [(json.dumps(f["geometry"]),) for f in lakes["features"]
              if (b := _bbox(f["geometry"]))[1] >= x0 and b[0] <= x1 and b[3] >= y0 and b[2] <= y1]
        spark.createDataFrame(rows, "iso3 string, step double, geojson string").createOrReplaceTempView("countries")
        spark.createDataFrame(lk, "geojson string").createOrReplaceTempView("lakes")
        # Global lattice (multiples of step) keeps cell ids stable across runs; land points only.
        spark.sql("""
          WITH b AS (SELECT iso3, step, st_geomfromgeojson(geojson) g FROM countries),
          e AS (SELECT *, cast(floor(st_xmin(g) / step) AS int) i0, cast(ceil(st_xmax(g) / step) AS int) i1,
                          cast(floor(st_ymin(g) / step) AS int) j0, cast(ceil(st_ymax(g) / step) AS int) j1 FROM b),
          p AS (SELECT iso3, step, g, round(i * step, 4) lon, round(j * step, 4) lat FROM e
                LATERAL VIEW explode(sequence(i0, i1)) AS i LATERAL VIEW explode(sequence(j0, j1)) AS j),
          land AS (SELECT iso3, step, lon, lat FROM p WHERE st_contains(g, st_point(lon, lat, 4326))),
          lk AS (SELECT st_geomfromgeojson(geojson) lg FROM lakes)
          SELECT concat(iso3, '_', cast(round(step * 111) AS int), 'km_',
                        format_string('%.2f_%.2f', lat, lon)) AS cell_id,
                 iso3, cast(round(step * 111) AS int) AS grid_km, step AS grid_step_deg, lat, lon
          FROM land LEFT ANTI JOIN lk ON st_contains(lk.lg, st_point(land.lon, land.lat, 4326))
          """).write.mode("overwrite").json(grid_dir)
    return grid_dir


def land_enso(root, run_date):
    oni = http_get(reg.url("noaa_cpc_oni")).text  # raw text: bronze adds data_source from the folder
    write_text(f"{root}/enso_oni/run_date={run_date}/oni.ascii.txt", oni)
    return len(oni.splitlines())


def gdacs_events(iso3, start, end, max_pages=20):
    """All GDACS events for a country and date range (the API pages 100 events at a time)."""
    feats, seen = [], set()
    for page in range(1, max_pages + 1):
        r = http_get(reg.url("gdacs"), params={"eventlist": "FL;TC;DR;EQ;WF;VO", "alertlevel": "Green;Orange;Red",
                                               "country": reg.NAMES[iso3], "fromdate": start, "todate": end,
                                               "pagenumber": page})
        new = [f for f in (r.json().get("features", []) if r.status_code == 200 else [])  # 204 = none
               if (f["properties"]["eventid"], f["properties"]["eventtype"]) not in seen]
        seen.update((f["properties"]["eventid"], f["properties"]["eventtype"]) for f in new)
        feats += new
        if len(new) < 100:
            break
    return feats


def land_gdacs(root, run_date, countries, ingested_at, lookback_days=30, start=None,
               request_mode="daily", subdir="gdacs"):
    """One file per country; a marker row when there are no events so every run is auditable."""
    start, n = start or (dt.date.fromisoformat(run_date) - dt.timedelta(days=lookback_days)).isoformat(), 0
    for iso3 in countries:
        feats = gdacs_events(iso3, start, run_date)
        meta = {"query_iso3": iso3, "query_from": start, "query_to": run_date, "run_date": run_date,
                "ingested_at": ingested_at, **reg.tags("gdacs", request_mode)}
        write_jsonl(f"{root}/{subdir}/run_date={run_date}/{iso3}.jsonl",
                    [{**meta, **f} for f in feats] or [{**meta, "type": "no_events"}])
        n += len(feats)
    return n
