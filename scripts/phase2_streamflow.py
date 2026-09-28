"""Phase 2: daily streamflow for inventory stations from national agencies.

  python scripts/phase2_streamflow.py --source usgs|hydat|nrfa|hubeau [--force]

Maps each inventory row of the source to a national station ID, downloads
daily mean flow for 1950-2019, writes data/phase2/streamflow/<source>/<UCIN>.parquet
and replaces that source's rows in results/phase2/streamflow_manifest.csv.
Existing parquet files are reused unless --force. Prints the record-length
summary (stations with >= 10 years of >= 300 valid days in 1979-2019).
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from stormflow_diag import streamflow as sf


def setup_usgs(inv: pd.DataFrame):
    rows = inv[inv["reference.db"] == "usgs"]
    cands = rows["reference.no"].map(sf.usgs_site_candidates)
    info = sf.usgs_info(sorted({c for cs in cands for c in cs}))
    ids = cands.map(lambda cs: next((c for c in cs if c in info.index), cs[0]))
    notes = pd.Series(np.where(ids.isin(info.index), "", "site not in NWIS site service"), index=rows.index)
    return rows, ids, notes, info.drain_area_km2, sf.fetch_usgs


def setup_hydat(inv: pd.DataFrame):
    rows = inv[inv["reference.db"] == "hydat"]
    ids = rows["reference.no"]
    z = sf.hydat_zip()
    print(f"HYDAT archive {z.name}, sha256 {sf.sha256(z)}")
    flows, meta = sf.hydat_load(sorted(set(ids)), z)
    notes = pd.Series(np.where(ids.isin(meta.index), "", "station not in HYDAT"), index=rows.index)
    return rows, ids, notes, meta.DRAINAGE_AREA_GROSS, lambda s: sf.fetch_hydat(s, flows, meta)


def matched(rows: pd.DataFrame, national: pd.DataFrame, source: str, **kw) -> pd.DataFrame:
    """Position/area match of GSIM rows to national stations; mapping table saved for audit."""
    gsim = pd.read_csv(sf.GSIM_META, usecols=["gsim.no", "river", "latitude", "longitude", "area"])
    m = sf.match_by_area(rows[["gsim.no"]].drop_duplicates().merge(gsim, on="gsim.no"), national, **kw)
    m.to_csv(sf.MANIFEST.parent / f"streamflow_mapping_{source}.csv")
    return m


def setup_nrfa(inv: pd.DataFrame):
    rows = inv[(inv.country == "GB") & inv["gsim.no"].notna()]
    st = sf.nrfa_stations()
    m = matched(rows, st, "nrfa", area_tol=0.01)
    ids = rows["gsim.no"].map(m.national_id)
    notes = rows["gsim.no"].map(m.note)
    area = st.set_index(st.id.astype(str)).area
    return rows, ids, notes.where(ids.isna(), ""), area, lambda s: sf.fetch_nrfa(s, st)


def setup_hubeau(inv: pd.DataFrame):
    rows = inv[inv.country == "FR"]
    sites = sf.hubeau_sites()
    gsim = rows["gsim.no"].notna()
    m = matched(rows[gsim], sites, "hubeau", area_tol=0.02)
    ids = rows["gsim.no"].map(m.national_id)
    notes = rows["gsim.no"].map(m.note).fillna("")
    camels = rows["Polygon Source"] == "CAMELS-FR"  # Source ID carries the 10-character station code
    ids[camels] = rows.loc[camels, "Source ID"].str.removeprefix("CAMELS-FR_")
    area = sites.set_index("id").area
    area = pd.concat([area, pd.Series(area.reindex(ids[camels].str[:8]).to_numpy(), index=ids[camels])])
    return rows, ids, notes.where(ids.isna(), ""), area[~area.index.duplicated()], sf.fetch_hubeau


SETUP = {"usgs": setup_usgs, "hydat": setup_hydat, "nrfa": setup_nrfa, "hubeau": setup_hubeau}


def run(source: str, force: bool) -> pd.DataFrame:
    t0 = time.time()
    inv = sf.inventory()
    rows, ids, notes, national_area, fetch = SETUP[source](inv)
    have = {u for u in rows.UCIN if (sf.OUT / source / f"{u}.parquet").exists()} if not force else set()
    todo = sorted(set(ids[ids.notna() & (notes == "") & ~rows.UCIN.isin(have)]))
    print(f"{source}: {len(rows)} rows, {ids.notna().sum()} mapped, {len(todo)} IDs to download")

    by_id = rows.assign(national_id=ids).groupby("national_id").UCIN.apply(list).to_dict()
    area = rows.set_index("UCIN").Area
    results = {}
    for u in have:
        df = pd.read_parquet(sf.OUT / source / f"{u}.parquet")
        results[u] = {"status": "ok", "note": df.attrs.get("note", ""), **sf.summarise(df)}
    for n, (nid, raw) in enumerate(fetch(todo), 1):
        for u in by_id.get(nid, []):
            if isinstance(raw, Exception):
                results[u] = {"status": "error", "note": f"{type(raw).__name__}: {raw}"[:300]}
            else:
                results[u] = sf.write_station(source, u, raw, area[u])
        if n % 100 == 0:
            print(f"  {n} sites written, {time.time() - t0:.0f}s")

    out = []
    for i, r in rows.iterrows():
        u, nid = r.UCIN, ids[i]
        nat = national_area.get(nid, np.nan) if isinstance(nid, str) else np.nan
        if not isinstance(nid, str):
            res = {"status": "unmapped", "note": notes[i]}
        elif notes[i]:
            res = {"status": "not_found", "note": notes[i]}
        else:
            res = dict(results.get(u, {"status": "not_found", "note": "no daily flow returned for 1950-2019"}))
        res["note"] = sf.note(res, r.Area, nat)
        out.append({"UCIN": u, "source": source, "national_id": nid, "area_km2": r.Area,
                    "national_area_km2": nat, **res})
    man = pd.DataFrame(out)
    sf.update_manifest(man, source)

    man = man.merge(rows[["UCIN", "any_simple"]], on="UCIN")
    print(f"\n{source}: done in {(time.time() - t0) / 60:.1f} min")
    print(man.status.value_counts().to_string())
    man["usable"] = (man.status == "ok") & (man.n_years_ge_300_valid_days >= 10)
    print("\nStations with >= 10 years of >= 300 valid days in 1979-2019, by any_simple:")
    print(man.groupby("any_simple").agg(n=("UCIN", "size"), ok=("status", lambda s: (s == "ok").sum()),
                                        usable=("usable", "sum")).to_string())
    return man


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, choices=sorted(SETUP))
    ap.add_argument("--force", action="store_true", help="re-download stations that already have a file")
    a = ap.parse_args()
    run(a.source, a.force)


if __name__ == "__main__":
    main()
