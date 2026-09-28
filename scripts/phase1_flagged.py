"""Phase 1: the 246 boundary-flagged gauges as a free out-of-sample test.

The authors labelled these gauges but excluded them from training and from the
paper because their catchment boundaries were flagged. They were never seen by
the models, so their observed labels test the released classifiers.

Steps
  1. Reproduce the authors' own predicted classes for the 4,306 unflagged gauges
     (sanity check of our feature construction).
  2. Score the models on the authors' held-out test set (their reported setting).
  3. Score the models on the 246 flagged gauges, against two baselines:
     "always complex" and the majority class of the training set.

Writes results/phase1/flagged_predictions.csv and results/phase1/flagged_scores.csv
"""
from __future__ import annotations

import pandas as pd

from stormflow_diag import paths
from stormflow_diag.predict import SEASONS, gauged_attributes, predict, predict_proba, training_ids
from stormflow_diag.validate import confusion, scores

OUT = paths.RESULTS / "phase1"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    a = gauged_attributes()
    train = training_ids()
    flagged = a.Catchment_Boundary_Flagged.astype(bool)

    rows, preds = [], []
    for s in SEASONS:
        pred = predict(a, s)
        proba = predict_proba(a, s)
        obs = a[f"{s}_gauged_class"]

        theirs = a[f"{s}_predicted_class"]
        same = (pred[~flagged] == theirs[~flagged]).mean()
        print(f"[{s}] our predictions vs authors' predicted class (unflagged, n={(~flagged).sum()}): {same:.4f} identical")

        in_train = a.index.isin(train[s])
        test = ~flagged & ~in_train & obs.notna()
        print(f"[{s}] flagged gauges in training set: {(flagged & in_train).sum()}")

        sets = {"authors_test": test, "flagged": flagged & obs.notna()}
        for name, m in sets.items():
            r = {"season": s, "set": name, "model": "xgboost", **scores(obs[m], pred[m])}
            rows.append(r)
            base = pd.Series("complex", index=obs[m].index)
            rows.append({"season": s, "set": name, "model": "always_complex", **scores(obs[m], base)})
            print(f"\n[{s}] {name}: n={r['n']}  acc={r['accuracy']:.3f}  bal_acc={r['balanced_accuracy']:.3f}  "
                  f"kappa={r['kappa']:.3f}  simple P/R={r['precision_simple']:.2f}/{r['recall_simple']:.2f}")
            print(confusion(obs[m], pred[m]))

        preds.append(pd.DataFrame({
            "GCIN": a.index, "season": s, "flagged": flagged.values, "in_training": in_train,
            "observed": obs.values, "predicted": pred.values, "authors_predicted": theirs.values,
            **{c: proba[c].values for c in proba.columns},
            "country": a.country.values,
        }))

    pd.concat(preds).to_csv(OUT / "flagged_predictions.csv", index=False)
    sc = pd.DataFrame(rows)
    sc.to_csv(OUT / "flagged_scores.csv", index=False)
    cols = ["season", "set", "model", "n", "accuracy", "balanced_accuracy", "kappa",
            "precision_simple", "recall_simple", "precision_intermediate", "recall_intermediate",
            "precision_complex", "recall_complex"]
    print("\n", sc[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
