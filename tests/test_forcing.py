"""Tests for basin-mean precipitation (stormflow_diag.forcing) on synthetic
EM-Earth-like monthly NetCDF files (time x lat x lon, 0.1 deg, variable prcp,
_FillValue over "sea"), in both latitude orders and both longitude conventions.

Reference values are brute force: each cell's share of the polygon from
shapely intersections, times the cell's spherical band area.
"""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

gpd = pytest.importorskip("geopandas")
pytest.importorskip("exactextract")
from shapely.geometry import Point, box  # noqa: E402

from stormflow_diag import forcing  # noqa: E402

RES = 0.1
LAT = np.round(29.05 + RES * np.arange(40), 6)  # 29.05 .. 32.95
LON = np.round(-100.95 + RES * np.arange(40), 6)  # -100.95 .. -97.05
SEA = (LAT[:, None] > 32.0) & (LON[None, :] < -100.5)  # NaN block in the NW corner
DAY_NAN = (1, 10, 11)  # (day, lat index, lon index) of one extra NaN cell: 30.05 N, -99.85 E


def field(nt: int) -> np.ndarray:
    """prcp(t, lat, lon) on the ascending/-180 grid, with the NaN cells applied."""
    f = (np.arange(nt)[:, None, None] + 1.0) + 10 * (LAT[None, :, None] - 29) + (LON[None, None, :] + 101)
    f = f.astype("float32")
    f[:, SEA] = np.nan
    d, i, j = DAY_NAN
    f[d, i, j] = np.nan
    return f


def write_month(directory, month: str, lat_desc=False, lon360=False, lat=LAT) -> None:
    start = pd.Timestamp(f"{month[:4]}-{month[4:]}-01")
    f = field(start.days_in_month)
    la, lo = lat.copy(), LON.copy()
    if lat_desc:
        la, f = la[::-1], f[:, ::-1, :]
    if lon360:
        lo = lo + 360
    ds = xr.Dataset({"prcp": (("time", "lat", "lon"), f)},
                    coords={"time": pd.date_range(start, periods=len(f), freq="D"), "lat": la, "lon": lo})
    ds.to_netcdf(directory / f"EM_Earth_deterministic_daily_prcp_{month}.nc",
                 encoding={"prcp": {"zlib": True, "_FillValue": -9999.0}})


def reference(poly, f_day: np.ndarray, weighting="area") -> tuple[float, float]:
    """Brute-force weighted mean and valid fraction of one day's field (ascending grid)."""
    f_day = f_day.astype(float)
    cells = {}
    for i, la in enumerate(LAT):
        for j, lo in enumerate(LON):
            cell = box(lo - RES / 2, la - RES / 2, lo + RES / 2, la + RES / 2)
            cells[i, j] = poly.intersection(cell).area / cell.area
    top = max(cells.values())
    num = den = tot = 0.0
    for (i, j), cov in cells.items():
        if cov <= 1e-9 * top:  # round-off slivers along shared edges
            continue
        w = cov
        if weighting == "area":
            la = LAT[i]
            w *= np.sin(np.radians(la + RES / 2)) - np.sin(np.radians(la - RES / 2))
        tot += w
        if np.isfinite(f_day[i, j]):
            num += w * f_day[i, j]
            den += w
    return (num / den if den > 0 else np.nan), den / tot


POLYS = {
    1: box(-99.9, 30.0, -99.8, 30.1),  # exactly the cell 30.05 N, -99.85 E
    2: box(-99.87, 30.03, -99.86, 30.04),  # inside that cell, 1 % of it
    3: box(-99.81, 30.03, -99.79, 30.04),  # sub-cell, straddles two cells in one row
    4: box(-99.87, 30.09, -99.86, 30.11),  # sub-cell, straddles two rows
    5: box(-100.7, 31.8, -100.3, 32.2),  # partly over NaN (sea) cells
    6: box(-100.9, 32.3, -100.6, 32.6),  # entirely over NaN cells
    7: Point(-99.3, 30.7).buffer(0.37),  # irregular, many partial cells
    8: box(-98.4321, 31.2345, -98.4321 + 1e-7, 31.2345 + 1e-7),  # far below a cell
    9: Point(-99.85, 30.05).buffer(0.25),  # covers the day-1 NaN cell
}


@pytest.fixture
def polygons():
    return gpd.GeoSeries(list(POLYS.values()), index=list(POLYS.keys()), crs=4326)


