"""Daily streamflow from national agencies for the Phase 2 validation set.

Each `fetch_<source>` yields (national_id, raw) pairs, where raw has columns
date, q_m3s, flag and an optional raw.attrs["note"]; raw is the exception
instead when the request failed. `write_station` turns a raw series into one row per
calendar day between the first and last observed day and writes
data/phase2/streamflow/<source>/<UCIN>.parquet. `summarise` gives the
manifest fields; record-length statistics refer to 1979-2019.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import tempfile
import time
import unicodedata
import zipfile
from collections.abc import Iterator
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

from stormflow_diag import paths

START, END = "1950-01-01", "2019-12-31"
PERIOD = ("1979-01-01", "2019-12-31")
CFS = 0.028316846592  # m3/s per ft3/s
MI2 = 2.589988110336  # km2 per mi2
OUT = paths.DATA / "phase2" / "streamflow"
INVENTORY = paths.RESULTS / "phase2" / "station_inventory.csv"
MANIFEST = paths.RESULTS / "phase2" / "streamflow_manifest.csv"
AREA_CHECK = paths.RESULTS / "phase2" / "gsim_polygon_area_check.csv"
MANIFEST_COLS = ["UCIN", "source", "national_id", "status", "first_date", "last_date", "n_days_valid",
                 "frac_missing_1979_2019", "n_years_ge_300_valid_days", "note",
                 "area_km2", "national_area_km2", "mean_q_mmd"]


def inventory() -> pd.DataFrame:
    return pd.read_csv(INVENTORY, dtype={"reference.no": str, "Source ID": str})


def validation_set(source: str = "usgs", min_years: int = 10) -> pd.DataFrame:
    """Validation stations of one source: manifest status ok, >= `min_years` calendar years
    with >= 300 valid days in 1979-2019, and polygon area within 0.8-1.25x the national
    drainage area (`r` in results/phase2/gsim_polygon_area_check.csv)."""
    man = pd.read_csv(MANIFEST, dtype={"national_id": str})
    chk = pd.read_csv(AREA_CHECK, usecols=["UCIN", "Source ID", "dormant_predicted_class",
                                           "growing_predicted_class", "r"])
    v = man[(man.source == source) & (man.status == "ok") & (man.n_years_ge_300_valid_days >= min_years)]
    v = v.merge(chk, on="UCIN")
    return v[v.r.between(0.8, 1.25)].reset_index(drop=True)


def retry(fn, *args, tries: int = 4, wait: float = 10.0, **kwargs):
    """Call fn, retrying with exponential backoff on any exception."""
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(wait * 2**i)


def get_json(url: str, params: dict | None = None, timeout: float = 180) -> dict:
    """GET with retries; HTTP errors count as failures."""
    import requests

    def once():
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    return retry(once)


# --- common writer ----------------------------------------------------------

def standardise(raw: pd.DataFrame, area_km2: float) -> pd.DataFrame:
    """One row per day from first to last observed value; q_mmd from the given area."""
    raw = raw.dropna(subset=["q_m3s"]).sort_values("date").drop_duplicates("date")
    if raw.empty:
        return pd.DataFrame(columns=["date", "q_m3s", "q_mmd", "flag"])
    raw = raw.assign(date=raw.date.astype("datetime64[ns]"))
    days = pd.date_range(raw.date.iloc[0], raw.date.iloc[-1], freq="D", name="date", unit="ns")
    df = raw.set_index("date").reindex(days).reset_index()
    df["q_m3s"] = df.q_m3s.astype(float)
    df["q_mmd"] = df.q_m3s * 86.4 / area_km2
    df["flag"] = df.flag.astype("string")
    return df[["date", "q_m3s", "q_mmd", "flag"]]


def summarise(df: pd.DataFrame) -> dict:
    """Manifest fields for a standardised series; missing share and year counts over 1979-2019."""
    valid = df.loc[df.q_m3s.notna()]
    period = pd.date_range(*PERIOD, freq="D")
    in_period = valid.date.between(*PERIOD)
    per_year = valid.loc[in_period, "date"].dt.year.value_counts()
    flags = valid.flag.fillna("").value_counts()
    flags = flags[flags.index != ""]
    return {
        "first_date": valid.date.min().date() if len(valid) else None,
        "last_date": valid.date.max().date() if len(valid) else None,
        "n_days_valid": len(valid),
        "frac_missing_1979_2019": round(1 - in_period.sum() / len(period), 4),
        "n_years_ge_300_valid_days": int((per_year >= 300).sum()),
        "mean_q_mmd": round(valid.q_mmd.mean(), 4) if len(valid) else np.nan,
        "flags": "; ".join(f"{k}={v}" for k, v in flags.head(6).items()),
        "n_negative": int((valid.q_m3s < 0).sum()),
    }


def write_station(source: str, ucin: int, raw: pd.DataFrame, area_km2: float) -> dict:
    df = standardise(raw, area_km2)
    if df.empty:
        return {"status": "not_found", "note": "; ".join(filter(None, [raw.attrs.get("note"),
                                                                        "no valid daily flow in 1950-2019"]))}
    (OUT / source).mkdir(parents=True, exist_ok=True)
    df.attrs["note"] = raw.attrs.get("note", "")
    df.to_parquet(OUT / source / f"{ucin}.parquet", index=False)
    return {"status": "ok", "note": df.attrs["note"], **summarise(df)}


def note(s: dict, area_km2: float, national_area_km2: float) -> str:
    parts = [s.pop("note", "")]
    if s.get("flags"):
        parts.append(f"flags: {s['flags']}")
    if s.get("n_negative"):
        parts.append(f"negative flow on {s['n_negative']} days")
    if national_area_km2 and np.isfinite(national_area_km2) and national_area_km2 > 0:
        r = area_km2 / national_area_km2
        if not 0.8 <= r <= 1.25:
            parts.append(f"AREA MISMATCH polygon/national={r:.3g}")
    return " | ".join(p for p in parts if p)


def update_manifest(rows: pd.DataFrame, source: str) -> pd.DataFrame:
    """Replace this source's rows in the manifest."""
    rows = rows.reindex(columns=MANIFEST_COLS)
    if MANIFEST.exists():
        old = pd.read_csv(MANIFEST, dtype={"national_id": str})
        rows = pd.concat([old[old.source != source], rows], ignore_index=True)
    rows = rows.sort_values(["source", "UCIN"]).astype({"n_days_valid": "Int64", "n_years_ge_300_valid_days": "Int64"})
    rows.to_csv(MANIFEST, index=False)
    return rows


