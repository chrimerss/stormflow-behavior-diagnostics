"""Scoring predicted against observed functional classes."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score, confusion_matrix

CLASSES = ["simple", "intermediate", "complex"]


def confusion(obs: pd.Series, pred: pd.Series) -> pd.DataFrame:
    """Rows observed, columns predicted."""
    m = confusion_matrix(obs, pred, labels=CLASSES)
    return pd.DataFrame(m, index=pd.Index(CLASSES, name="observed"), columns=pd.Index(CLASSES, name="predicted"))


def scores(obs: pd.Series, pred: pd.Series) -> dict:
    ok = obs.notna() & pred.notna()
    obs, pred = obs[ok], pred[ok]
    out = {
        "n": int(ok.sum()),
        "accuracy": float((obs == pred).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(obs, pred)),
        "kappa": float(cohen_kappa_score(obs, pred, labels=CLASSES)),
    }
    for c in CLASSES:
        tp = int(((pred == c) & (obs == c)).sum())
        out[f"n_obs_{c}"] = int((obs == c).sum())
        out[f"n_pred_{c}"] = int((pred == c).sum())
        out[f"precision_{c}"] = tp / out[f"n_pred_{c}"] if out[f"n_pred_{c}"] else np.nan
        out[f"recall_{c}"] = tp / out[f"n_obs_{c}"] if out[f"n_obs_{c}"] else np.nan
    oc, pc = obs == "complex", pred == "complex"
    out["complex_vs_rest_accuracy"] = float((oc == pc).mean())
    out["complex_vs_rest_balanced_accuracy"] = float(balanced_accuracy_score(oc, pc))
    return out
