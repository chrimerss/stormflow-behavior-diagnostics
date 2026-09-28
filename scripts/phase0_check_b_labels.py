"""Phase 0, Check B end to end: labels from the raw daily series.

Our DMCA-ESR events (from Event_Inputs.zip) go through our regression and
labelling, and the labels are compared with the authors'. Two season splits:

  released : seasons from the released phenology CSV (everything rebuilt from
             released data)
  theirs   : each of our events takes the season of the identical event in
             their catalogue (isolates event detection + regression); events
             not in their catalogue fall back to the released CSV

Gauges whose Source ID starts with 'WRR_' are reported separately: their
catalogue seasons do not follow the released phenology CSV.

Writes results/phase0/our_events.parquet (not tracked) and
results/phase0/check_b_labels.csv
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from stormflow_diag import paths
from stormflow_diag.stage1.events import detect_gauge_events, load_catalogue
from stormflow_diag.stage1.regression import fit_catalogue

OUT = paths.RESULTS / "phase0"
KEY = ["GCIN", "start_precip_date", "end_precip_date", "start_stormflow_date", "end_stormflow_date"]


def _detect(gcin: int) -> pd.DataFrame:
    return detect_gauge_events(gcin, min_events=0)


def our_events(gcins) -> pd.DataFrame:
    cache = OUT / "our_events.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as ex:
        ev = pd.concat(ex.map(_detect, gcins, chunksize=8), ignore_index=True)
    ev.to_parquet(cache, index=False)
    return ev


def label(ev: pd.DataFrame, season_col: str) -> pd.DataFrame:
    fits = fit_catalogue(ev.rename(columns={season_col: "season_"}), by=["GCIN", "season_"])
    return fits.rename(columns={"season_": "season"})[["GCIN", "season", "n", "r2_lin", "label_seq"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    attrs = pd.read_csv(paths.GAUGED_ATTRS).set_index("GCIN")
    ev = our_events(attrs.index.tolist())
    print(f"our events: {len(ev):,} at {ev.GCIN.nunique()} gauges")

    cat = load_catalogue()[KEY + ["season"]].rename(columns={"season": "season_theirs"})
    ev = ev.merge(cat, on=KEY, how="left")
    print(f"matched to their catalogue: {ev.season_theirs.notna().sum():,}")
    ev["season_theirs"] = ev.season_theirs.fillna(ev.season)

    rows = []
    for variant, col in [("released", "season"), ("theirs", "season_theirs")]:
        lab = label(ev, col).assign(variant=variant)
        rows.append(lab)
    lab = pd.concat(rows, ignore_index=True)

    theirs = attrs[["dormant_gauged_class", "growing_gauged_class", "Source ID"]].rename(
        columns={"dormant_gauged_class": "dormant", "growing_gauged_class": "growing"})
    long = theirs.melt(id_vars="Source ID", value_vars=["dormant", "growing"], var_name="season",
                       value_name="their_label", ignore_index=False).reset_index()
    out = long.merge(lab, on=["GCIN", "season"], how="left")
    out["wrr"] = out["Source ID"].str.startswith("WRR_")
    out = out[out.their_label.notna() & out.variant.notna()]
    out.to_csv(OUT / "check_b_labels.csv", index=False)

    out["agree"] = out.label_seq == out.their_label
    print("\nLabel agreement with the authors (their labelled gauge-seasons):")
    print(out.groupby(["variant", "wrr", "season"]).agg(n=("agree", "size"), agree=("agree", "mean")).round(4))
    print(out.groupby(["variant"]).agg(n=("agree", "size"), agree=("agree", "mean")).round(4))
    for v in ["released", "theirs"]:
        s = out[(out.variant == v) & (out.their_label == "simple")]
        print(f"[{v}] simple reproduced: " + ", ".join(
            f"{k} {int(d.agree.sum())}/{len(d)}" for k, d in s.groupby("season")))
    missing = long[long.their_label.notna()].merge(lab[lab.variant == "released"], on=["GCIN", "season"], how="left")
    print("their labelled gauge-seasons with <15 of our events under released seasons:",
          int(missing.label_seq.isna().sum()))


if __name__ == "__main__":
    main()
