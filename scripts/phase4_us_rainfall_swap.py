"""Phase 4 (US): do the authors' gauged labels survive a swap of rainfall product?

For the 681 US gauged catchments with Source ID GSIM_US_* (metadata: EM-Earth),
keep the authors' own inputs (Event_Inputs: dates, streamflow) and replace the
precipitation with our EM-Earth prcp_corrected basin mean over the same polygon
(scripts/phase2_emearth.py us-gauged). Then detect events and label exactly as
in Phase 0 and compare with the authors' labels.

  190 gauges whose inputs are EM-Earth already (1950-2019 window): must
      reproduce (sanity check; our rainfall covers 1979-2019 only, so the
      window is cut to 1979-2019 here and small differences can arise)
  491 gauges whose inputs look like EMDNA (1979-2018, F11): label flips measure
      sensitivity to the rainfall product

Writes results/phase4/us_rainfall_swap.csv
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from stormflow_diag import forcing, paths
from stormflow_diag.stage1 import events as ev
from stormflow_diag.stage1.regression import fit_catalogue

CACHE = paths.DATA / "phase2" / "forcing" / "emearth" / "us_gauged"
OUT = paths.RESULTS / "phase4"


def _events(args):
    gcin, p = args
    inp = ev.load_event_inputs(gcin)
    inp = inp[(inp.date >= p.index.min()) & (inp.date <= p.index.max())].copy()
    inp["precipitation_mmd"] = p.reindex(inp.date).to_numpy()
    return ev.detect_gauge_events(gcin, inputs=inp, min_events=0)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    a = pd.read_csv(paths.GAUGED_ATTRS).set_index("GCIN")
    ids = sorted(a.index[a["Source ID"].str.startswith("GSIM_US_") & (a.precipitation_source == "EM-Earth")])
    P = forcing.load(CACHE, ids, column=forcing.column("prcp_corrected", "coverage"))
    chk = pd.read_csv(paths.RESULTS / "phase2" / "emearth_vs_authors.csv")
    exact = set(chk[(chk.weighting == "prcp_corrected/coverage") & (chk.frac_close >= 0.99)].GCIN)

    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as ex:
        evs = pd.concat(ex.map(_events, [(g, P[g]) for g in ids], chunksize=8), ignore_index=True)
    fits = fit_catalogue(evs, by=["GCIN", "season"])[["GCIN", "season", "n", "r2_lin", "label_seq"]]

    long = a.loc[ids, ["dormant_gauged_class", "growing_gauged_class"]].rename(
        columns={"dormant_gauged_class": "dormant", "growing_gauged_class": "growing"}).reset_index().melt(
        id_vars="GCIN", var_name="season", value_name="their_label")
    out = long.merge(fits, on=["GCIN", "season"], how="left")
    out["group"] = out.GCIN.map(lambda g: "EM-Earth inputs (190)" if g in exact else "EMDNA-like inputs (491)")
    out = out[out.their_label.notna()]
    out.to_csv(OUT / "us_rainfall_swap.csv", index=False)

    out["agree"] = out.label_seq == out.their_label
    print(out.groupby(["group", "season"]).agg(n=("agree", "size"), labelled=("label_seq", "count"),
                                                agree=("agree", "mean")).round(3))
    for (grp, s), d in out[out.group.str.startswith("EMDNA")].groupby(["group", "season"]):
        print(f"\n{grp} {s}: their label (rows) vs EM-Earth label (cols)")
        print(pd.crosstab(d.their_label, d.label_seq.fillna("<15 events")))


if __name__ == "__main__":
    main()
