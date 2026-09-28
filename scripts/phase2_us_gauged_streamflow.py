"""Phase 2: our USGS streamflow processing against the authors' gauged series.

  python scripts/phase2_us_gauged_streamflow.py [--force]

For the gauged catchments with Source ID GSIM_US_*, maps gsim.no to a USGS site
(GSIM reference.no, leading zeros restored as in streamflow.py), downloads NWIS
daily discharge with the Phase 2 fetcher into
data/phase2/streamflow/usgs_gauged/<GCIN>.parquet (q_mmd from the authors'
`Area` for the GCIN) and compares it with `streamflow_mmd` in their
Event_Inputs/<GCIN>.csv.

Writes results/phase2/us_streamflow_vs_authors.csv, one row per GCIN:

- n_overlap: days where both series have a value; frac_match: share of those
  within 0.1 % (both zero counts as a match); match = frac_match >= 0.99.
- ratio_median / ratio_p05 / ratio_p95: theirs / ours on overlapping days with
  ours > 0; ratio_median_mismatch: the same over mismatching days only.
- area_ratio_usgs: authors' Area / USGS drainage area (what a constant ratio
  would be if they had used the USGS area instead of their polygon).
- theirs_nan_ours_valid (+ by NWIS flag), ours_nan_theirs_valid: days inside
  their valid record where only one side has a value.
- n_est / n_est_theirs_nan / frac_est_match: NWIS estimated days ('e' qualifier)
  inside their record, how many they left NaN, how many match.
- n_prov / frac_prov_match: provisional (P) days.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from stormflow_diag import paths
from stormflow_diag import streamflow as sf
from stormflow_diag.stage1 import events as ev

SOURCE = "usgs_gauged"
OUT_CSV = paths.RESULTS / "phase2" / "us_streamflow_vs_authors.csv"
RTOL = 1e-3


def gauged_us() -> pd.DataFrame:
    meta = pd.read_csv(paths.GAUGED_ATTRS, usecols=["GCIN", "Source ID", "Area", "Catchment_Boundary_Flagged",
                                                    "streamflow_start", "streamflow_end", "dormant_gauged_class",
                                                    "growing_gauged_class"])
    g = meta[meta["Source ID"].str.startswith("GSIM_US_")].copy()
    g["gsim.no"] = g["Source ID"].str.removeprefix("GSIM_")
    gsim = pd.read_csv(sf.GSIM_META, usecols=["gsim.no", "reference.db", "reference.no"], dtype={"reference.no": str})
    return g.merge(gsim, on="gsim.no", how="left")


def download(g: pd.DataFrame, force: bool) -> pd.DataFrame:
    """Resolve USGS site numbers and fetch missing series; returns g with site_no, usgs_area_km2, status."""
    cands = g["reference.no"].map(sf.usgs_site_candidates)
    info = sf.usgs_info(sorted({c for cs in cands for c in cs}))
    g["site_no"] = cands.map(lambda cs: next((c for c in cs if c in info.index), cs[0]))
    g["in_site_service"] = g.site_no.isin(info.index)
    g["usgs_area_km2"] = g.site_no.map(info.drain_area_km2)
    g["station_nm"] = g.site_no.map(info.station_nm)

    have = {u for u in g.GCIN if (sf.OUT / SOURCE / f"{u}.parquet").exists()} if not force else set()
    todo = sorted(set(g.loc[g.in_site_service & ~g.GCIN.isin(have), "site_no"]))
    print(f"{len(g)} GSIM_US gauged catchments, {g.in_site_service.sum()} sites in NWIS, {len(todo)} to download")
    by_site = g.groupby("site_no").GCIN.apply(list).to_dict()
    area = g.set_index("GCIN").Area
    status = {u: "ok" for u in have}
    t0 = time.time()
    for n, (site, raw) in enumerate(sf.fetch_usgs(todo), 1):
        for u in by_site.get(site, []):
            if isinstance(raw, Exception):
                status[u] = f"error: {type(raw).__name__}: {raw}"[:200]
            else:
                status[u] = sf.write_station(SOURCE, u, raw, area[u])["status"]
        if n % 100 == 0:
            print(f"  {n} sites, {time.time() - t0:.0f}s")
    g["status"] = g.GCIN.map(status).fillna(
        pd.Series(np.where(g.in_site_service, "not_found", "site not in NWIS"), index=g.index))
    return g


def compare(gcin: int) -> dict:
    theirs = ev.load_event_inputs(gcin)[["date", "streamflow_mmd"]]
    ours = pd.read_parquet(sf.OUT / SOURCE / f"{gcin}.parquet")
    d = theirs.merge(ours[["date", "q_mmd", "flag"]], on="date", how="left")
    valid_t = d.streamflow_mmd.notna()
    first, last = d.date[valid_t].min(), d.date[valid_t].max()
    rec = d[d.date.between(first, last)]  # their valid record span
    vt, vo = rec.streamflow_mmd.notna(), rec.q_mmd.notna()
    both = rec[vt & vo]
    t, o = both.streamflow_mmd.to_numpy(), both.q_mmd.to_numpy()
    close = np.abs(t - o) <= RTOL * np.abs(t) + 1e-12
    pos = o > 0
    ratio = t[pos] / o[pos]
    ratio_mis = (t / np.where(o > 0, o, np.nan))[~close]
    flag = rec.flag.fillna("").astype(str)
    est = flag.str.contains(r"\be\b", regex=True)
    prov = flag.str.contains(r"\bP\b", regex=True)
    only_o = rec[~vt & vo]
    fl_only_o = only_o.flag.fillna("").value_counts()
    est_both = est[vt & vo].to_numpy()
    prov_both = prov[vt & vo].to_numpy()
    return {
        "their_first": first.date(), "their_last": last.date(),
        "their_series_start": d.date.iloc[0].date(), "their_series_end": d.date.iloc[-1].date(),
        "n_their_valid": int(vt.sum()), "n_our_valid_in_span": int(vo.sum()),
        "n_overlap": len(both), "frac_match": close.mean() if len(both) else np.nan,
        "ratio_median": np.median(ratio) if ratio.size else np.nan,
        "ratio_p05": np.percentile(ratio, 5) if ratio.size else np.nan,
        "ratio_p95": np.percentile(ratio, 95) if ratio.size else np.nan,
        "ratio_median_mismatch": np.nanmedian(ratio_mis) if np.isfinite(ratio_mis).any() else np.nan,
        "n_mismatch": int((~close).sum()),
        "theirs_nan_ours_valid": len(only_o),
        "theirs_nan_ours_valid_flags": "; ".join(f"{k or '-'}={v}" for k, v in fl_only_o.head(5).items()),
        "ours_nan_theirs_valid": int((vt & ~vo).sum()),
        "n_est": int(est.sum()), "n_est_theirs_nan": int((est & ~vt).sum()),
        "frac_est_match": close[est_both].mean() if est_both.any() else np.nan,
        "n_prov": int(prov.sum()), "frac_prov_match": close[prov_both].mean() if prov_both.any() else np.nan,
        "n_zero_ours": int((o == 0).sum()), "n_zero_theirs": int((t == 0).sum()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download sites that already have a file")
    a = ap.parse_args()

    g = download(gauged_us(), a.force)
    rows = []
    for r in g.itertuples():
        row = {"GCIN": r.GCIN}
        if r.status == "ok":
            row.update(compare(r.GCIN))
        rows.append(row)
    res = g.merge(pd.DataFrame(rows), on="GCIN", how="left")
    res["area_ratio_usgs"] = res.Area / res.usgs_area_km2
    res["match"] = res.frac_match >= 0.99
    cols = ["GCIN", "Source ID", "site_no", "station_nm", "status", "Catchment_Boundary_Flagged", "Area",
            "usgs_area_km2", "area_ratio_usgs", "streamflow_start", "streamflow_end"]
    res = res[cols + [c for c in res.columns if c not in cols and c not in
                      ("gsim.no", "reference.db", "reference.no", "in_site_service")]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_CSV, index=False, float_format="%.6g")

    ok = res[res.status == "ok"]
    print(f"\n{len(ok)} of {len(res)} compared; status counts:\n{res.status.value_counts().to_string()}")
    print(f"match (>= 99 % of overlapping days within 0.1 %): {ok.match.sum()} / {len(ok)} "
          f"({ok.match.mean():.1%})")
    print(ok.frac_match.describe(percentiles=[.01, .05, .1, .25, .5]).to_string())
    print("\nratio theirs/ours, median over GCINs:", ok.ratio_median.median())
    print("non-matching GCINs, ratio_median quantiles:")
    print(ok.loc[~ok.match, "ratio_median"].describe(percentiles=[.05, .25, .5, .75, .95]).to_string())
    print(f"\ntheirs NaN / ours valid days: {ok.theirs_nan_ours_valid.sum()}; "
          f"ours NaN / theirs valid days: {ok.ours_nan_theirs_valid.sum()}")
    print(f"estimated days in their span: {ok.n_est.sum()}, of which NaN in theirs: {ok.n_est_theirs_nan.sum()}")
    print(f"provisional days in their span: {ok.n_prov.sum()}")


if __name__ == "__main__":
    main()
