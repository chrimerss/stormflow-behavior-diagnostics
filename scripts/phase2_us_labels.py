"""Phase 2: observed functional labels for the US validation catchments.

  python scripts/phase2_us_labels.py [--start 1979-01-01] [--end 2019-12-31] [--allow-gaps]
                                     [--forcing-dir DIR] [--workers N] [--out-dir DIR]

For each US validation station (stormflow.validation_set("usgs")):

1. daily inputs on every day of the analysis window: EM-Earth basin mean over
   the UCIN polygon (scripts/phase2_emearth.py us-validation) and USGS q_mmd
   (data/phase2/streamflow/usgs/<UCIN>.parquet), NaN where USGS has no value.
   As in the authors' Event_Inputs, the series spans the whole window and
   missing streamflow stays NaN;
2. DMCA-ESR events and filters exactly as for the gauged catchments
   (events.detect_gauge_events, gauged=False) with the UCIN's monthly
   phenology from Ungauged_Catchments_Growing_Dormancy_Probability.csv;
3. regression and label (regression.fit_catalogue, label_seq) for every
   season with >= 15 events.

The window is --start..--end cut to the EM-Earth months extracted. A missing
month inside it stops the run, unless --allow-gaps, which uses the longest run
of consecutive months instead (for trial runs only).

Writes results/phase2/us_labels.csv (one row per UCIN and season: n_events,
r2_lin, r2_seg, observed label, the authors' predicted class, record length,
relation to the gauged catchments from us_validation_relations.csv) and
results/phase2/us_events.parquet (the event catalogue).
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from stormflow_diag import forcing, paths
from stormflow_diag import streamflow as sf
from stormflow_diag.stage1 import events as ev
from stormflow_diag.stage1.regression import fit_catalogue

FORCING = paths.DATA / "phase2" / "forcing" / "emearth" / "us_validation"
RELATIONS = paths.RESULTS / "phase2" / "us_validation_relations.csv"
OUT_DIR = paths.RESULTS / "phase2"
SEASONS = ["dormant", "growing"]


def window(forcing_dir, start, end, allow_gaps: bool) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last day of the analysis window, from whole extracted months."""
    have = [pd.Period(f"{m[:4]}-{m[4:]}", "M") for m in forcing.cached_months(forcing_dir)]
    want = pd.period_range(pd.Timestamp(start).to_period("M"), pd.Timestamp(end).to_period("M"), freq="M")
    have = sorted(set(have) & set(want))
    if not have:
        raise SystemExit(f"no EM-Earth months for {start}..{end} in {forcing_dir}")
    span = pd.period_range(have[0], have[-1], freq="M")
    missing = sorted(set(span) - set(have))
    if missing:
        if not allow_gaps:
            raise SystemExit(f"{len(missing)} months missing between {have[0]} and {have[-1]}, e.g. "
                             f"{[str(m) for m in missing[:6]]}; extract them or pass --allow-gaps")
        runs, cur = [], [have[0]]
        for p in have[1:]:
            if p == cur[-1] + 1:
                cur.append(p)
            else:
                runs.append(cur)
                cur = [p]
        runs.append(cur)
        best = max(runs, key=len)
        print(f"WARNING: {len(missing)} months missing; using the longest run {best[0]}..{best[-1]} "
              f"({len(best)} months)")
        have = best
    return have[0].start_time, have[-1].end_time.normalize()


