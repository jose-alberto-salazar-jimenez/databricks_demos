"""Reference and context sources: data-source manifest, boundaries, land grid, GeoNames towns,
NOAA ENSO index and GDACS events. Weather downloads live in ingest_lib.py."""
import datetime as dt
import io
import json
import os
import zipfile

import source_registry as reg
from ingest_lib import http_get, write_jsonl, write_text


def land_reference(spark, root):
    """Source manifest (every run) plus boundaries, GeoNames dumps and the land grid (if missing)."""
    ne_path, grid_dir = f"{root}/reference/natural_earth/ne_10m_admin_0_countries.geojson", f"{root}/reference/grid_cells"
    write_jsonl(f"{root}/reference/data_sources/sources.jsonl",  # manifest -> dim_data_source
                [{"data_source": k, **v} for k, v in reg.SOURCES.items()])
    if not os.path.exists(ne_path):
        write_text(ne_path, http_get(reg.url("natural_earth")).text)
    for iso2 in reg.ISO2.values():
        path = f"{root}/geonames/{iso2}.txt"
        if not os.path.exists(path):
            z = zipfile.ZipFile(io.BytesIO(http_get(reg.url("geonames", iso2=iso2)).content))
            write_text(path, z.read(f"{iso2}.txt").decode("utf-8"))
    if not os.path.exists(grid_dir):
        with open(ne_path, encoding="utf-8") as f:
            ne = json.load(f)
        rows = [(p["ADM0_A3"], reg.GRID_STEP[p["ADM0_A3"]], json.dumps(feat["geometry"]))
                for feat in ne["features"] if (p := feat["properties"]).get("ADM0_A3") in reg.GRID_STEP]
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
