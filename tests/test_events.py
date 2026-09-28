"""Tests for the DMCA-ESR port (stormflow_diag.stage1.events).

Fixtures (tests/fixtures/)
--------------------------
- dmca_example_27071.csv.gz: the example series shipped with the reference
  code (giuliagiani/DMCA-ESR @ b033330, daily_rainfall_27071.txt and
  daily_flow_27071.txt), values copied as text.
- octave_events.csv.gz, octave_summary.csv: output of the unmodified reference
  MATLAB code run in GNU Octave 10.3.0 (conda-forge) with the harness in
  fixtures/octave/. The shims add MATLAB's cumsum(...,'omitnan'), nansum and
  nanmin, which Octave lacks. Indices are converted to 0-based. Series
  "27071" follows example.m (inputs/24, rain_min 0.02, max_window 100,
  EVENT_ANALYSIS multiple 24); the gauge series follow the authors'
  convention (Event_Inputs/<GCIN>.csv, inputs/24, rain_min 0.05,
  max_window 16, multiple 24). ``sha_fluct_*`` hash the float64 bytes of
  fluct_rain_Tr and fluct_flow_Tr.

Tests that need the Figshare package skip when it is absent.
"""
import gzip
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stormflow_diag import paths
from stormflow_diag.stage1 import events as ev

FX = Path(__file__).parent / "fixtures"
KEYS = ["start_precip_date", "end_precip_date", "start_stormflow_date", "end_stormflow_date"]
IDX = ["rain_start", "rain_end", "flow_start", "flow_end"]

needs_inputs = pytest.mark.skipif(not paths.EVENT_INPUTS_ZIP.exists(),
                                  reason="Figshare Event_Inputs.zip not available")
needs_catalogue = pytest.mark.skipif(
    not all(p.exists() for p in paths.EVENTS.values()) or not paths.EVENT_INPUTS_ZIP.exists(),
    reason="Figshare event catalogue not available")


def _sha(a):
    return hashlib.sha256(np.ascontiguousarray(a, dtype="<f8").tobytes()).hexdigest()


@pytest.fixture(scope="module")
def example():
    with gzip.open(FX / "dmca_example_27071.csv.gz", "rt") as fh:
        df = pd.read_csv(fh, float_precision="round_trip", parse_dates=["date"])
    return df


@pytest.fixture(scope="module")
def octave():
    with gzip.open(FX / "octave_events.csv.gz", "rt") as fh:
        events = pd.read_csv(fh, float_precision="round_trip", dtype={"series": str})
    summary = pd.read_csv(FX / "octave_summary.csv", dtype={"series": str}).set_index("series")
    return events, summary


# ---------------------------------------------------------------------------
# example 27071 against GNU Octave running the reference code
# ---------------------------------------------------------------------------
def test_example_27071_matches_octave_bitwise(example, octave):
    events, summary = octave
    ref = events[events.series == "27071"].reset_index(drop=True)
    rain = example.rain_mmd.to_numpy() / 24
    flow = example.flow_mmd.to_numpy() / 24
    assert np.isnan(flow).sum() == 256  # the example contains streamflow gaps

    Tr, fr, ff, _ = ev.step1_step2_tr_and_fluctuations(rain, flow, 0.02, 100)
    assert Tr == summary.loc["27071", "Tr"] == 1
    assert _sha(fr) == summary.loc["27071", "sha_fluct_rain"]
    assert _sha(ff) == summary.loc["27071", "sha_fluct_flow"]

    out = ev.dmca_esr(rain, flow, 0.02, 100, multiple=24)
    assert len(out) == len(ref) == 449
    np.testing.assert_array_equal(out[IDX].to_numpy(), ref[IDX].to_numpy())
    np.testing.assert_array_equal(out.duration_rain, ref.duration_rain)
    np.testing.assert_array_equal(out.duration_flow, ref.duration_flow)
    np.testing.assert_array_equal(out.volume_rain, ref.volume_rain)
    np.testing.assert_array_equal(out.volume_flow, ref.volume_flow)
    np.testing.assert_array_equal(out.runoff_ratio, ref.runoff_ratio)