# --- USGS NWIS ---------------------------------------------------------------

def usgs_site_candidates(ref: str) -> list[str]:
    """GSIM drops leading zeros from USGS site numbers (8-15 digits); candidates in order
    of preference, the first one known to the NWIS site service is used."""
    if len(ref) < 8:
        return [ref.zfill(8)]
    return ["0" + ref, ref] if len(ref) == 9 else [ref, "0" + ref]


def usgs_info(site_nos: list[str], batch: int = 100) -> pd.DataFrame:
    """Site service rows (site_no, station_nm, drain_area_km2) for sites that exist."""
    from dataretrieval import nwis
    from dataretrieval.exceptions import HTTPError

    def once(sites):
        try:
            return nwis.get_info(sites=sites, siteOutput="expanded")[0]
        except HTTPError as e:
            if e.status_code == 404:  # none of the sites exist
                return pd.DataFrame(columns=["site_no", "station_nm", "drain_area_va"])
            raise

    out = []
    for i in range(0, len(site_nos), batch):
        out.append(retry(once, site_nos[i:i + batch])[["site_no", "station_nm", "drain_area_va"]])
        time.sleep(1)
    info = pd.concat(out, ignore_index=True).drop_duplicates("site_no")
    info["drain_area_km2"] = pd.to_numeric(info.drain_area_va, errors="coerce") * MI2
    return info.set_index("site_no")


