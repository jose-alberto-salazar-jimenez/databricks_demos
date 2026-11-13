"""History for model training (phase 3): ERA5 reanalysis for a persisted sample of grid cells.

Sample = the cell nearest to each GDACS event in the period (events from gdacs_history/) plus
`per_country` random cells per country, saved once to reference/history_cells/ so resumed runs
use the same cells. ERA5 lands in open_meteo_era5/year=<y>/, tagged data_source=open_meteo_era5,
request_mode=backfill_history. Runs stop cleanly at `budget` calls and resume on the next run."""
import datetime as dt
import os

import context_lib as ctx
import ingest_lib as lib
import source_registry as reg


def select_history_cells(spark, root, countries, start, end, ingested_at, per_country=80, seed=42):
    out = f"{root}/reference/history_cells"
    if not os.path.exists(out):
        ctx.land_gdacs(root, end, countries, ingested_at, start=start,
                       request_mode="backfill_history", subdir="gdacs_history")
        spark.read.json(f"{root}/reference/grid_cells").createOrReplaceTempView("grid")
        ev = spark.read.json(f"{root}/gdacs_history/run_date={end}")
        if "geometry" not in ev.columns:  # only no_events markers landed
            ev = spark.createDataFrame([], "type string, properties struct<eventid:long, eventtype:string>, "
                                           "geometry struct<type:string, coordinates:array<double>>")
        ev.createOrReplaceTempView("ev")
        isos = ",".join(f"'{c}'" for c in countries if c in reg.GRID_STEP)  # whitelist, no free text
        spark.sql(f"""
          WITH g AS (SELECT * FROM grid WHERE iso3 IN ({isos})),
          e AS (SELECT DISTINCT properties.eventid AS eventid, properties.eventtype AS eventtype,
                       try_cast(geometry.coordinates[0] AS double) AS elon,
                       try_cast(geometry.coordinates[1] AS double) AS elat
                FROM ev WHERE type = 'Feature' AND geometry.type = 'Point'),
          near AS (SELECT g.cell_id, g.iso3, g.lat, g.lon, 'gdacs_event' AS reason,
                          row_number() OVER (PARTITION BY e.eventid, e.eventtype
                                             ORDER BY pow(g.lat - e.elat, 2) + pow(g.lon - e.elon, 2)) AS rk
                   FROM e JOIN g ON abs(g.lat - e.elat) <= 0.3 AND abs(g.lon - e.elon) <= 0.3),
          rnd AS (SELECT cell_id, iso3, lat, lon, 'random' AS reason,
                         row_number() OVER (PARTITION BY iso3 ORDER BY xxhash64(cell_id, {int(seed)})) AS rk
                  FROM g),
          u AS (SELECT * FROM near WHERE rk = 1 UNION ALL SELECT * FROM rnd WHERE rk <= {int(per_country)})
          SELECT cell_id, first(iso3) iso3, first(lat) lat, first(lon) lon,
                 array_sort(collect_set(reason)) AS sample_reasons
          FROM u GROUP BY cell_id""").write.mode("overwrite").json(out)
    return spark.read.json(out)


def land_era5(root, cells, start, end, ingested_at, budget):
    """ERA5 daily history in calendar-year chunks; stops at `budget` weighted calls (resumable)."""
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    tag, limiter = reg.tags("open_meteo_era5", "backfill_history", "era5"), lib.RateLimiter()
    out = {"api_calls": 0, "batches_landed": 0, "batches_skipped": 0, "batches_remaining": 0}
    for y in range(s.year, e.year + 1):
        a, b = max(s, dt.date(y, 1, 1)), min(e, dt.date(y, 12, 31))
        params = {"daily": ",".join(reg.ERA5_DAILY_VARS), "start_date": a.isoformat(),
                  "end_date": b.isoformat(), "timezone": "auto", "models": "era5"}
        r = lib.land_open_meteo(root, "open_meteo_era5", f"year={y}", cells, params, (b - a).days + 1,
                                len(reg.ERA5_DAILY_VARS), tag, ingested_at, budget - out["api_calls"],
                                on_budget="stop", extra={"period_start": a.isoformat(),
                                                         "period_end": b.isoformat()}, limiter=limiter)
        for k in out:
            out[k] = round(out[k] + r[k], 1)
    out["complete"] = out["batches_remaining"] == 0
    return out