def test_example_27071_dates(example):
    out = ev.dmca_esr(example.rain_mmd / 24, example.flow_mmd / 24, 0.02, 100,
                      dates=example.date)
    first = out.iloc[0]
    assert first.rain_start_date == example.date[first.rain_start]
    assert (out.flow_start_date >= out.rain_start_date).all()
    assert (out.flow_end_date >= out.rain_end_date).all()


# ---------------------------------------------------------------------------
# authors' gauges against GNU Octave running the reference code
# ---------------------------------------------------------------------------
@needs_inputs
@pytest.mark.parametrize("gcin", [2, 11, 1000, 2660, 4000])
def test_gauge_matches_octave_bitwise(gcin, octave):
    events, summary = octave
    ref = events[events.series == str(gcin)].reset_index(drop=True)
    d = ev.load_event_inputs(gcin)
    rain = d.precipitation_mmd.to_numpy() / 24
    flow = d.streamflow_mmd.to_numpy() / 24

    Tr, fr, ff, _ = ev.step1_step2_tr_and_fluctuations(rain, flow, 0.05, 16)
    assert Tr == summary.loc[str(gcin), "Tr"]
    assert _sha(fr) == summary.loc[str(gcin), "sha_fluct_rain"]
    assert _sha(ff) == summary.loc[str(gcin), "sha_fluct_flow"]

    out = ev.dmca_esr(rain, flow, 0.05, 16, multiple=24)
    np.testing.assert_array_equal(out[IDX].to_numpy(), ref[IDX].to_numpy())
    np.testing.assert_array_equal(out.volume_rain, ref.volume_rain)
    np.testing.assert_array_equal(out.volume_flow, ref.volume_flow)


# ---------------------------------------------------------------------------
# authors' catalogue
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def catalogue():
    return ev.load_catalogue([1, 100, 1411, 2660, 2674, 2686, 3719])


@needs_catalogue
@pytest.mark.parametrize("gcin", [
    1,     # AR, long NaN tail after 1968
    100,   # AU, NaN head and interior gaps; trimming the tails loses an event
    1411,  # zero-stormflow events kept only through floating-point residues
    2674,  # rain == 1.2 mm/day: needs rain_min = 0.05, not 1.2/24
    2686,  # CAMELS-GB, 46 rain fluctuations exactly on the tolerance
    3719,  # residue 4e-20 mm that pandas' default CSV parser loses
])
def test_detect_gauge_events_reproduces_catalogue(gcin, catalogue):
    theirs = catalogue[catalogue.GCIN == gcin]
    ours = ev.detect_gauge_events(gcin, min_events=0)
    merged = ours.merge(theirs, on=KEYS, how="outer", suffixes=("", "_t"), indicator=True)
    assert (merged["_merge"] == "both").all(), merged[merged["_merge"] != "both"][KEYS + ["_merge"]]
    assert len(merged) == len(theirs)
    np.testing.assert_allclose(merged.volume_precip_mm, merged.volume_precip_mm_t, rtol=1e-13)
    np.testing.assert_allclose(merged.volume_stormflow_mm, merged.volume_stormflow_mm_t,
                               rtol=1e-9, atol=1e-18)
    assert (merged.duration_precip == merged.duration_precip_t).all()
    assert (merged.duration_stormflow == merged.duration_stormflow_t).all()
    assert (merged.missed_streamflow == 0).all()
    source = pd.read_csv(paths.GAUGED_ATTRS, index_col="GCIN").loc[gcin, "Source ID"]
    if source.startswith("WRR_"):
        # the catalogue's phenology for WRR_* gauges is not the released CSV
        assert not np.allclose(merged.growing_dormancy_prob, merged.growing_dormancy_prob_t)
    else:
        np.testing.assert_allclose(merged.growing_dormancy_prob, merged.growing_dormancy_prob_t,
                                   atol=1e-12)
        assert (merged.season == merged.season_t).all()


@needs_catalogue
@pytest.mark.xfail(strict=True, reason="MATLAB movmean rounds differently at exact "
                   "tolerance ties (CAMELS-GB); 24 of 4,552 gauges differ by 1-4 events")
def test_known_tie_mismatch_gcin_2660(catalogue):
    theirs = catalogue[catalogue.GCIN == 2660]
    ours = ev.detect_gauge_events(2660, min_events=0)
    assert set(map(tuple, ours[KEYS].astype(str).to_numpy())) == \
        set(map(tuple, theirs[KEYS].astype(str).to_numpy()))