def fetch_usgs(site_nos: list[str], batch: int = 25) -> Iterator[tuple[str, pd.DataFrame]]:
    """NWIS daily mean discharge (00060/00003), START-END, several sites per request.

    Sites with more than one 00060 series (e.g. several gauges or methods) keep the
    plain `00060_Mean` series, or the longest one if that is absent.
    """
    from dataretrieval import nwis

    for i in range(0, len(site_nos), batch):
        sites = site_nos[i:i + batch]
        try:
            df, _ = retry(nwis.get_dv, sites=sites, parameterCd="00060", statCd="00003", start=START, end=END)
        except Exception as e:  # noqa: BLE001 - reported per site in the manifest
            for s in sites:
                yield s, e
            continue
        time.sleep(1)
        if df.empty:
            continue
        df = df.reset_index()
        for s, g in df.groupby("site_no"):
            vals = [c for c in g.columns if c.startswith("00060") and c.endswith("Mean") and g[c].notna().any()]
            if not vals:
                continue
            col = "00060_Mean" if "00060_Mean" in vals else max(vals, key=lambda c: g[c].notna().sum())
            q = pd.to_numeric(g[col], errors="coerce").where(lambda x: x > -999999)
            raw = pd.DataFrame({"date": g.datetime.dt.tz_localize(None).dt.normalize(),
                                "q_m3s": q * CFS, "flag": g.get(f"{col}_cd")})
            if len(vals) > 1:
                raw.attrs["note"] = f"kept {col} of {len(vals)} 00060 series"
            yield s, raw


# --- HYDAT (ECCC) ------------------------------------------------------------

HYDAT_URL = "https://collaboration.cmc.ec.gc.ca/cmc/hydrometrics/www/"


