"""Phase 0, check B (pilot): our DMCA-ESR events against the authors' catalogue.

Runs ``detect_gauge_events`` on ~20 gauges spread across countries (one per
country for the 14 largest countries, plus six dormant-season 'simple'
gauges), compares with Identified_Rainfall_Runoff_Events_{Dormant,Growing}.csv
per gauge and season, and writes results/phase0/check_b_pilot.csv.

An event matches when all four dates (start/end of precipitation and of
stormflow) are identical. Season rows compare events within the same season;
the 'all' row ignores season, so event detection is judged separately from
the season split. ``min_events=0`` is used because the released catalogue
keeps seasons with fewer than 15 events.

Usage
-----
python scripts/phase0_check_b_pilot.py
python scripts/phase0_check_b_pilot.py --gcins 1 100 2660
python scripts/phase0_check_b_pilot.py --all --jobs 6 --out results/phase0/check_b_all.csv
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from stormflow_diag import paths
from stormflow_diag.stage1 import events as ev

KEYS = ["start_precip_date", "end_precip_date", "start_stormflow_date", "end_stormflow_date"]
OUT = paths.RESULTS / "phase0" / "check_b_pilot.csv"


def select_pilot_gcins(attrs: pd.DataFrame, seed: int = 0) -> list[int]:
    """One gauge per country for the 14 largest countries, plus six dormant
    'simple' gauges from distinct countries."""
    rng = np.random.default_rng(seed)
    countries = attrs["country"].value_counts().index[:14]
    picks = [int(rng.choice(attrs.index[attrs["country"] == c])) for c in countries]
    simple = attrs[(attrs["dormant_gauged_class"] == "simple") & ~attrs.index.isin(picks)]
    simple = simple.loc[rng.permutation(simple.index)].drop_duplicates("country")
    picks += [int(g) for g in simple.index[:6]]
    return sorted(picks)


def _rel(a, b):
    return np.abs(a - b) / np.abs(b)


def compare_gauge(gcin, theirs, phenology, attrs):
    """Rows (one per season and one for 'all') comparing our events with theirs."""
    t0 = time.time()
    ours = ev.detect_gauge_events(gcin, min_events=0, phenology=phenology, attributes=attrs)
    a = attrs.loc[gcin]
    base = {
        "GCIN": gcin, "country": a["country"], "source_id": a["Source ID"],
        "streamflow_source": a["streamflow_source"], "precipitation_source": a["precipitation_source"],
        "Tr": int(ours["Tr"].iloc[0]) if len(ours) else np.nan,
    }
    both = ours.merge(theirs, on=KEYS, suffixes=("", "_t"))
    pheno_same = bool(np.allclose(both["growing_dormancy_prob"], both["growing_dormancy_prob_t"],
                                  rtol=0, atol=1e-12)) if len(both) else np.nan
    rows = []
    for season in ["dormant", "growing", "all"]:
        if season == "all":
            o, t, m = ours, theirs, both
        else:
            o = ours[ours["season"] == season]
            t = theirs[theirs["season"] == season]
            m = both[(both["season"] == season) & (both["season_t"] == season)]
        row = dict(base, season=season, n_theirs=len(t), n_ours=len(o), n_matched=len(m),
                   frac_theirs_matched=len(m) / len(t) if len(t) else np.nan,
                   frac_ours_matched=len(m) / len(o) if len(o) else np.nan)
        row["phenology_matches_csv"] = pheno_same
        if season == "all":
            row["matched_same_season"] = int((m["season"] == m["season_t"]).sum())
            row["class_theirs"] = ""
        else:
            row["matched_same_season"] = len(m)
            row["class_theirs"] = a[f"{season}_gauged_class"]
        if len(m):
            dp = _rel(m["volume_precip_mm"], m["volume_precip_mm_t"])
            dq = _rel(m["volume_stormflow_mm"], m["volume_stormflow_mm_t"])
            row.update(
                max_rel_diff_volume_precip=dp.max(), median_rel_diff_volume_precip=dp.median(),
                max_rel_diff_volume_stormflow=dq.max(),
                median_rel_diff_volume_stormflow=dq.median(),
                max_abs_diff_volume_stormflow_mm=(m["volume_stormflow_mm"]
                                                  - m["volume_stormflow_mm_t"]).abs().max(),
                max_abs_diff_runoff_ratio=(m["runoff_ratio"] - m["runoff_ratio_t"]).abs().max())
        row["seconds"] = round(time.time() - t0, 2)
        rows.append(row)
    return rows


_STATE: dict = {}


def _worker(gcin):
    cat, pheno, attrs = _STATE["cat"], _STATE["pheno"], _STATE["attrs"]
    theirs = cat[cat["GCIN"] == gcin]
    return compare_gauge(gcin, theirs, pheno.loc[gcin, ev.MONTHS].to_numpy(float), attrs)


def _init(cat, pheno, attrs):
    _STATE.update(cat=cat, pheno=pheno, attrs=attrs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gcins", type=int, nargs="*")
    ap.add_argument("--all", action="store_true", help="every gauge in the catalogue")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    attrs = pd.read_csv(paths.GAUGED_ATTRS, index_col="GCIN")
    pheno = pd.read_csv(paths.GAUGED_PHENOLOGY, index_col="GCIN")
    if args.all:
        gcins = attrs.index.tolist()
    else:
        gcins = args.gcins or select_pilot_gcins(attrs)
    print(f"{len(gcins)} gauges: {gcins if len(gcins) <= 30 else str(gcins[:30]) + ' ...'}")

    cat = ev.load_catalogue(None if args.all else gcins)
    t0 = time.time()
    if args.jobs > 1:
        with ProcessPoolExecutor(args.jobs, initializer=_init, initargs=(cat, pheno, attrs)) as ex:
            nested = list(ex.map(_worker, gcins, chunksize=8))
    else:
        _init(cat, pheno, attrs)
        nested = [_worker(g) for g in gcins]
    table = pd.DataFrame([r for rows in nested for r in rows])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False, float_format="%.6g")

    allrows = table[table["season"] == "all"]
    print(f"done in {time.time() - t0:.0f}s -> {out}")
    print(f"events: theirs {allrows.n_theirs.sum()}, ours {allrows.n_ours.sum()}, "
          f"matched {allrows.n_matched.sum()} "
          f"({allrows.n_matched.sum() / allrows.n_theirs.sum():.5%} of theirs)")
    print(f"gauges with every event matched: {(allrows.n_matched == allrows.n_theirs).sum()}"
          f" / {len(allrows)} (and no extra events: "
          f"{((allrows.n_matched == allrows.n_theirs) & (allrows.n_ours == allrows.n_theirs)).sum()})")
    print(f"matched events in the same season: {allrows.matched_same_season.sum()} / "
          f"{allrows.n_matched.sum()}; gauges whose catalogue phenology differs from the CSV: "
          f"{(allrows.phenology_matches_csv == False).sum()}")  # noqa: E712
    print(f"max relative volume difference (matched): precip "
          f"{allrows.max_rel_diff_volume_precip.max():.2e}, stormflow "
          f"{allrows.max_rel_diff_volume_stormflow.max():.2e}")
    if not args.all:
        cols = ["GCIN", "country", "season", "class_theirs", "Tr", "n_theirs", "n_ours",
                "n_matched", "frac_theirs_matched", "phenology_matches_csv",
                "max_rel_diff_volume_precip", "max_rel_diff_volume_stormflow"]
        with pd.option_context("display.width", 200, "display.max_rows", 200):
            print(table[cols].to_string(index=False))


if __name__ == "__main__":
    main()