@pytest.mark.parametrize("lat_desc", [False, True])
@pytest.mark.parametrize("lon360", [False, True])
def test_basin_means_match_brute_force(tmp_path, polygons, lat_desc, lon360):
    write_month(tmp_path, "200001", lat_desc=lat_desc, lon360=lon360)
    status = forcing.extract(tmp_path, polygons, tmp_path / "cache", weightings=("area", "coverage"))
    assert status == {"200001": "written"}
    out = pd.read_parquet(tmp_path / "cache" / "prcp_200001.parquet")
    assert len(out) == 31 * len(POLYS)
    f = field(31)
    for pid, poly in POLYS.items():
        for day in (0, 1, 20):
            row = out[(out.id == pid) & (out.date == pd.Timestamp("2000-01-01") + pd.Timedelta(days=day))].iloc[0]
            for w, col in forcing.WEIGHTINGS.items():
                mean, frac = reference(poly, f[day], w)
                if np.isnan(mean):
                    assert np.isnan(row[col]), (pid, day, w)
                else:
                    assert row[col] == pytest.approx(mean, rel=1e-9, abs=1e-9), (pid, day, w)
            assert row.valid_frac == pytest.approx(reference(poly, f[day])[1], abs=1e-6), (pid, day)


def test_special_polygons(tmp_path, polygons):
    write_month(tmp_path, "200001")
    forcing.extract(tmp_path, polygons, tmp_path / "cache")
    p = forcing.load(tmp_path / "cache")
    f = field(31).astype(float)
    cell = f[:, 10, 11]  # 30.05 N, -99.85 E
    # polygons 1 and 2 (whole cell, and 1 % of it) both give that cell, NaN on the NaN day
    np.testing.assert_allclose(p[1].to_numpy(), cell, rtol=1e-12)
    np.testing.assert_allclose(p[2].to_numpy(), cell, rtol=1e-12)
    # same-row straddle: the plain mean of the two cells
    np.testing.assert_allclose(p[3].to_numpy()[[0, 5]], ((f[:, 10, 11] + f[:, 10, 12]) / 2)[[0, 5]], rtol=1e-12)
    # all-sea polygon: NaN every day; far-below-a-cell polygon: its cell
    assert p[6].isna().all()
    np.testing.assert_allclose(p[8].to_numpy(), f[:, np.abs(LAT - 31.25).argmin(), np.abs(LON + 98.45).argmin()],
                               rtol=1e-12)
    # the day-1 NaN cell is dropped and the rest renormalised, other days unaffected
    assert np.isfinite(p.loc["2000-01-02", 9])


def test_extract_is_incremental(tmp_path, polygons, monkeypatch):
    for m in ("200001", "200002"):
        write_month(tmp_path, m)
    cache = tmp_path / "cache"
    assert forcing.extract(tmp_path, polygons, cache) == {"200001": "written", "200002": "written"}
    assert len(list(cache.glob("weights_*.npz"))) == 1

    # weights come from the cache now; building them again would fail
    monkeypatch.setattr(forcing, "build_weights", lambda *a, **k: pytest.fail("weights rebuilt"))
    write_month(tmp_path, "200003")
    assert forcing.extract(tmp_path, polygons, cache) == {"200001": "done", "200002": "done", "200003": "written"}
    assert forcing.cached_months(cache) == ["200001", "200002", "200003"]

    p = forcing.load(cache, ids=[1, 7])
    assert list(p.columns) == [1, 7]
    assert len(p) == 31 + 29 + 31 and p.index.is_monotonic_increasing
    assert p.index[0] == pd.Timestamp("2000-01-01") and p.index[-1] == pd.Timestamp("2000-03-31")
    assert len(forcing.load(cache, start="2000-02-01", end="2000-02-29")) == 29


def test_cloud_placeholders_and_bad_files(tmp_path, polygons, monkeypatch):
    write_month(tmp_path, "200001")
    write_month(tmp_path, "200002", lat=LAT + 0.05)  # a different grid
    monkeypatch.setattr(forcing, "is_local", lambda p: "200001" not in str(p))
    status = forcing.extract(tmp_path, polygons, tmp_path / "cache", log=lambda *a: None)
    assert status["200001"] == "cloud"
    assert status["200002"] == "written"  # weights are built on the first file processed

    status = forcing.extract(tmp_path, polygons, tmp_path / "cache", include_cloud=True, log=lambda *a: None)
    assert status["200001"].startswith("error: ValueError") and "differs from weights grid" in status["200001"]
    assert not (tmp_path / "cache" / "prcp_200001.parquet").exists()


def test_emearth_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EMEARTH_DIR", str(tmp_path))
    assert forcing.emearth_dir() == tmp_path
    assert forcing.emearth_dir(tmp_path / "x") == tmp_path / "x"
    monkeypatch.delenv("EMEARTH_DIR")
    with pytest.raises(ValueError):
        forcing.emearth_dir()
