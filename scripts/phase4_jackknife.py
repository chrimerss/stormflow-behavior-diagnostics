"""Phase 4: reproduce the authors' jackknife next to a disjoint-halves test.

Authors (Methods): 100 rounds per catchment-season of an 80 % random subsample
without replacement; certainty = share of rounds that keep the full-sample label.
They report median certainty (dormant / growing): simple 98 / 86 %,
intermediate 96 / 92 %, complex 100 / 100 %.

To keep run time reasonable we use every simple gauge and a random 200
intermediate and 200 complex gauges per season.

Writes results/phase4/jackknife.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stormflow_diag import paths
from stormflow_diag.stage1.regression import fit_catalogue

OUT = paths.RESULTS / "phase4"
ROUNDS, FRACTION, PER_CLASS, SEED = 100, 0.8, 200, 7


def sample_gauges(attrs: pd.DataFrame, season: str, rng) -> list[int]:
    lab = attrs[f"{season}_gauged_class"]
    ids = list(lab.index[lab == "simple"])
    for c in ["intermediate", "complex"]:
        pool = lab.index[lab == c].to_numpy()
        ids += list(rng.choice(pool, size=min(PER_CLASS, len(pool)), replace=False))
    return ids


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    attrs = pd.read_csv(paths.GAUGED_ATTRS).set_index("GCIN")
    frames = []
    for season, f in paths.EVENTS.items():
        ev = pd.read_csv(f, usecols=["GCIN", "volume_precip_mm", "volume_stormflow_mm"])
        ev = ev[ev.GCIN.isin(sample_gauges(attrs, season, rng))]
        reps = []
        for r in range(ROUNDS):
            sub = ev.groupby("GCIN", group_keys=False).sample(frac=FRACTION, random_state=int(rng.integers(1 << 31)))
            reps.append(sub.assign(round=r))
        fits = fit_catalogue(pd.concat(reps), by=["GCIN", "round"], min_events=1)
        fits["season"] = season
        frames.append(fits.join(attrs[f"{season}_gauged_class"].rename("full_label"), on="GCIN"))
    fits = pd.concat(frames, ignore_index=True)
    fits.to_csv(OUT / "jackknife.csv", index=False)

    cert = (fits.assign(keep=fits.label_seq == fits.full_label)
            .groupby(["season", "full_label", "GCIN"]).keep.mean())
    summary = cert.groupby(["season", "full_label"]).agg(n="size", median="median", q25=lambda x: x.quantile(.25))
    print("Jackknife certainty (share of 80 % subsamples keeping the full label):")
    print(summary.round(3))


if __name__ == "__main__":
    main()
