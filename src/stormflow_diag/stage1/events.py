"""DMCA-ESR rainfall-runoff event separation, ported from MATLAB.

Giani, G., Rico-Ramirez, M. A. & Woods, R. A. (2022). A practical, objective,
and robust technique to directly estimate catchment response time. Water
Resources Research. Reference code: https://github.com/giuliagiani/DMCA-ESR
(EVENT_IDENTIFICATION_DMCA.m, STEP1..STEP10, BASEFLOW_CURVE.m, EVENT_ANALYSIS.m).

Index convention
----------------
Every index in this module is a 0-based position in the input arrays. The
MATLAB code is 1-based, so each place where an index enters a comparison with
an array length, or is used to build a range, carries a ``# MATLAB:`` comment
with the original expression. Comparisons between two indices (e.g.
``end_rain < beginning_core``) are unchanged by the shift. MATLAB ranges
``a:b`` are inclusive, so they become ``a:b + 1`` here.

Delimiter vectors that MATLAB fills with NaN (STEP6 onward) are kept as float
arrays with NaN, so NaN comparisons behave as in MATLAB (always false).

Floating point
--------------
``movmean`` sums each window left to right and divides by its length, and
``nansum`` sums left to right, as GNU Octave does; the port matches Octave
10.3 running the reference code bit for bit (fluctuations, Tr, events,
baseflow, volumes). MATLAB's ``movmean`` rounds differently in the last bit.
That matters only where a rain fluctuation lies exactly on the tolerance,
``|r(i) - r(i+1)| == R_min`` for Tr = 1, which happens with 2-decimal rainfall
(CAMELS-GB). Against the authors' catalogue this leaves 22 missing and 26
extra events out of 2,030,569, all at 24 CAMELS-GB gauges. Summing right to
left, or running sums, fit worse.

Gauge-level conventions (``detect_gauge_events``) were inferred from the
authors' catalogue and are documented there.
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd

from stormflow_diag import paths

R_MIN = 1.2  # mm/day, Ameli et al. (2026) Methods
L_MAX = 16  # days, maximum window tested for Tr (MATLAB ``max_window``)
MULTIPLE = 24  # example.m: series divided by 24 (mm/h) before DMCA-ESR, volumes x24
MAX_DURATION = 15  # days, inclusive count
MIN_DURATION_PRECIP = 2  # days, inclusive count ("shorter than 1 day" = end == start)
MIN_EVENTS_PER_SEASON = 15
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CATALOGUE_COLUMNS = [
    "GCIN",
    "Catchment_Boundary_Flagged",
    "id",
    "start_precip_date",
    "end_precip_date",
    "duration_precip",
    "start_stormflow_date",
    "end_stormflow_date",
    "duration_stormflow",
    "volume_precip_mm",
    "volume_stormflow_mm",
    "runoff_ratio",
    "missed_streamflow",
    "growing_dormancy_prob",
]


# ---------------------------------------------------------------------------
# numerical helpers
# ---------------------------------------------------------------------------
def _seq_sum(x: np.ndarray) -> float:
    """Left-to-right sum ignoring NaN (MATLAB ``nansum`` on a vector)."""
    x = x[~np.isnan(x)]
    return float(np.cumsum(x)[-1]) if x.size else 0.0


def _movmean(x: np.ndarray, window: int) -> np.ndarray:
    """MATLAB ``movmean(x, window)`` for odd ``window``, default 'shrink' endpoints.

    Each output is x[i-h .. i+h] (clipped to the array) summed left to right
    from 0, divided by the element count: Octave's ``movfun(@mean)``.
    """
    n = x.size
    h = (window - 1) // 2
    acc = np.zeros(n)
    cnt = np.zeros(n)
    pos = np.arange(n)
    for off in range(-h, h + 1):
        src = pos + off
        ok = (src >= 0) & (src < n)
        acc[ok] = acc[ok] + x[src[ok]]
        cnt[ok] += 1
    return acc / cnt


def _two_zeros(fluct: np.ndarray, a: int, b: int) -> bool:
    """MATLAB ``sum(fluct(a:b)==0)==2`` for a two-element range (0-based a, b)."""
    return int(np.sum(fluct[a : b + 1] == 0)) == 2


# ---------------------------------------------------------------------------
# STEP1-STEP10 (one function per MATLAB file)
# ---------------------------------------------------------------------------
def step1_step2_tr_and_fluctuations(rain, flow, rain_min, max_window):
    """STEP1_STEP2_Tr_and_fluctuations_timeseries.m

    Returns (Tr, fluct_rain_Tr, fluct_flow_Tr, fluct_bivariate_Tr). ``Tr`` is a
    count of time steps (the half window), not an index, so it keeps its
    MATLAB value.
    """
    rain = np.asarray(rain, dtype=float)
    flow = np.asarray(flow, dtype=float)
    rain_int = np.nancumsum(rain)  # MATLAB: cumsum(rain, 'omitnan')
    flow_int = np.nancumsum(flow)
    T = rain.size

    windows = list(range(3, max_window + 1, 2))  # MATLAB: window=3:2:max_window
    fluct_rain = np.empty((len(windows), T))
    fluct_flow = np.empty((len(windows), T))
    rho = np.empty(len(windows))
    for j, window in enumerate(windows):  # MATLAB row (window-1)/2 is j+1
        fluct_rain[j] = rain_int - _movmean(rain_int, window)
        fluct_flow[j] = flow_int - _movmean(flow_int, window)
        # MATLAB: columns window-0.5*(window-1) : T-0.5*(window-1), i.e. h+1..T-h
        # 1-based inclusive with h=(window-1)/2 -> 0-based slice [h, T-h).
        h = (window - 1) // 2
        fr = fluct_rain[j, h : T - h]
        ff = fluct_flow[j, h : T - h]
        norm = 1 / (T - window + 1)
        F_rain = norm * _seq_sum(fr**2)
        F_flow = norm * _seq_sum(ff**2)
        F_rain_flow = norm * _seq_sum(fr * ff)
        with np.errstate(divide="ignore", invalid="ignore"):  # MATLAB: 0/0 -> NaN silently
            rho[j] = F_rain_flow / (np.sqrt(F_rain) * np.sqrt(F_flow))

    if np.all(np.isnan(rho)):
        raise ValueError("DMCA correlation is NaN for every window (constant rain or flow?)")
    # MATLAB: position_minimum=find(rho==nanmin(rho)); Tr=position_minimum (1-based)
    j_min = int(np.flatnonzero(rho == np.nanmin(rho))[0])
    Tr = j_min + 1

    tol_fluct_rain = (rain_min / (2 * Tr + 1)) * (((2 * Tr + 1) - 1) / 2)
    tol_fluct_flow = flow_int[-1] / 1e15
    fluct_rain_Tr = fluct_rain[j_min].copy()
    fluct_flow_Tr = fluct_flow[j_min].copy()
    fluct_rain_Tr[np.abs(fluct_rain_Tr) < tol_fluct_rain] = 0
    fluct_flow_Tr[np.abs(fluct_flow_Tr) < tol_fluct_flow] = 0
    fluct_bivariate_Tr = fluct_rain_Tr * fluct_flow_Tr
    return Tr, fluct_rain_Tr, fluct_flow_Tr, fluct_bivariate_Tr


def step3_core_identification(fluct_bivariate_Tr):
    """STEP3_core_identification.m -> (beginning_core, end_core), 0-based."""
    fb = np.asarray(fluct_bivariate_Tr, dtype=float)
    N = fb.size
    beginning_core, end_core = [], []
    q = 0  # MATLAB: q=1
    while q + 2 <= N:  # MATLAB: while q+1<=length(fb)
        if abs(fb[q]) > 0:
            beginning_core.append(q)
            # MATLAB: while q+1<length(fb) && sum(abs(fb(q:q+1)))>0
            while q + 2 < N and np.abs(fb[q]) + np.abs(fb[q + 1]) > 0:
                q += 1
                if q + 1 >= N:  # MATLAB: if q>=length(fb)
                    break
            end_core.append(q - 1)
        q += 1
    return np.array(beginning_core, dtype=int), np.array(end_core, dtype=int)


def step4_end_rain_events(beginning_core, end_core, rain, fluct_rain_Tr, rain_min):
    """STEP4_end_rain_events.m -> end_rain (0-based)."""
    N = rain.size
    bc = np.asarray(beginning_core, dtype=float)
    end_rain = np.empty(len(end_core), dtype=float)
    for g in range(len(end_core)):
        er = int(end_core[g])  # preliminary guess
        ec = int(end_core[g])
        # MATLAB: end_core(g)+2<length(rain) & sum(fluct_rain_Tr(end_core(g)+1:end_core(g)+2)==0)==2
        if ec + 3 < N and _two_zeros(fluct_rain_Tr, ec + 1, ec + 2):
            if rain[er] == 0:  # case 1: move backward to non-zero rain
                while er > 0 and rain[er] == 0:  # MATLAB: end_rain(g)-1>0
                    er -= 1
            else:  # case 2: move forward until rain <= rain_min
                nxt = np.flatnonzero(~np.isnan(bc[g + 1 :]))
                if nxt.size:
                    bound = bc[g + 1 + nxt[0]]
                    # MATLAB: end_rain(g)+1<length(rain)
                    while er + 2 < N and rain[er] > rain_min and er < bound:
                        er += 1
                    er -= 1
                else:  # "last" event
                    while er + 2 < N and rain[er] > rain_min:
                        er += 1
                    er -= 1
        else:  # case 3: core ends because flow fluctuations are zero
            while er > 0 and rain[er] > rain_min and er >= bc[g]:
                er -= 1
            while er > 0 and rain[er] < rain_min and er >= bc[g]:
                er -= 1
        end_rain[g] = er
    return end_rain


def step5_beginning_rain_events(beginning_core, end_rain, rain, fluct_rain_Tr, rain_min):
    """STEP5_beginning_rain_events.m -> beginning_rain (0-based)."""
    N = rain.size
    end_rain = np.asarray(end_rain, dtype=float)
    beginning_rain = np.empty(len(beginning_core), dtype=float)

    def move_back(br, g):
        # shared by case 2 and case 3: move backward while rain > rain_min,
        # bounded by the end of the previous rain event, then step forward one.
        prev = np.flatnonzero(~np.isnan(end_rain[:g]))  # MATLAB: end_rain(1:g-1)
        if prev.size:
            bound = end_rain[prev[-1]]
            while br > 0 and rain[br] > rain_min and br > bound:  # MATLAB: beginning_rain(g)-1>0
                br -= 1
        else:  # "first" event
            while br > 0 and rain[br] > rain_min:
                br -= 1
        return br + 1

    for g in range(len(beginning_core)):
        bc = int(beginning_core[g])
        br = bc  # preliminary guess
        # MATLAB: beginning_core(g)>2 & sum(fluct_rain_Tr(beginning_core(g)-2:beginning_core(g)-1)==0)==2
        if bc > 1 and _two_zeros(fluct_rain_Tr, bc - 2, bc - 1):
            if rain[bc] == 0:  # case 1: move forward to non-zero rain
                while br + 2 < N and rain[br] == 0:  # MATLAB: beginning_rain(g)+1<length(rain)
                    br += 1
            else:  # case 2
                br = move_back(br, g)
        else:  # case 3: flow fluctuations are zero before the core
            br = move_back(br, g)
        beginning_rain[g] = br
    return beginning_rain


def step6_checks_on_rain_events(beginning_rain, end_rain, rain, rain_min):
    """STEP6_checks_on_rain_events.m -> (beginning_rain_checked, end_rain_checked)."""
    brc = np.array(beginning_rain, dtype=float)
    erc = np.array(end_rain, dtype=float)
    for g in range(brc.size):
        br, er = int(beginning_rain[g]), int(end_rain[g])
        # MATLAB: rain(beginning_rain(g)-1)>rain_min | rain(end_rain(g)+1)>rain_min
        if br > er or rain[br - 1] > rain_min or rain[er + 1] > rain_min:
            brc[g] = np.nan
            erc[g] = np.nan
    return brc, erc


def step7_end_flow_events(beginning_rain_checked, end_rain_checked, beginning_core,
                          end_core, flow, fluct_rain_Tr, fluct_flow_Tr, Tr):
    """STEP7_end_flow_events.m -> end_flow (0-based, NaN where no valid rain event)."""
    N = flow.size
    brc = np.asarray(beginning_rain_checked, dtype=float)
    erc = np.asarray(end_rain_checked, dtype=float)
    ffl = fluct_flow_Tr
    end_flow = np.full(erc.size, np.nan)
    for g in range(erc.size):
        if np.isnan(erc[g]) or np.isnan(brc[g]):
            continue
        ec = int(end_core[g])
        # MATLAB: end_core(g)+2<length(flow) & sum(fluct_rain_Tr(end_core(g)+1:end_core(g)+2)==0)==2
        if ec + 3 < N and _two_zeros(fluct_rain_Tr, ec + 1, ec + 2):
            ef = int(erc[g])  # case 1: start from end of rain
            nxt = np.flatnonzero(~np.isnan(brc[g + 1 :]))
            if nxt.size:
                bound = brc[g + 1 + nxt[0]] + Tr
                # MATLAB: end_flow(g)+1<length(flow)
                while ef + 2 < N and ffl[ef] <= 0 and ef < bound:
                    ef += 1
                while ef + 2 < N and ffl[ef] > 0 and ef < bound:
                    ef += 1
                ef -= 1
            else:  # "last" event
                while ef + 2 < N and ffl[ef] <= 0:
                    ef += 1
                while ef + 2 < N and ffl[ef] > 0:
                    ef += 1
                ef -= 1
        else:  # case 2: core ends because flow fluctuations are zero
            ef = ec
            while ef > beginning_core[g] and ffl[ef] <= 0:
                ef -= 1
        end_flow[g] = ef
    return end_flow


def step8_beginning_flow_events(beginning_rain_checked, end_rain_checked, end_flow,
                                beginning_core, fluct_rain_Tr, fluct_flow_Tr):
    """STEP8_beginning_flow_events.m -> beginning_flow (0-based, NaN where invalid).

    MATLAB also writes ``end_flow(g)=NaN`` here, but only to its local copy,
    so it has no effect on the caller; it is not reproduced.
    """
    brc = np.asarray(beginning_rain_checked, dtype=float)
    erc = np.asarray(end_rain_checked, dtype=float)
    ffl = fluct_flow_Tr
    beginning_flow = np.full(brc.size, np.nan)
    for g in range(brc.size):
        if np.isnan(brc[g]) or np.isnan(erc[g]):
            continue
        bc = int(beginning_core[g])
        ef = end_flow[g]
        # MATLAB: beginning_core(g)>2 & sum(fluct_rain_Tr(beginning_core(g)-2:beginning_core(g)-1)==0)==2
        if bc > 1 and _two_zeros(fluct_rain_Tr, bc - 2, bc - 1):
            bf = int(brc[g])  # case 1
            while ffl[bf] > 0 and bf < ef:
                bf += 1
        else:  # case 2
            bf = bc
            while bf <= ef and ffl[bf] >= 0:
                bf += 1
        beginning_flow[g] = bf
    return beginning_flow


def step9_checks_on_flow_events(beginning_rain_checked, end_rain_checked, beginning_flow,
                                end_flow, fluct_flow_Tr):
    """STEP9_checks_on_flow_events.m -> ungrouped (br, er, bf, ef) of valid events."""
    brc = np.asarray(beginning_rain_checked, dtype=float)
    erc = np.asarray(end_rain_checked, dtype=float)
    bfc = np.array(beginning_flow, dtype=float)
    efc = np.array(end_flow, dtype=float)
    ffl = fluct_flow_Tr
    for g in range(bfc.size):
        bf, ef = beginning_flow[g], end_flow[g]
        if np.isnan(bf) or np.isnan(ef):
            continue
        # short-circuit order as in MATLAB: ef<=bf is tested before ffl(bf) is read
        if (ef <= bf or ffl[int(bf)] > 0 or ffl[int(ef)] < 0
                or bf < brc[g] or ef < erc[g]):
            bfc[g] = np.nan
            efc[g] = np.nan
    keep = ~np.isnan(brc) & ~np.isnan(bfc) & ~np.isnan(erc) & ~np.isnan(efc)
    return brc[keep], erc[keep], bfc[keep], efc[keep]


def step10_checks_on_overlapping_events(beginning_rain_ungrouped, end_rain_ungrouped,
                                        beginning_flow_ungrouped, end_flow_ungrouped):
    """STEP10_checks_on_overlapping_events.m -> grouped (br, er, bf, ef) as int arrays.

    MATLAB returns ``time(index)``; the caller maps indices to dates.
    """
    bru = np.array(beginning_rain_ungrouped, dtype=float)
    eru = np.array(end_rain_ungrouped, dtype=float)
    bfu = np.array(beginning_flow_ungrouped, dtype=float)
    efu = np.array(end_flow_ungrouped, dtype=float)

    marker = [g for g in range(eru.size - 1)  # MATLAB: for g=1:length(eru)-1
              if eru[g] > bru[g + 1] or efu[g] > bfu[g + 1]]
    # MATLAB ``for q=1:length(marker)``: the inner while advances a copy of q;
    # the for loop still visits every q, so the tail of each run of consecutive
    # markers is visited again. Those rows are already NaN, so the repeat
    # only rewrites NaN, but it is kept for fidelity.
    for q0 in range(len(marker)):
        q = q0
        to_group = [marker[q]]
        while q < len(marker) - 1 and marker[q] == marker[q + 1] - 1:
            to_group.append(marker[q + 1])
            q += 1
        first, last_next = to_group[0], to_group[-1] + 1
        efu[first] = efu[last_next]
        eru[first] = eru[last_next]
        for arr in (bru, bfu, efu, eru):
            if len(to_group) > 1:
                arr[to_group[1:]] = np.nan
            arr[last_next] = np.nan

    keep = ~np.isnan(bru) & ~np.isnan(bfu) & ~np.isnan(eru) & ~np.isnan(efu)
    return (bru[keep].astype(int), eru[keep].astype(int),
            bfu[keep].astype(int), efu[keep].astype(int))


def event_identification_dmca(rain, flow, rain_min, max_window):
    """EVENT_IDENTIFICATION_DMCA.m.

    ``rain`` and ``flow`` are 1-D arrays in the same units per time step;
    ``rain_min`` is in those units. Returns 0-based index arrays
    (beginning_rain, end_rain, beginning_flow, end_flow) and Tr.
    """
    rain = np.asarray(rain, dtype=float)
    flow = np.asarray(flow, dtype=float)
    empty = np.array([], dtype=int)

    Tr, fluct_rain_Tr, fluct_flow_Tr, fluct_bivariate_Tr = step1_step2_tr_and_fluctuations(
        rain, flow, rain_min, max_window)
    beginning_core, end_core = step3_core_identification(fluct_bivariate_Tr)
    if beginning_core.size == 0:  # MATLAB would error on undefined outputs
        return empty, empty, empty, empty, Tr
    end_rain = step4_end_rain_events(beginning_core, end_core, rain, fluct_rain_Tr, rain_min)
    beginning_rain = step5_beginning_rain_events(beginning_core, end_rain, rain, fluct_rain_Tr,
                                                 rain_min)
    brc, erc = step6_checks_on_rain_events(beginning_rain, end_rain, rain, rain_min)
    end_flow = step7_end_flow_events(brc, erc, beginning_core, end_core, flow, fluct_rain_Tr,
                                     fluct_flow_Tr, Tr)
    beginning_flow = step8_beginning_flow_events(brc, erc, end_flow, beginning_core,
                                                 fluct_rain_Tr, fluct_flow_Tr)
    bru, eru, bfu, efu = step9_checks_on_flow_events(brc, erc, beginning_flow, end_flow,
                                                     fluct_flow_Tr)
    br, er, bf, ef = step10_checks_on_overlapping_events(bru, eru, bfu, efu)
    return br, er, bf, ef, Tr


def baseflow_curve(beginning_flow, end_flow, flow):
    """BASEFLOW_CURVE.m: straight lines joining every consecutive flow delimiter.

    The delimiters are taken in the order BF1, EF1, BF2, EF2, ..., so the
    inter-event stretches are joined too. Segments that are >= 90 % NaN are set
    to NaN (endpoints included), and a line starting from a NaN baseflow value
    stays NaN, as in MATLAB. Where flow(start) == flow(end) no line is drawn.
    """
    flow = np.asarray(flow, dtype=float)
    baseflow = flow.copy()
    delims = np.column_stack([beginning_flow, end_flow]).ravel().astype(int)
    for k in range(delims.size - 1):
        ib, ie = delims[k], delims[k + 1]
        seg = flow[ib : ie + 1]  # MATLAB: flow(index_beg:index_end)
        if np.sum(np.isnan(seg)) >= seg.size * 0.9:
            baseflow[ib : ie + 1] = np.nan
        elif ie - ib == 1:
            baseflow[ib] = flow[ib]
            baseflow[ie] = flow[ie]
        elif flow[ib] < flow[ie]:
            increment = (flow[ie] - flow[ib]) / (ie - ib)
            for j in range(ib + 1, ie):  # MATLAB: index_beg+1:index_end-1
                baseflow[j] = baseflow[ib] + increment * (j - ib)
        elif flow[ib] > flow[ie]:
            increment = (flow[ib] - flow[ie]) / (ie - ib)
            for j in range(ib + 1, ie):
                baseflow[j] = baseflow[ib] - increment * (j - ib)
    over = baseflow > flow  # NaN compares false, as in MATLAB
    baseflow[over] = flow[over]
    return baseflow


def event_analysis(beginning_rain, end_rain, beginning_flow, end_flow, rain, flow,
                   flow_is_runoff=False, multiple=1.0):
    """EVENT_ANALYSIS.m.

    ``multiple`` converts summed per-step values to volumes, as in MATLAB
    (``VOLUME = nansum(...) .* multiple``). Durations are ``end - start`` in
    time steps (MATLAB ``etime``/(3600*multiple) with ``multiple`` hours per
    step). Volumes are inclusive NaN-ignoring sums. Returns a dict of arrays.
    """
    rain = np.asarray(rain, dtype=float)
    flow = np.asarray(flow, dtype=float)
    n = len(beginning_rain)
    volume_rain = np.array([_seq_sum(rain[beginning_rain[h] : end_rain[h] + 1]) * multiple
                            for h in range(n)])
    if flow_is_runoff:  # MATLAB flag=1
        volume_runoff = np.array([_seq_sum(flow[beginning_flow[h] : end_flow[h] + 1]) * multiple
                                  for h in range(n)])
    else:  # MATLAB flag=0: stormflow above the BASEFLOW_CURVE line
        baseflow = baseflow_curve(beginning_flow, end_flow, flow)
        volume_runoff = np.array([
            _seq_sum(flow[beginning_flow[h] : end_flow[h] + 1]
                     - baseflow[beginning_flow[h] : end_flow[h] + 1]) * multiple
            for h in range(n)])
    with np.errstate(divide="ignore", invalid="ignore"):
        runoff_ratio = volume_runoff / volume_rain
    return {
        "duration_rain": np.asarray(end_rain, dtype=int) - np.asarray(beginning_rain, dtype=int),
        "volume_rain": volume_rain,
        "duration_runoff": np.asarray(end_flow, dtype=int) - np.asarray(beginning_flow, dtype=int),
        "volume_runoff": volume_runoff,
        "runoff_ratio": runoff_ratio,
    }


def dmca_esr(rain, flow, r_min=R_MIN, l_max=L_MAX, dates=None, flow_is_runoff=False,
             multiple=1.0):
    """Run DMCA-ESR (EVENT_IDENTIFICATION_DMCA) and EVENT_ANALYSIS on one series pair.

    Parameters
    ----------
    rain, flow : 1-D arrays, same length and units per time step. NaN is
        allowed; the cumulative sums treat it as zero, as MATLAB 'omitnan' does.
    r_min : minimum significant rain in the units of ``rain`` (MATLAB ``rain_min``).
    l_max : maximum moving-window length tested for Tr (MATLAB ``max_window``).
    dates : optional sequence of timestamps; adds date columns.
    flow_is_runoff : MATLAB ``flag``; False subtracts the baseflow line.
    multiple : MATLAB ``multiple``; volumes are sums times ``multiple``.

    Returns
    -------
    DataFrame with one row per event: 0-based inclusive indices ``rain_start``,
    ``rain_end``, ``flow_start``, ``flow_end``, MATLAB-style durations
    (end - start, in steps), volumes and runoff ratio. ``df.attrs['Tr']`` is
    the catchment response time in time steps.
    """
    rain = np.asarray(rain, dtype=float)
    flow = np.asarray(flow, dtype=float)
    if rain.shape != flow.shape or rain.ndim != 1:
        raise ValueError("rain and flow must be 1-D arrays of equal length")
    br, er, bf, ef, Tr = event_identification_dmca(rain, flow, r_min, l_max)
    stats = event_analysis(br, er, bf, ef, rain, flow, flow_is_runoff, multiple)
    df = pd.DataFrame({
        "rain_start": br, "rain_end": er, "flow_start": bf, "flow_end": ef,
        "duration_rain": stats["duration_rain"], "duration_flow": stats["duration_runoff"],
        "volume_rain": stats["volume_rain"], "volume_flow": stats["volume_runoff"],
        "runoff_ratio": stats["runoff_ratio"],
    })
    if dates is not None:
        dates = pd.DatetimeIndex(dates)
        for col, idx in [("rain_start_date", br), ("rain_end_date", er),
                         ("flow_start_date", bf), ("flow_end_date", ef)]:
            df[col] = dates[idx]
    df.attrs["Tr"] = Tr
    return df


# ---------------------------------------------------------------------------
# Ameli et al. (2026) gauge-level pipeline
# ---------------------------------------------------------------------------
def load_event_inputs(gcin, zip_path=None):
    """Daily inputs for one gauge from ``Event_Inputs.zip`` (date, P and Q in mm/day).

    ``float_precision="round_trip"`` matters: pandas' default parser is off by
    one ulp for ~15 % of these values, which changes the floating-point
    residues that decide whether zero-stormflow events pass the runoff-ratio
    filter (e.g. GCIN 3719).
    """
    with zipfile.ZipFile(zip_path or paths.EVENT_INPUTS_ZIP) as z:
        raw = z.read(f"Event_Inputs/{gcin}.csv")
    df = pd.read_csv(io.BytesIO(raw), float_precision="round_trip")
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_catalogue(gcins=None, seasons=("dormant", "growing"), chunksize=500_000):
    """The authors' event catalogue, optionally restricted to ``gcins``.

    Reads the 130-150 MB files in chunks and keeps only the requested gauges.
    Adds a ``season`` column; date columns are parsed to timestamps.
    """
    wanted = None if gcins is None else set(int(g) for g in gcins)
    parts = []
    for season in seasons:
        for chunk in pd.read_csv(paths.EVENTS[season], chunksize=chunksize):
            if wanted is not None:
                chunk = chunk[chunk["GCIN"].isin(wanted)]
            if len(chunk):
                parts.append(chunk.assign(season=season))
    if not parts:
        return pd.DataFrame(columns=CATALOGUE_COLUMNS + ["season"])
    cat = pd.concat(parts, ignore_index=True)
    for col in ["start_precip_date", "end_precip_date", "start_stormflow_date",
                "end_stormflow_date"]:
        cat[col] = pd.to_datetime(cat[col])
    return cat


def season_probability(start, end, monthly):
    """Mean of the monthly growing/dormancy values over the calendar months
    spanned by [start, end] (each month counted once, not weighted by days).

    ``start``/``end`` are DatetimeIndex-like of equal length; ``monthly`` is a
    length-12 array (Jan..Dec).
    """
    start = pd.DatetimeIndex(start)
    end = pd.DatetimeIndex(end)
    monthly = np.asarray(monthly, dtype=float)
    first = start.month.to_numpy() - 1
    n_months = ((end.year - start.year) * 12 + (end.month - start.month)).to_numpy() + 1
    total = np.zeros(len(start))
    for k in range(int(n_months.max(initial=0))):
        total += np.where(k < n_months, monthly[(first + k) % 12], 0.0)
    return total / n_months


def detect_gauge_events(gcin, r_min=R_MIN, l_max=L_MAX, min_events=MIN_EVENTS_PER_SEASON,
                        inputs=None, phenology=None, attributes=None):
    """Detect and filter events for one gauge as in Ameli et al. (2026).

    Conventions, each inferred from the authors' catalogue (``Identified_
    Rainfall_Runoff_Events_*.csv``) and checked against it event by event:

    - DMCA-ESR runs on the full ``Event_Inputs`` series, NaN streamflow
      included and leading/trailing NaN tails *not* trimmed (trimming changes
      Tr and loses events, e.g. GCIN 100).
    - As in example.m, P and Q are divided by 24 (mm/h), ``rain_min`` is the
      literal 0.05 mm/h (R_min/24 rounded to 10 decimals; ``1.2/24`` is one ulp
      smaller and loses an event at GCIN 2674) and volumes are multiplied back
      by ``multiple`` = 24. This reproduces their floating-point residues in
      zero-stormflow events.
    - ``missed_streamflow`` = NaN streamflow days in [start_stormflow,
      end_stormflow]; events with any are dropped (catalogue is all zeros).
    - Kept: 0 < runoff ratio <= 1; 2 <= precipitation duration <= 15 days and
      stormflow duration <= 15 days (inclusive day counts, as in the catalogue).
      Zero-volume events survive in their catalogue only through floating-point
      residues (volumes ~1e-17); the same arithmetic reproduces that here.
    - ``growing_dormancy_prob`` = mean of the gauge's monthly values over the
      calendar months from start_precip_date to end_stormflow_date; < 0 is
      dormant, >= 0 growing (their growing file contains exact zeros). This
      reproduces their values for every gauge except the 1,145 with Source ID
      'WRR_*', whose catalogue values are multiples of 1/18 and do not come
      from the released CSV; their season split cannot be reproduced.
    - Seasons with fewer than ``min_events`` events are dropped. Their released
      catalogue keeps such seasons (96 growing gauge-seasons, class NaN), so
      pass ``min_events=0`` to compare with it.

    Parameters
    ----------
    inputs : optional DataFrame (date, precipitation_mmd, streamflow_mmd);
        loaded from ``Event_Inputs.zip`` when None.
    phenology : optional length-12 monthly values (Jan..Dec) for this gauge;
        read from ``Gauged_Catchments_Growing_Dormancy_Probability.csv`` when None.
    attributes : optional DataFrame of gauge metadata indexed by GCIN, used
        for ``Catchment_Boundary_Flagged``; read from the metadata CSV when None.

    Returns
    -------
    DataFrame with the catalogue's columns plus ``season`` and ``Tr``. ``id``
    is our 0-based DMCA event number within the gauge (their ids are global
    counters that cannot be reproduced).
    """
    if inputs is None:
        inputs = load_event_inputs(gcin)
    dates = pd.DatetimeIndex(inputs["date"])
    p = inputs["precipitation_mmd"].to_numpy(dtype=float)
    q = inputs["streamflow_mmd"].to_numpy(dtype=float)

    rain_min = round(r_min / MULTIPLE, 10)  # the authors' literal 0.05 mm/h
    raw = dmca_esr(p / MULTIPLE, q / MULTIPLE, rain_min, l_max, dates=dates,
                   multiple=MULTIPLE)

    nan_cum = np.r_[0, np.cumsum(np.isnan(q))]
    out = pd.DataFrame({
        "GCIN": int(gcin),
        "id": np.arange(len(raw)),
        "start_precip_date": raw["rain_start_date"],
        "end_precip_date": raw["rain_end_date"],
        "duration_precip": raw["rain_end"] - raw["rain_start"] + 1,
        "start_stormflow_date": raw["flow_start_date"],
        "end_stormflow_date": raw["flow_end_date"],
        "duration_stormflow": raw["flow_end"] - raw["flow_start"] + 1,
        "volume_precip_mm": raw["volume_rain"],
        "volume_stormflow_mm": raw["volume_flow"],
        "runoff_ratio": raw["runoff_ratio"],
        "missed_streamflow": nan_cum[raw["flow_end"] + 1] - nan_cum[raw["flow_start"]],
    })
    keep = ((out["missed_streamflow"] == 0)
            & (out["runoff_ratio"] > 0) & (out["runoff_ratio"] <= 1)
            & (out["duration_precip"] >= MIN_DURATION_PRECIP)
            & (out["duration_precip"] <= MAX_DURATION)
            & (out["duration_stormflow"] <= MAX_DURATION))
    out = out[keep].reset_index(drop=True)

    if phenology is None:
        pheno = pd.read_csv(paths.GAUGED_PHENOLOGY, index_col="GCIN")
        phenology = pheno.loc[int(gcin), MONTHS].to_numpy(dtype=float)
    out["growing_dormancy_prob"] = season_probability(
        out["start_precip_date"], out["end_stormflow_date"], phenology)
    out["season"] = np.where(out["growing_dormancy_prob"] < 0, "dormant", "growing")

    if attributes is None:
        attributes = pd.read_csv(paths.GAUGED_ATTRS, index_col="GCIN",
                                 usecols=["GCIN", "Catchment_Boundary_Flagged"])
    flagged = attributes.loc[int(gcin), "Catchment_Boundary_Flagged"]
    out["Catchment_Boundary_Flagged"] = bool(flagged)

    if min_events:
        counts = out["season"].map(out["season"].value_counts())
        out = out[counts >= min_events].reset_index(drop=True)
    out["Tr"] = raw.attrs["Tr"]
    return out[CATALOGUE_COLUMNS + ["season", "Tr"]]