@needs_inputs
def test_min_events_rule_drops_small_seasons():
    ours = ev.detect_gauge_events(2, min_events=0)
    counts = ours.season.value_counts()
    kept = ev.detect_gauge_events(2)
    assert set(kept.season) == set(counts[counts >= ev.MIN_EVENTS_PER_SEASON].index)


# ---------------------------------------------------------------------------
# unit tests of MATLAB semantics
# ---------------------------------------------------------------------------
def test_movmean_shrink_endpoints():
    x = np.array([1.0, 2.0, 4.0, 8.0, 16.0])
    np.testing.assert_allclose(ev._movmean(x, 3), [1.5, 7 / 3, 14 / 3, 28 / 3, 12.0])
    np.testing.assert_allclose(ev._movmean(x, 5), [7 / 3, 15 / 4, 31 / 5, 30 / 4, 28 / 3])


def test_step3_needs_two_zero_steps_to_end_a_core():
    fb = np.array([0, 0, 1, -1, 0, 2, 0, 0, 0, 3, 3, 0, 0, 0], dtype=float)
    bc, ec = ev.step3_core_identification(fb)
    # a single zero (index 4) does not end the core; two zeros (6, 7) do
    np.testing.assert_array_equal(bc, [2, 9])
    np.testing.assert_array_equal(ec, [5, 10])


def test_step10_groups_runs_of_overlapping_events():
    br = np.array([0, 10, 12, 14, 30], dtype=float)
    er = np.array([2, 13, 15, 16, 32], dtype=float)  # 1 overlaps 2, 2 overlaps 3
    bf = np.array([1, 11, 13, 15, 31], dtype=float)
    ef = np.array([5, 12, 14, 20, 35], dtype=float)
    out = ev.step10_checks_on_overlapping_events(br, er, bf, ef)
    np.testing.assert_array_equal(out[0], [0, 10, 30])
    np.testing.assert_array_equal(out[1], [2, 16, 32])
    np.testing.assert_array_equal(out[2], [1, 11, 31])
    np.testing.assert_array_equal(out[3], [5, 20, 35])


def test_baseflow_curve_matlab_quirks():
    flow = np.array([1.0, 3.0, 2.0, 1.0, 5.0, 4.0, 2.0, 2.0, 9.0, 2.0])
    bfl = ev.baseflow_curve(np.array([0, 6]), np.array([3, 9]), flow)
    # event 1: equal end values -> no line is drawn, baseflow = flow
    np.testing.assert_array_equal(bfl[:4], flow[:4])
    # inter-event stretch 3 -> 6 is joined too (line from 1 to 2, clipped by flow)
    np.testing.assert_allclose(bfl[4:6], [4 / 3, 5 / 3])
    # event 2: 2 -> 2 again equal, so baseflow = flow and stormflow is zero
    np.testing.assert_array_equal(bfl[6:], flow[6:])
    stats = ev.event_analysis(np.array([0, 6]), np.array([2, 8]), np.array([0, 6]),
                              np.array([3, 9]), flow, flow)
    np.testing.assert_array_equal(stats["volume_runoff"], [0.0, 0.0])


def test_baseflow_curve_mostly_nan_segment():
    flow = np.full(21, np.nan)
    flow[0], flow[20] = 1.0, 3.0  # 19 of 21 NaN (>= 90 %)
    bfl = ev.baseflow_curve(np.array([0]), np.array([20]), flow)
    assert np.isnan(bfl).all()  # whole segment set to NaN, endpoints included
    flow[1] = 2.0  # 18 of 21 NaN (< 90 %): a line is drawn between the endpoints
    bfl = ev.baseflow_curve(np.array([0]), np.array([20]), flow)
    assert bfl[0] == 1.0 and bfl[1] == 1.1 and bfl[20] == 3.0


def test_season_probability_counts_each_month_once():
    monthly = np.arange(1, 13, dtype=float)  # Jan=1 ... Dec=12
    start = pd.to_datetime(["2000-11-23", "2000-11-05", "2000-12-25", "1992-08-24"])
    end = pd.to_datetime(["2000-12-01", "2000-11-10", "2001-01-05", "1992-10-12"])
    np.testing.assert_allclose(ev.season_probability(start, end, monthly),
                               [11.5, 11.0, 6.5, 9.0])
