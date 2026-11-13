"""Core ingestion helpers: HTTP retries, free-tier rate limiting, atomic landing writers and the
Open-Meteo downloader. Every JSONL row is tagged with its data source (see source_registry.py).
Reference/context sources (grid, GeoNames, ENSO, GDACS) live in context_lib.py."""
import hashlib
import json
import os
import time

import requests

import source_registry as reg


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
    """Write via a .tmp file and rename, so an interrupted run never leaves a partial file that a
    resume would treat as done (readers should glob the final extension, e.g. *.jsonl)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def write_jsonl(path, records):
    write_text(path, "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")


def calls_per_point(days, n_vars=len(reg.DAILY_VARS)):
    """Open-Meteo weighting: >14 days or >10 variables per location count as fractional extra calls."""
    return max(1, days / 14) * max(1, n_vars / 10)


def land_open_meteo(root, subdir, partition, points, params, days, n_vars, tag, ingested_at, budget,
                    on_budget="raise", batch=100, extra=None, limiter=None):
    """Rate-limited, resumable multi-location Open-Meteo download into <subdir>/<partition>/.
    on_budget='raise' refuses a run over `budget` calls; 'stop' lands batches up to the budget and
    returns (re-run later to resume). File = index + fingerprint of request params and cell ids, so
    only an identical request is skipped."""
    cpp = calls_per_point(days, n_vars)
    if on_budget == "raise" and len(points) * cpp > budget:
        raise ValueError(f"{len(points)} points x {cpp:.2f} calls = {len(points) * cpp:.0f} > budget "
                         f"{budget:.0f}; reduce days, points or countries")
    batch = max(1, min(batch, int(500 // cpp)))  # one request must fit the 600/min limit
    out_dir, calls, skipped, landed = f"{root}/{subdir}/{partition}", 0, 0, 0
    limiter = limiter or RateLimiter()  # share one limiter across calls in the same run
    for b in range(0, len(points), batch):
        chunk = points[b:b + batch]
        key = "|".join([json.dumps(params, sort_keys=True)] + [p.cell_id for p in chunk])
        path = f"{out_dir}/batch_{b // batch:04d}_{hashlib.sha1(key.encode()).hexdigest()[:12]}.jsonl"
        if os.path.exists(path):
            skipped += 1
            continue
        if calls + len(chunk) * cpp > budget:
            break
        limiter.acquire(len(chunk) * cpp)
        body = http_get(tag["source_url"], params={"latitude": ",".join(str(p.lat) for p in chunk),
                                                   "longitude": ",".join(str(p.lon) for p in chunk), **params}).json()
        body = body if isinstance(body, list) else [body]
        assert len(body) == len(chunk), f"expected {len(chunk)} locations, got {len(body)}"
        write_jsonl(path, [{"cell_id": p.cell_id, "req_lat": p.lat, "req_lon": p.lon, **(extra or {}),
                            "ingested_at": ingested_at, **tag, **loc} for p, loc in zip(chunk, body)])
        calls, landed = calls + len(chunk) * cpp, landed + 1
    total = -(-len(points) // batch)
    return {"points": len(points), "api_calls": round(calls, 1), "batches_landed": landed,
            "batches_skipped": skipped, "batches_remaining": total - landed - skipped}


# Backward-compatible names for callers that still use lib.land_reference / land_enso / land_gdacs
# (lazy import: context_lib imports this module).
def land_reference(*a, **k):
    import context_lib
    return context_lib.land_reference(*a, **k)


def land_enso(*a, **k):
    import context_lib
    return context_lib.land_enso(*a, **k)


def land_gdacs(*a, **k):
    import context_lib
    return context_lib.land_gdacs(*a, **k)


def land_forecast(root, run_date, points, past_days, forecast_days, ingested_at, budget,
                  request_mode="daily", on_budget="raise"):
    """Forecast API; daily runs land in open_meteo_forecast/, backfills in open_meteo_forecast_backfill/."""
    subdir = "open_meteo_forecast" if request_mode == "daily" else "open_meteo_forecast_backfill"
    params = {"daily": ",".join(reg.DAILY_VARS), "past_days": past_days, "forecast_days": forecast_days,
              "timezone": "auto"}
    s = land_open_meteo(root, subdir, f"run_date={run_date}", points, params, past_days + forecast_days,
                        len(reg.DAILY_VARS), reg.tags("open_meteo_forecast", request_mode, "best_match"),
                        ingested_at, budget, on_budget, extra={"run_date": run_date})
    return {**{f"forecast_{k}": v for k, v in s.items()}, "past_days": past_days, "forecast_days": forecast_days}