def _detect(args) -> tuple[pd.DataFrame, dict]:
    ucin, inputs, pheno = args
    q = inputs.streamflow_mmd
    valid = inputs.loc[q.notna() & inputs.precipitation_mmd.notna(), "date"]
    per_year = valid.dt.year.value_counts()
    info = {"UCIN": ucin, "first_q": valid.min(), "last_q": valid.max(), "n_days_valid": len(valid),
            "n_years_ge_300": int((per_year >= 300).sum()), "n_p_nan": int(inputs.precipitation_mmd.isna().sum())}
    if info["n_p_nan"]:
        info["status"] = "precipitation has NaN days"
        return pd.DataFrame(), info
    try:
        e = ev.detect_gauge_events(ucin, min_events=0, inputs=inputs, phenology=pheno, gauged=False)
    except ValueError as err:  # e.g. DMCA correlation NaN everywhere
        info["status"] = f"error: {err}"
        return pd.DataFrame(), info
    info.update(status="ok", Tr=int(e.Tr.iloc[0]) if len(e) else np.nan)
    return e.rename(columns={"GCIN": "UCIN"}), info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="1979-01-01")
    ap.add_argument("--end", default="2019-12-31")
    ap.add_argument("--allow-gaps", action="store_true")
    ap.add_argument("--forcing-dir", default=str(FORCING))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="where us_labels.csv and us_events.parquet go")
    a = ap.parse_args()

    val = sf.validation_set("usgs")
    t0, t1 = window(a.forcing_dir, a.start, a.end, a.allow_gaps)
    print(f"{len(val)} US validation stations; window {t0.date()} .. {t1.date()}")
    # the authors' EM-Earth series: prcp_corrected, plain coverage mean (F11)
    P = forcing.load(a.forcing_dir, val.UCIN, column=forcing.column("prcp_corrected", "coverage"), start=t0, end=t1)
    days = pd.date_range(t0, t1, freq="D")
    missing_ids = sorted(set(val.UCIN) - set(P.columns))
    if missing_ids:
        raise SystemExit(f"{len(missing_ids)} UCINs have no precipitation in {a.forcing_dir}, e.g. {missing_ids[:5]}")
    P = P.reindex(days)
    pheno = pd.read_csv(paths.UNGAUGED_PHENOLOGY, index_col="UCIN")

    def tasks():
        for u in val.UCIN:
            q = pd.read_parquet(sf.OUT / "usgs" / f"{u}.parquet", columns=["date", "q_mmd"]).set_index("date").q_mmd
            inputs = pd.DataFrame({"date": days, "precipitation_mmd": P[u].to_numpy(),
                                   "streamflow_mmd": q.reindex(days).to_numpy()})
            yield u, inputs, pheno.loc[u, ev.MONTHS].to_numpy(float)

    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        out = list(ex.map(_detect, tasks(), chunksize=4))
    events = pd.concat([e for e, _ in out if len(e)], ignore_index=True)
    info = pd.DataFrame([i for _, i in out])
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events.to_parquet(out_dir / "us_events.parquet", index=False)
    print(f"{len(events):,} events at {events.UCIN.nunique()} catchments; status {info.status.value_counts().to_dict()}")

    fits = fit_catalogue(events, by=["UCIN", "season"], workers=a.workers)
    fits["r2_seg"] = np.select([fits.k_seq == 1, fits.k_seq == 2], [fits.r2_seg1, fits.r2_seg2], fits.r2_lin)
    fits = fits.rename(columns={"label_seq": "label"})[["UCIN", "season", "r2_lin", "r2_seg", "k_seq", "label"]]

    grid = pd.MultiIndex.from_product([val.UCIN, SEASONS], names=["UCIN", "season"]).to_frame(index=False)
    n = events.groupby(["UCIN", "season"]).size().rename("n_events").reset_index()
    res = grid.merge(n, how="left").merge(fits, how="left").fillna({"n_events": 0})
    res["predicted"] = np.where(res.season == "dormant", res.UCIN.map(val.set_index("UCIN").dormant_predicted_class),
                                res.UCIN.map(val.set_index("UCIN").growing_predicted_class))
    res = res.merge(val[["UCIN", "Source ID", "national_id"]], on="UCIN").merge(info, on="UCIN")
    if RELATIONS.exists():
        rel = pd.read_csv(RELATIONS)[["UCIN", "relation", "relation_gcin", "same_catchment", "nearest_gcin",
                                      "nearest_dist_km"]]
        res = res.merge(rel, on="UCIN", how="left")
    res.insert(res.columns.get_loc("status"), "window", f"{t0.date()}..{t1.date()}")
    res.to_csv(out_dir / "us_labels.csv", index=False, float_format="%.6g")

    for s in SEASONS:
        r = res[(res.season == s) & res.label.notna()]
        print(f"\n{s}: {len(r)} labelled of {(res.season == s).sum()}")
        print(pd.crosstab(r.label, r.predicted, margins=True).to_string())


if __name__ == "__main__":
    main()
