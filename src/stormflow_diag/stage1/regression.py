"""Rainfall-runoff regression and functional labelling of gauged catchments.

The fits run in R (`segfit.R`, package `segmented` by Muggeo, whom the paper
cites for the score test) through rpy2. The labelling rule is applied here so
that alternative rules can be compared on the same fits.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

SEGFIT_R = Path(__file__).with_name("segfit.R")

SIMPLE_R2 = 0.75
INTERMEDIATE_LIN_R2 = 0.50
SEGMENTED_R2 = 0.75

_r_fit = None


def _r():
    """Load segfit.R once per process and return the R function."""
    global _r_fit
    if _r_fit is None:
        import rpy2.robjects as ro

        ro.r["source"](str(SEGFIT_R))
        _r_fit = ro.globalenv["fit_catchment"]
    return _r_fit


def fit_catchment(rain: np.ndarray, stormflow: np.ndarray, alpha: float = 0.05, seed: int = 1) -> dict:
    """Linear and segmented fits of event stormflow volume on event rainfall volume."""
    import rpy2.robjects as ro

    res = _r()(ro.FloatVector(rain), ro.FloatVector(stormflow), alpha=alpha, seed=seed)
    return {k: (np.nan if v[0] is ro.NA_Real else v[0]) for k, v in zip(res.names, res)}


def label(r2_lin: float, r2_seg: float) -> str:
    """Methods rule: simple, intermediate (linear or threshold-like), else complex."""
    if r2_lin >= SIMPLE_R2:
        return "simple"
    if r2_lin >= INTERMEDIATE_LIN_R2:
        return "intermediate"
    if not np.isnan(r2_seg) and r2_seg >= SEGMENTED_R2:
        return "intermediate"
    return "complex"


def label_variants(fit: dict) -> dict:
    """Labels under the readings of the Methods that the text leaves open.

    seq     : sequential score tests at alpha, segmented R2 of the selected model
    selg    : segmented::selgmented(type = "score"), Muggeo's own selector
    any_seg : best of the 1- and 2-breakpoint fits, ignoring significance
    """
    r2_seq = {0: fit["r2_lin"], 1: fit["r2_seg1"], 2: fit["r2_seg2"]}[int(fit["k_seq"])]
    r2_any = np.nanmax([fit["r2_lin"], fit["r2_seg1"], fit["r2_seg2"]])
    return {
        "label_seq": label(fit["r2_lin"], r2_seq),
        "label_selg": label(fit["r2_lin"], fit["r2_selgmented"]),
        "label_any_seg": label(fit["r2_lin"], r2_any),
    }


def _fit_group(args):
    key, rain, stormflow, alpha, seed = args
    fit = fit_catchment(rain, stormflow, alpha=alpha, seed=seed)
    return {**key, **fit, **label_variants(fit)}


def fit_catalogue(
    events: pd.DataFrame,
    by: list[str],
    rain_col: str = "volume_precip_mm",
    flow_col: str = "volume_stormflow_mm",
    min_events: int = 15,
    alpha: float = 0.05,
    seed: int = 1,
    workers: int | None = None,
) -> pd.DataFrame:
    """Fit and label every group (e.g. GCIN x season) of an event catalogue in parallel."""
    tasks = []
    for key, g in events.groupby(by, sort=True):
        if len(g) < min_events:
            continue
        key = dict(zip(by, key if isinstance(key, tuple) else (key,)))
        tasks.append((key, g[rain_col].to_numpy(float), g[flow_col].to_numpy(float), alpha, seed))

    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    import multiprocessing as mp

    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        rows = list(ex.map(_fit_group, tasks, chunksize=16))
    return pd.DataFrame(rows)