def hydat_zip() -> Path:
    """Latest Hydat_sqlite3_YYYYMMDD.zip in data/hydat/, downloaded if not already there."""
    import requests

    name = max(re.findall(r"Hydat_sqlite3_\d{8}\.zip", retry(requests.get, HYDAT_URL, timeout=60).text))
    dest = paths.DATA / "hydat" / name
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(".part")
        with requests.get(HYDAT_URL + name, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        part.rename(dest)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hydat_load(stations: list[str], zip_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily flows (station, date, q_m3s, flag) and station table (area, regulation)
    for the given station numbers, read from the zipped HYDAT sqlite."""
    q = ",".join("?" * len(stations))
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path) as z:
        db = z.extract(next(n for n in z.namelist() if n.endswith(".sqlite3")), tmp)
        with sqlite3.connect(db) as con:
            wide = pd.read_sql(f"SELECT * FROM DLY_FLOWS WHERE STATION_NUMBER IN ({q})", con, params=stations)
            meta = pd.read_sql(f"SELECT STATION_NUMBER, STATION_NAME, DRAINAGE_AREA_GROSS FROM STATIONS "
                               f"WHERE STATION_NUMBER IN ({q})", con, params=stations)
            reg = pd.read_sql(f"SELECT * FROM STN_REGULATION WHERE STATION_NUMBER IN ({q})", con, params=stations)
    n = len(wide)
    flows = pd.DataFrame({
        "station": np.repeat(wide.STATION_NUMBER.to_numpy(), 31),
        "date": pd.to_datetime(pd.DataFrame({"year": np.repeat(wide.YEAR.to_numpy(), 31),
                                             "month": np.repeat(wide.MONTH.to_numpy(), 31),
                                             "day": np.tile(np.arange(1, 32), n)}), errors="coerce"),
        "q_m3s": wide[[f"FLOW{d}" for d in range(1, 32)]].to_numpy(float).ravel(),
        "flag": wide[[f"FLOW_SYMBOL{d}" for d in range(1, 32)]].to_numpy(object).ravel(),
    }).dropna(subset=["date"])
    meta = meta.merge(reg[["STATION_NUMBER", "REGULATED"]], on="STATION_NUMBER", how="left").set_index("STATION_NUMBER")
    return flows, meta


def fetch_hydat(stations: list[str], flows: pd.DataFrame, meta: pd.DataFrame) -> Iterator[tuple[str, pd.DataFrame]]:
    for s, g in flows[flows.station.isin(stations)].dropna(subset=["q_m3s"]).groupby("station"):
        raw = g.loc[g.date.between(START, END), ["date", "q_m3s", "flag"]].reset_index(drop=True)
        notes = ["HYDAT: regulated"] if meta.REGULATED.get(s) == 1 else []
        if raw.empty:
            notes.append(f"HYDAT daily flow {g.date.min().year}-{g.date.max().year}")
        raw.attrs["note"] = "; ".join(notes)
        yield s, raw


# --- GSIM stations without a national ID (GB, FR) ----------------------------

GSIM_META = paths.DATA / "gsim" / "GSIM_metadata" / "GSIM_catalog" / "GSIM_metadata.csv"


def _km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


STOPWORDS = {"THE", "RIVER", "BROOK", "BURN", "WATER", "RUISSEAU", "RIVIERE", "RU", "FLEUVE",
             "LE", "LA", "LES", "DE", "DU", "DES", "EN", "AU", "AUX", "ET", "SUR", "SOUS"}


def _words(name: str) -> set[str]:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()
    return set(re.findall(r"[A-Z]{2,}", re.sub(r"\(.*?\)|\bL'|\bD'", " ", text))) - STOPWORDS


def _same_river(a: str, b: str) -> bool:
    """Some word of `a` matches a word of `b` up to spelling (similarity >= 0.8)."""
    return any(SequenceMatcher(None, x, y).ratio() >= 0.8 for x in _words(a) for y in _words(b))


def match_by_area(gsim: pd.DataFrame, cand: pd.DataFrame, max_km: float = 5, area_tol: float = 0.01,
                  ) -> pd.DataFrame:
    """Map GSIM stations (gsim.no, river, latitude, longitude, area = GSIM reported area)
    to national stations (id, name, latitude, longitude, area) by position and area.

    A national station qualifies if it lies within `max_km` of the GSIM coordinates
    and its catchment area is within `area_tol` of the GSIM reported area (the
    national agencies supplied that area to GRDC/EWA). One qualifying station is
    taken; with several, the nearest is taken only if the next is >= 3x farther.
    Names are never used to make a match; a match is rejected when no word of the
    GSIM river name resembles a word of the national station name (a check on bad
    coordinates).
    """
    cand = cand.dropna(subset=["latitude", "longitude", "area"])
    out = []
    for _, g in gsim.iterrows():
        d = _km(g.latitude, g.longitude, cand.latitude.to_numpy(), cand.longitude.to_numpy())
        ok = np.flatnonzero((d <= max_km) & (np.abs(cand.area.to_numpy() / g.area - 1) <= area_tol))
        ok = ok[np.argsort(d[ok])]
        row = {"gsim.no": g["gsim.no"], "national_id": None, "n_candidates": len(ok), "dist_km": np.nan, "note": ""}
        if len(ok) == 0:
            row["note"] = f"no national station within {max_km} km with area within {area_tol:.0%}"
        elif len(ok) > 1 and d[ok[1]] < 3 * d[ok[0]]:
            row["note"] = f"{len(ok)} national stations qualify: {', '.join(cand.id.iloc[ok].astype(str))}"
        else:
            c = cand.iloc[ok[0]]
            if _same_river(g.river, c["name"]):
                row.update(national_id=str(c.id), dist_km=round(d[ok[0]], 2))
            else:
                row["note"] = f"match to {c.id} rejected: GSIM river '{g.river}' vs '{c['name']}'"
        out.append(row)
    return pd.DataFrame(out).set_index("gsim.no")


# --- NRFA (UK) ----------------------------------------------------------------

NRFA_URL = "https://nrfaapps.ceh.ac.uk/nrfa/ws/"


def nrfa_stations() -> pd.DataFrame:
    j = get_json(NRFA_URL + "station-info", {"station": "*", "format": "json-object",
                                             "fields": "id,name,catchment-area,latitude,longitude,factors-affecting-runoff"})
    return pd.DataFrame(j["data"]).rename(columns={"catchment-area": "area"})


def fetch_nrfa(ids: list[str], stations: pd.DataFrame) -> Iterator[tuple[str, pd.DataFrame]]:
    """Gauged daily flow (gdf, m3/s) with NRFA data flags; missing days are absent in the stream.

    The NRFA API licence (clause 3.5) allows only temporary caching (<= 30 days) of
    unmodified data; see data/phase2/README.md before running this.
    """
    far = stations.set_index(stations.id.astype(str))["factors-affecting-runoff"]
    for s in ids:
        try:
            ds = get_json(NRFA_URL + "time-series", {"station": s, "data-type": "gdf", "format": "json-object",
                                                     "flags": "true"})["data-stream"]
        except Exception as e:  # noqa: BLE001 - reported per site in the manifest
            yield s, e
            continue
        v = [x if isinstance(x, list) else [x, None] for x in ds[1::2]]
        raw = pd.DataFrame({"date": pd.to_datetime(ds[0::2]), "q_m3s": [x[0] for x in v], "flag": [x[1] for x in v]})
        raw = raw[raw.date.between(START, END)].reset_index(drop=True)
        if isinstance(far.get(s), str) and far.get(s):
            raw.attrs["note"] = f"NRFA factors affecting runoff: {far[s]}"
        yield s, raw
        time.sleep(0.5)


# --- Hub'Eau hydrometrie (France) ------------------------------------------------

HUBEAU_URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/"


def hubeau_sites() -> pd.DataFrame:
    """Hub'Eau site referential (code_site, name, position, surface_bv)."""
    out, page = [], 1
    while True:
        j = get_json(HUBEAU_URL + "referentiel/sites", {"format": "json", "size": 5000, "page": page})
        out += j["data"]
        if not j.get("next"):
            break
        page += 1
    s = pd.DataFrame(out)
    return s.rename(columns={"code_site": "id", "libelle_site": "name", "latitude_site": "latitude",
                             "longitude_site": "longitude", "surface_bv": "area"})


def fetch_hubeau(codes: list[str]) -> Iterator[tuple[str, pd.DataFrame]]:
    """Daily mean flow QmnJ (l/s -> m3/s). An 8-character site code returns the site
    series and its stations' series; the site series (code_station empty) is kept,
    else the longest station series. Flag = qualification/method/status."""
    for c in codes:
        try:
            data, url = [], HUBEAU_URL + "obs_elab"
            params = {"code_entite": c, "grandeur_hydro_elab": "QmnJ", "date_debut_obs_elab": START,
                      "date_fin_obs_elab": END, "size": 20000}
            while url:
                j = get_json(url, params)
                data += j["data"]
                url, params = j.get("next"), None
        except Exception as e:  # noqa: BLE001 - reported per site in the manifest
            yield c, e
            continue
        time.sleep(0.2)
        if not data:
            continue
        d = pd.DataFrame(data)
        d["series"] = d.code_station.fillna("site")
        keep = "site" if "site" in set(d.series) else d.series.value_counts().idxmax()
        d = d[d.series == keep]
        raw = pd.DataFrame({"date": pd.to_datetime(d.date_obs_elab), "q_m3s": d.resultat_obs_elab.astype(float) / 1000,
                            "flag": d.libelle_qualification + "/" + d.libelle_methode + "/" + d.libelle_statut})
        raw.attrs["note"] = f"Hub'Eau series: {keep}"
        yield c, raw.reset_index(drop=True)
