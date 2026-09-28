"""Phase 0, Check A: does the authors' regression rule reproduce their labels
from their own event catalogue?

Writes
  results/phase0/check_a_fits.csv        one row per GCIN x season, all fits and label variants
  results/phase0/check_a_zenodo2024.csv  same fits on the 2024 release, next to its reported R2
and prints agreement tables.
"""
from __future__ import annotations

import pandas as pd

from stormflow_diag import paths
from stormflow_diag.stage1.regression import fit_catalogue

OUT = paths.RESULTS / "phase0"
VARIANTS = ["label_seq", "label_selg", "label_any_seg"]
CLASSES = ["simple", "intermediate", "complex"]


def figshare_fits() -> pd.DataFrame:
    attrs = pd.read_csv(paths.GAUGED_ATTRS).set_index("GCIN")
    frames = []
    for season, f in paths.EVENTS.items():
        ev = pd.read_csv(f, usecols=["GCIN", "volume_precip_mm", "volume_stormflow_mm"])
        fits = fit_catalogue(ev, by=["GCIN"])
        fits["season"] = season
        fits = fits.join(attrs[f"{season}_gauged_class"].rename("their_label"), on="GCIN")
        fits = fits.join(attrs[["Catchment_Boundary_Flagged", "country"]], on="GCIN")
        frames.append(fits)
    return pd.concat(frames, ignore_index=True)


def zenodo_fits() -> pd.DataFrame:
    base = paths.ZENODO_2024 / "regression_and_spectral_analysis"
    frames = []
    for season in ["dormant", "growing"]:
        ev = pd.read_csv(base / f"study_catchments_identified_events_{season}.csv")
        rep = pd.read_csv(base / f"study_catchments_regression_coherency_attributes_{season}.csv")
        fits = fit_catalogue(ev, by=["Gridcode"])
        fits["season"] = season
        rep = rep.set_index("Gridcode")[["valid_model", "behavioral_class", "R2", "num_events"]]
        frames.append(fits.join(rep, on="Gridcode"))
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    fs = figshare_fits()
    fs.to_csv(OUT / "check_a_fits.csv", index=False)
    lab = fs[fs.their_label.notna()]
    print(f"Figshare: {len(fs)} catchment-seasons fitted, {len(lab)} with an observed label\n")
    for season, d in lab.groupby("season"):
        for v in VARIANTS:
            agree = (d[v] == d.their_label).mean()
            print(f"[{season}] {v}: agreement {agree:.4f}  ({(d[v] != d.their_label).sum()} mismatches)")
            print(pd.crosstab(d.their_label, d[v]).reindex(index=CLASSES, columns=CLASSES, fill_value=0), "\n")

    zf = zenodo_fits()
    zf.to_csv(OUT / "check_a_zenodo2024.csv", index=False)
    zf["their_k"] = zf.valid_model.str.extract(r"\((\d) Bp")[0].astype(float).fillna(0)
    lin = zf.valid_model == "Linear Model"
    zf.loc[lin, "their_k"] = 0
    print("Zenodo 2024: reported R2 vs our fits")
    for vm, d in zf.groupby("valid_model"):
        col = {"Linear Model": "r2_lin", "Segmented Model (1 Bp)": "r2_seg1",
               "Segmented Model (2 Bps)": "r2_seg2"}.get(vm)
        if col is None:
            continue
        err = (d[col] - d.R2).abs()
        print(f"  {vm:26s} n={len(d):4d}  |ours-theirs| median {err.median():.4f}  max {err.max():.4f}")
    seg = zf[zf.valid_model.str.startswith("Segmented", na=False)]
    print("  segmented cases, their k vs our k_seq / k_selgmented:")
    print(pd.crosstab(seg.their_k, seg.k_seq), "\n", pd.crosstab(seg.their_k, seg.k_selgmented))


if __name__ == "__main__":
    main()
