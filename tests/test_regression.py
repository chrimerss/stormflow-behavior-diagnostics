import numpy as np
import pytest

from stormflow_diag.stage1.regression import fit_catchment, label, label_variants


@pytest.mark.parametrize(
    "r2_lin, r2_seg, expected",
    [
        (0.80, np.nan, "simple"),
        (0.75, 0.95, "simple"),  # linear rule wins even when a breakpoint fits better
        (0.60, np.nan, "intermediate"),
        (0.30, 0.80, "intermediate"),
        (0.30, 0.74, "complex"),
        (0.49, np.nan, "complex"),
    ],
)
def test_label_rule(r2_lin, r2_seg, expected):
    assert label(r2_lin, r2_seg) == expected


def test_threshold_response_is_intermediate():
    rng = np.random.default_rng(0)
    rain = rng.uniform(5, 120, 150)
    flow = np.maximum(0, rain - 90) * 0.9 + rng.normal(0, 1.0, rain.size)
    fit = fit_catchment(rain, flow)
    assert fit["r2_lin"] < 0.75
    assert fit["k_seq"] >= 1
    assert fit["psi1_seg1"] == pytest.approx(90, abs=5)
    assert label_variants(fit)["label_seq"] == "intermediate"


def test_noise_is_complex():
    rng = np.random.default_rng(1)
    rain = rng.uniform(5, 120, 150)
    flow = rng.gamma(1.0, 2.0, rain.size)
    fit = fit_catchment(rain, flow)
    assert label_variants(fit)["label_seq"] == "complex"
