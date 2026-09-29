"""Phase 3 (US): score the authors' predictions on independent USGS gauges.

Observed labels come from scripts/phase2_us_labels.py (our reproduction of the
authors' labelling on EM-Earth prcp_corrected and USGS flow). Predictions:

  authors         : the released XGBoost models, applied by us to the authors'
                    ungauged attribute table (checked against their published
                    predicted class)
  always_complex  : the majority class
  climate_only    : XGBoost on RW5 and AI only, trained on the authors'
                    training gauges with their hyperparameters
  nearest_gauge   : the observed class of the nearest gauged catchment

Scores per season and stratum (relation to the training polygons, record
length, area). Writes results/phase3/us_scores.csv, us_predictions.csv and
us_simple.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb

from stormflow_diag import paths
from stormflow_diag.predict import CLASSES, SEASONS, predict, training_ids
from stormflow_diag.validate import confusion, scores

OUT = paths.RESULTS / "phase3"
LABELS = paths.RESULTS / "phase2" / "us_labels.csv"
RELATIONS = paths.RESULTS / "phase2" / "us_validation_relations.csv"
PARAMS = {"objective": "multi:softprob", "num_class": 3, "eta": 0.3, "max_depth": 8, "subsample": 0.6,
          "eval_metric": "mlogloss", "seed": 1}


def climate_only(season: str, target: pd.DataFrame) -> pd.Series:
    """RW5 + AI model, trained like the authors' (5-fold CV, early stopping 20, cap 100)."""
    g = pd.read_csv(paths.UPSTREAM / "data" / "Gauged_Catchments_Metadata_and_Attributes.csv").set_index("GCIN")
    g = g[g.index.isin(training_ids()[season]) & g[f"{season}_gauged_class"].notna()]
    cols = [f"RW5-{season}", "AI"]
    y = g[f"{season}_gauged_class"].map({c: i for i, c in enumerate(CLASSES)})
    X, Y = g[cols].to_numpy(float), y.to_numpy()
    # xgb.cv in xgboost 1.7 breaks under NumPy 2, so the 5-fold CV is done by hand
    from sklearn.model_selection import StratifiedKFold
    best = []
    for tr, va in StratifiedKFold(5, shuffle=True, random_state=1).split(X, Y):
        m = xgb.train(PARAMS, xgb.DMatrix(X[tr], label=Y[tr]), num_boost_round=100,
                      evals=[(xgb.DMatrix(X[va], label=Y[va]), "va")], early_stopping_rounds=20, verbose_eval=False)
        best.append(m.best_iteration + 1)
    model = xgb.train(PARAMS, xgb.DMatrix(X, label=Y), num_boost_round=int(np.mean(best)))
    p = model.predict(xgb.DMatrix(target[cols].to_numpy(float)))
    return pd.Series(np.array(CLASSES)[p.argmax(1)], index=target.index)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lab = pd.read_csv(LABELS)
    rel = pd.read_csv(RELATIONS).set_index("UCIN")
    ua = pd.read_csv(paths.UPSTREAM / "data" / "Ungauged_Catchments_Metadata_and_Attributes.csv").set_index("UCIN")
    ua = ua.loc[ua.index.isin(lab.UCIN)]

    rows, preds, simple = [], [], []
    for s in SEASONS:
        L = lab[(lab.season == s) & lab.label.notna()].set_index("UCIN")
        ours = predict(ua, s)
        same = (ours == ua[f"{s}_predicted_class"]).mean()
        print(f"[{s}] our application of the released model vs published predicted class: {same:.4f} identical")
        P = pd.DataFrame({
            "observed": L.label,
            "authors": ours.reindex(L.index),
            "always_complex": "complex",
            "climate_only": climate_only(s, ua.reindex(L.index)),
            "nearest_gauge": rel[f"nearest_{s}_gauged_class"].reindex(L.index),
        })
        P["relation"] = rel.relation.reindex(L.index)
        P["overlaps_gauged"] = P.relation.isin(["nested", "contains", "overlapping"])
        P["years"] = pd.cut(rel.n_years_ge_300_valid_days.reindex(L.index), [0, 20, 30, 100], labels=["10-20", "20-30", ">30"])
        P["area"] = pd.cut(rel.area_km2.reindex(L.index), [0, 100, 1000, 1e7], labels=["<100", "100-1000", ">1000"])
        P["r2_lin"] = L.r2_lin
        P["n_events"] = L.n_events if "n_events" in L else np.nan
        P["season"] = s
        preds.append(P.reset_index())

        strata = [("all", P.index == P.index)]
        strata += [(f"relation={r}", P.relation == r) for r in ["independent", "adjacent", "nested", "contains"]]
        strata += [("overlaps_gauged=no", ~P.overlaps_gauged), ("overlaps_gauged=yes", P.overlaps_gauged)]
        strata += [(f"years={y}", P.years == y) for y in P.years.cat.categories]
        strata += [(f"area={a}", P.area == a) for a in P.area.cat.categories]
        for name, m in strata:
            for model in ["authors", "always_complex", "climate_only", "nearest_gauge"]:
                ok = m & P[model].notna()
                if ok.sum() >= 10:
                    rows.append({"season": s, "stratum": name, "model": model, **scores(P.observed[ok], P[model][ok])})

        print(f"\n[{s}] n = {len(P)}; observed {P.observed.value_counts().to_dict()}")
        print(confusion(P.observed, P.authors))
        ps = P[P.authors == "simple"]
        simple.append({"season": s, "n_pred_simple": len(ps),
                       **{f"observed_{c}": int((ps.observed == c).sum()) for c in CLASSES},
                       "median_r2_lin": ps.r2_lin.median(), "share_r2_lin_ge_0.75": (ps.r2_lin >= 0.75).mean(),
                       "share_r2_lin_ge_0.6": (ps.r2_lin >= 0.6).mean()})

    sc = pd.DataFrame(rows)
    sc.to_csv(OUT / "us_scores.csv", index=False, float_format="%.4f")
    pd.concat(preds).to_csv(OUT / "us_predictions.csv", index=False)
    pd.DataFrame(simple).to_csv(OUT / "us_simple.csv", index=False, float_format="%.4f")
    cols = ["season", "stratum", "model", "n", "accuracy", "balanced_accuracy", "kappa",
            "precision_simple", "recall_simple", "precision_complex", "complex_vs_rest_balanced_accuracy"]
    print("\n", sc[sc.stratum == "all"][cols].round(3).to_string(index=False))
    print("\n", sc[(sc.model == "authors") & (sc.stratum != "all")][cols].round(3).to_string(index=False))
    print("\n", pd.DataFrame(simple).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
