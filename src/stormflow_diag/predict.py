"""Apply the authors' released XGBoost classifiers.

Feature construction mirrors the setup chunk of
upstream/code/Reproducing_XGBoost_Models_Results.Rmd: season-specific RW1,
RW2.5, RW5 and CTIW columns are selected for the season, and the 27 features
are passed in the notebook's `select()` order (the saved models carry no
feature names, so order is all that ties columns to trees).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb

from stormflow_diag import paths

CLASSES = ["simple", "intermediate", "complex"]  # R ordered factor levels, 0-based in the model
SEASONS = ["dormant", "growing"]

# (feature name in the notebook, column in upstream CSV; "{s}" = season)
FEATURES = [
    ("AI", "AI"),
    ("RW1", "RW1-{s}"),
    ("RW2.5", "RW2.5-{s}"),
    ("RW5", "RW5-{s}"),
    ("Area", "Area"),
    ("Async Index", "Async Index"),
    ("Slope/AI", "Slope/AI"),
    ("CTI", "Async Index x Slope/AI"),
    ("CTIW", "RW1 x Async Index x Slope/AI-{s}"),
    ("(P-AET) x Slope", "(P-AET) x Slope"),
    ("Median DepthToBedrock", "Median DepthToBedrock"),
    ("Median TWI", "Median TWI"),
    ("First Geo Dominant Class", "First Geo Dominant Class"),
    ("Second Geo Dominant Class", "Second Geo Dominant Class"),
    ("Frequency Not Level", "Frequency Not Level"),
    ("G Shape Elevation", "G Shape Elevation"),
    ("G Shape Slope", "G Shape Slope"),
    ("G Shape TWI", "G Shape TWI"),
    ("G Shape TRI", "G Shape TRI"),
    ("G Scale Elevation", "G Scale Elevation"),
    ("G Scale Slope", "G Scale Slope"),
    ("G Scale TWI", "G Scale TWI"),
    ("G Scale TRI", "G Scale TRI"),
    ("Urban", "Urban"),
    ("Forest", "Forest"),
    ("Cropland", "Cropland"),
    ("Bare", "Bare"),
]


def load_model(season: str) -> xgb.Booster:
    booster = xgb.Booster()
    booster.load_model(str(paths.UPSTREAM / "code" / "models" / f"{season}_model.json"))
    return booster


def feature_matrix(attrs: pd.DataFrame, season: str) -> pd.DataFrame:
    """27-column feature matrix for one season, in the order the model expects."""
    return pd.DataFrame({name: attrs[col.format(s=season)].to_numpy(float) for name, col in FEATURES}, index=attrs.index)


def predict_proba(attrs: pd.DataFrame, season: str, model: xgb.Booster | None = None) -> pd.DataFrame:
    model = model or load_model(season)
    X = feature_matrix(attrs, season)
    p = model.predict(xgb.DMatrix(X.to_numpy(), missing=np.nan))
    return pd.DataFrame(p, columns=[f"p_{c}" for c in CLASSES], index=attrs.index)


def predict(attrs: pd.DataFrame, season: str, model: xgb.Booster | None = None) -> pd.Series:
    p = predict_proba(attrs, season, model)
    return pd.Series(np.array(CLASSES)[p.to_numpy().argmax(axis=1)], index=attrs.index, name=f"{season}_pred")


def gauged_attributes() -> pd.DataFrame:
    """Upstream gauged attribute table (includes the derived Slope/AI and CTI columns)."""
    return pd.read_csv(paths.UPSTREAM / "data" / "Gauged_Catchments_Metadata_and_Attributes.csv").set_index("GCIN")


def training_ids() -> dict[str, set[int]]:
    import pyreadr

    r = pyreadr.read_r(str(paths.UPSTREAM / "data" / "Training_IDs.RData"))
    return {s: set(r[f"training_ids_{s}"].iloc[:, 0].astype(int)) for s in SEASONS}
