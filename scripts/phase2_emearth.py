"""Phase 2: EM-Earth basin-mean precipitation for the US polygon sets, and a check
of the extraction against the authors' Event_Inputs.

  python scripts/phase2_emearth.py us-validation [--emearth-dir DIR] [--include-cloud]
  python scripts/phase2_emearth.py us-gauged     [--emearth-dir DIR] [--include-cloud]
  python scripts/phase2_emearth.py check

us-validation : the UCIN polygons of the US validation set
                (stormflow.validation_set) -> data/phase2/forcing/emearth/us_validation/
us-gauged     : the authors' gauged polygons with Source ID GSIM_US_* (their
                precipitation_source is EM-Earth), with both area and plain
                coverage weights -> data/phase2/forcing/emearth/us_gauged/
check         : compares the us-gauged extraction with `precipitation_mmd` in
                Event_Inputs/<GCIN>.csv, which is their EM-Earth basin mean over
                the same polygons, on every day extracted so far. Writes
                results/phase2/emearth_vs_authors.csv, one row per GCIN and weighting:
                n_days, frac_close (|ours - theirs| <= 0.1 % + 0.001 mm), max/mean
                absolute difference, ratio of totals, and correlation at lags
                -1/0/+1 days (a best lag other than 0 means a date offset).

Extraction is incremental: months already in the cache are skipped, and
cloud-only placeholder files are skipped unless --include-cloud (opening one
starts its download). The EM-Earth directory comes from --emearth-dir or
EMEARTH_DIR.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from stormflow_diag import forcing, paths
from stormflow_diag import streamflow as sf
from stormflow_diag.stage1 import events as ev

CACHE = paths.DATA / "phase2" / "forcing" / "emearth"
CHECK_CSV = paths.RESULTS / "phase2" / "emearth_vs_authors.csv"


def us_gauged_ids() -> list[int]:
    m = pd.read_csv(paths.GAUGED_ATTRS, usecols=["GCIN", "Source ID", "precipitation_source"])
    m = m[m["Source ID"].str.startswith("GSIM_US_") & (m.precipitation_source == "EM-Earth")]
    return sorted(m.GCIN)


def run_extract(which: str, emearth_dir, include_cloud: bool) -> None:
    if which == "us-validation":
        polys = forcing.boundaries("ungauged", sf.validation_set("usgs").UCIN)
        weightings = ("area",)
    else:
        polys = forcing.boundaries("gauged", us_gauged_ids())
        weightings = ("area", "coverage")
    cache = CACHE / which.replace("-", "_")
    status = forcing.extract(forcing.emearth_dir(emearth_dir), polys.geometry, cache, weightings=weightings,
                             include_cloud=include_cloud)
    forcing.write_manifest(cache, status)
    counts = pd.Series(status).str.split(":").str[0].value_counts()
    print(f"{which}: {len(polys)} polygons; months {counts.to_dict()}; cached {len(forcing.cached_months(cache))}")


def _lag_corr(a: np.ndarray, b: np.ndarray, lag: int) -> float:
    """corr(ours[t], theirs[t + lag])"""
    if lag > 0:
        a, b = a[:-lag], b[lag:]
    elif lag < 0:
        a, b = a[-lag:], b[:lag]
    ok = np.isfinite(a) & np.isfinite(b)
    return np.corrcoef(a[ok], b[ok])[0, 1] if ok.sum() > 2 else np.nan


def run_check() -> None:
    cache = CACHE / "us_gauged"
    months = forcing.cached_months(cache)
    if not months:
        raise SystemExit(f"nothing extracted in {cache}; run `us-gauged` first")
    print(f"{len(months)} months extracted: {months[0]} .. {months[-1]}")
    ids = us_gauged_ids()
    ours = {w: forcing.load(cache, ids, column=c) for w, c in forcing.WEIGHTINGS.items()}
    valid = forcing.load(cache, ids, column="valid_frac")
    rows = []
    for g in ids:
        theirs = ev.load_event_inputs(g).set_index("date").precipitation_mmd
        for w, o in ours.items():
            d = pd.concat([o[g].rename("ours"), theirs.rename("theirs")], axis=1, join="inner").dropna()
            diff = (d.ours - d.theirs).to_numpy()
            # lags on the full daily index (months may not be contiguous)
            full = pd.concat([o[g].rename("ours"), theirs.rename("theirs")], axis=1).sort_index()
            full = full.reindex(pd.date_range(full.index.min(), full.index.max(), freq="D"))
            lag = {k: _lag_corr(full.ours.to_numpy(), full.theirs.to_numpy(), k) for k in (-1, 0, 1)}
            rows.append({
                "GCIN": g, "weighting": w, "n_days": len(d),
                "frac_close": float(np.mean(np.abs(diff) <= 1e-3 * d.theirs.abs() + 1e-3)) if len(d) else np.nan,
                "max_abs_diff": float(np.abs(diff).max()) if len(d) else np.nan,
                "mean_abs_diff": float(np.abs(diff).mean()) if len(d) else np.nan,
                "ratio_totals": d.ours.sum() / d.theirs.sum() if len(d) and d.theirs.sum() > 0 else np.nan,
                "corr_lag_m1": lag[-1], "corr_lag_0": lag[0], "corr_lag_p1": lag[1],
                "min_valid_frac": float(valid[g].min()),
            })
    res = pd.DataFrame(rows)
    res["best_lag"] = res[["corr_lag_m1", "corr_lag_0", "corr_lag_p1"]].idxmax(axis=1).map(
        {"corr_lag_m1": -1, "corr_lag_0": 0, "corr_lag_p1": 1})
    CHECK_CSV.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(CHECK_CSV, index=False, float_format="%.6g")
    for w, r in res.groupby("weighting"):
        print(f"\n{w} weights, {len(r)} GCINs, {r.n_days.median():.0f} days each (median)")
        print(f"  GCINs with >= 99 % of days within 0.1 % + 0.001 mm: {(r.frac_close >= 0.99).sum()}")
        print(r[["frac_close", "mean_abs_diff", "max_abs_diff", "ratio_totals", "corr_lag_0"]]
              .describe(percentiles=[.05, .25, .5, .75, .95]).to_string())
        print(f"  best lag: {r.best_lag.value_counts().to_dict()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["us-validation", "us-gauged", "check"])
    ap.add_argument("--emearth-dir", help="directory of EM_Earth_deterministic_daily_prcp_YYYYMM.nc (or EMEARTH_DIR)")
    ap.add_argument("--include-cloud", action="store_true",
                    help="also open cloud-only placeholder files (starts their download)")
    a = ap.parse_args()
    if a.what == "check":
        run_check()
    else:
        run_extract(a.what, a.emearth_dir, a.include_cloud)


if __name__ == "__main__":
    main()
