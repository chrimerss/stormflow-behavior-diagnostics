"""Phase 4: is the label a property of the catchment or of the period?

For each gauged catchment-season in the authors' event catalogue, split the
events into two halves and label each half with the same rule:

  chrono : first vs second half of the events in time (tests stationarity)
  random : two random halves of the same sizes (sampling noise only)

If chronological halves disagree more often than random halves, the label
drifts over time beyond what the smaller sample explains. Halves with fewer
than 15 events (the authors' minimum) are not labelled.

Writes results/phase4/split_half_fits.csv and prints agreement tables.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stormflow_diag import paths
from stormflow_diag.stage1.regression import fit_catalogue

OUT = paths.RESULTS / "phase4"
MIN_EVENTS = 15


def halves(ev: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    ev = ev.sort_values(["GCIN", "start_precip_date"]).copy()
    rank = ev.groupby("GCIN").cumcount()
    n = ev.groupby("GCIN").GCIN.transform("size")
    chrono = ev.assign(split="chrono", half=np.where(rank < n // 2, "a", "b"))
    rng = np.random.default_rng(seed)
    shuffled = ev.assign(_r=rng.random(len(ev))).sort_values(["GCIN", "_r"])
    rrank = shuffled.groupby("GCIN").cumcount()
    random = shuffled.drop(columns="_r").assign(split="random", half=np.where(rrank < n.loc[shuffled.index] // 2, "a", "b"))
    return pd.concat([chrono, random], ignore_index=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    attrs = pd.read_csv(paths.GAUGED_ATTRS).set_index("GCIN")
    frames = []
    for season, f in paths.EVENTS.items():
        ev = pd.read_csv(f, usecols=["GCIN", "start_precip_date", "volume_precip_mm", "volume_stormflow_mm"])
        fits = fit_catalogue(halves(ev), by=["GCIN", "split", "half"], min_events=MIN_EVENTS)
        fits["season"] = season
        fits = fits.join(attrs[f"{season}_gauged_class"].rename("full_label"), on="GCIN")
        frames.append(fits)
    fits = pd.concat(frames, ignore_index=True)
    fits.to_csv(OUT / "split_half_fits.csv", index=False)

    wide = fits.pivot_table(index=["season", "GCIN", "split", "full_label"], columns="half",
                            values="label_seq", aggfunc="first").dropna().reset_index()
    wide["agree"] = wide.a == wide.b
    print("Agreement between halves (both halves >= 15 events):")
    print(wide.groupby(["season", "split"]).agg(n=("agree", "size"), agree=("agree", "mean")).round(3))
    print("\nBy full-record label:")
    print(wide.groupby(["season", "full_label", "split"]).agg(n=("agree", "size"), agree=("agree", "mean"))
          .round(3).unstack("split"))
    for season in ["dormant", "growing"]:
        w = wide[(wide.season == season) & (wide.split == "chrono")]
        print(f"\n[{season}] chronological halves, first (rows) vs second (cols):")
        print(pd.crosstab(w.a, w.b).reindex(index=["simple", "intermediate", "complex"],
                                            columns=["simple", "intermediate", "complex"], fill_value=0))


if __name__ == "__main__":
    main()
