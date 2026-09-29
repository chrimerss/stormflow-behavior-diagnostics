"""Basin-mean daily precipitation from EM-Earth.

EM-Earth (Tang et al. 2022) deterministic daily precipitation comes as one
NetCDF file per month, ``EM_Earth_deterministic_daily_prcp_YYYYMM.nc``, on a
global 0.1 degree grid (variable ``prcp``, mm/day, NaN over sea). The EM-Earth
directory is given as an argument or by the environment variable EMEARTH_DIR.

Weights
-------
exactextract gives, for each polygon, the grid cells it touches and the
fraction of each cell it covers. This is computed once per polygon set and
grid, on a window of the grid that holds all polygons, and cached to disk as a
sparse matrix W (polygons x window cells). The weight of a cell is

- ``area``: coverage fraction x cell area (sin(lat_top) - sin(lat_bottom)),
  the area-weighted mean over the polygon (default);
- ``coverage``: coverage fraction only, the plain exactextract ``mean`` on a
  geographic grid.

The basin mean on day t is ``sum_j W_pj x_tj / sum_j W_pj [x_tj is not NaN]``:
NaN cells (sea, missing) drop out and the weights are renormalised each day.
``valid_frac`` is the share of the polygon's weight that had data that day.
A polygon smaller than one cell gets the one or few cells it lies in, with
their coverage fractions; a polygon for which exactextract returns no cell
(degenerate geometry) gets the cell holding its representative point.

Output
------
``extract`` writes one parquet per month, ``<cache_dir>/prcp_YYYYMM.parquet``,
with columns id, date, prcp_mmd (area weights), optionally
prcp_mmd_coverage, and valid_frac, and skips months already written, so it can
be rerun while files arrive. Cloud-only placeholder files (macOS File Provider,
e.g. OneDrive "online-only") are skipped unless ``include_cloud`` is set,
because opening one starts a download.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from stormflow_diag import paths

FILE_RE = re.compile(r"EM_Earth_deterministic_daily_prcp_(\d{6})\.nc$")
WEIGHTINGS = {"area": "prcp_mmd", "coverage": "prcp_mmd_coverage"}


def column(var: str = "prcp", weighting: str = "area") -> str:
    """Output column for a variable and weighting: prcp_mmd, prcp_corrected_mmd_coverage, ..."""
    return f"{var}_mmd" + ("_coverage" if weighting == "coverage" else "")
SF_DATALESS = 0x40000000  # macOS st_flags bit of a cloud-only placeholder
MIN_COVERAGE = 1e-9  # relative to the polygon's largest coverage; drops exactextract round-off slivers


# ---------------------------------------------------------------------------
# polygons
# ---------------------------------------------------------------------------
def boundaries(kind: str, ids=None):
    """The authors' catchment polygons (EPSG:4326) indexed by GCIN or UCIN.

    kind: "gauged" (Gauged_Catchments_Boundaries.gpkg) or "ungauged"
    (63434619_Ungauged_Catchments_Boundaries.gpkg). ``ids`` restricts the read.
    """
    import geopandas as gpd

    path, key = {"gauged": (paths.GAUGED_BOUNDARIES, "GCIN"),
                 "ungauged": (paths.UNGAUGED_BOUNDARIES, "UCIN")}[kind]
    where = None
    if ids is not None:
        ids = sorted({int(i) for i in ids})
        where = f"{key} IN ({','.join(map(str, ids))})"
    g = gpd.read_file(path, where=where, engine="pyogrio")
    g[key] = g[key].astype(int)
    g = g.set_index(key).sort_index()
    if ids is not None and len(g) != len(ids):
        missing = sorted(set(ids) - set(g.index))
        raise KeyError(f"{len(missing)} {key}s have no polygon, e.g. {missing[:5]}")
    return g


# ---------------------------------------------------------------------------
# grid
# ---------------------------------------------------------------------------
def _names(ds, var: str | None = None) -> tuple[str, str, str, str]:
    """(variable, time dimension, lat, lon) names in an EM-Earth-like dataset."""
    pool = set(ds.variables) | set(ds.dims)
    lat = next(n for n in ("lat", "latitude", "y") if n in pool)
    lon = next(n for n in ("lon", "longitude", "x") if n in pool)
    if var is None:
        var = "prcp" if "prcp" in ds.data_vars else next(v for v in ds.data_vars if ds[v].ndim == 3)
    tdim = next(d for d in ds[var].dims if d not in (lat, lon))
    return var, tdim, lat, lon


@dataclass
class Grid:
    """Regular lat/lon grid of cell centres as stored in the file (either lat order)."""
    lat: np.ndarray
    lon: np.ndarray

    def __post_init__(self):
        self.lat = self._regular("lat", self.lat)
        self.lon = self._regular("lon", self.lon)
        self.dlat = abs(self.lat[1] - self.lat[0])
        self.dlon = self.lon[1] - self.lon[0]
        if self.dlon <= 0:
            raise ValueError("longitude must increase")

    @staticmethod
    def _regular(name, c) -> np.ndarray:
        """Check a regular spacing and snap to it. EM-Earth stores float32
        coordinates, whose steps scatter by ~1e-5 degrees around 0.1."""
        c = np.asarray(c, dtype=float)
        if c.size < 2:
            raise ValueError(f"{name} is not a regular grid")
        # snap to the nominal lattice (step to 1e-6 deg, origin to 1e-4 deg) so a
        # cropped window and the global grid give identical cell edges
        step = round((c[-1] - c[0]) / (c.size - 1), 6)
        exact = round(c[0], 4) + step * np.arange(c.size)
        if np.abs(c - exact).max() > 1e-3 * abs(step):
            raise ValueError(f"{name} is not a regular grid")
        return np.round(exact, 9)

    @classmethod
    def from_file(cls, path) -> "Grid":
        import xarray as xr

        with xr.open_dataset(path, decode_times=False) as ds:
            _, _, lat, lon = _names(ds)
            return cls(ds[lat].to_numpy(), ds[lon].to_numpy())

    @property
    def lat_ascending(self) -> bool:
        return self.lat[1] > self.lat[0]

    @property
    def lon_360(self) -> bool:
        return self.lon.max() > 180 + self.dlon

    def signature(self) -> str:
        return (f"lat {self.lat[0]:.6f}:{self.lat[-1]:.6f}:{self.lat.size} "
                f"lon {self.lon[0]:.6f}:{self.lon[-1]:.6f}:{self.lon.size}")

    def row_range(self, south: float, north: float) -> tuple[int, int]:
        """File row slice [r0, r1) whose cells overlap [south, north], one cell of padding."""
        edges_lo = self.lat - self.dlat / 2
        edges_hi = self.lat + self.dlat / 2
        rows = np.flatnonzero((edges_hi >= south - self.dlat) & (edges_lo <= north + self.dlat))
        return int(rows.min()), int(rows.max()) + 1

    def col_range(self, west: float, east: float) -> tuple[int, int]:
        cols = np.flatnonzero((self.lon + self.dlon / 2 >= west - self.dlon)
                              & (self.lon - self.dlon / 2 <= east + self.dlon))
        return int(cols.min()), int(cols.max()) + 1


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------
@dataclass
class Weights:
    """Coverage fractions of polygons (rows) over the cells of a grid window.

    Window cells are numbered in file order, row-major: (file_row - r0) *
    ncols + (file_col - c0), so ``prcp[:, r0:r1, c0:c1].reshape(nt, -1)``
    lines up with the columns of ``coverage``.
    """
    ids: np.ndarray
    coverage: sp.csr_matrix
    window: tuple[int, int, int, int]  # r0, r1, c0, c1 in file indices
    lat: np.ndarray  # cell-centre latitude of each window row
    dlat: float
    grid_signature: str
    fallback_ids: np.ndarray  # polygons given their representative-point cell

    def matrix(self, weighting: str = "area") -> sp.csr_matrix:
        if weighting == "coverage":
            return self.coverage
        if weighting != "area":
            raise ValueError(f"unknown weighting {weighting!r}")
        lat = np.radians(self.lat)
        half = np.radians(self.dlat) / 2
        band = np.sin(np.minimum(lat + half, np.pi / 2)) - np.sin(np.maximum(lat - half, -np.pi / 2))
        ncols = self.window[3] - self.window[2]
        return (self.coverage @ sp.diags(np.repeat(band, ncols))).tocsr()

    def save(self, path: Path) -> None:
        c = self.coverage
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, ids=self.ids, data=c.data, indices=c.indices, indptr=c.indptr,
                            shape=np.array(c.shape), window=np.array(self.window), lat=self.lat,
                            dlat=self.dlat, grid_signature=self.grid_signature, fallback_ids=self.fallback_ids)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "Weights":
        z = np.load(path, allow_pickle=False)
        cov = sp.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=tuple(z["shape"]))
        return cls(z["ids"], cov, tuple(int(v) for v in z["window"]), z["lat"], float(z["dlat"]),
                   str(z["grid_signature"]), z["fallback_ids"])


def _polygonal(g):
    import shapely

    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = [p for p in shapely.get_parts(g) if p.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else g


def _to_grid_lon(geoms, grid: Grid):
    """Shift polygons west of 0 by +360 when the grid runs 0-360."""
    from shapely import affinity

    if not grid.lon_360:
        return geoms
    b = geoms.bounds
    if ((b.minx < 0) & (b.maxx > 0)).any():
        raise NotImplementedError("polygon crosses 0 deg longitude on a 0-360 grid")
    return geoms.where(b.maxx > 0, geoms.map(lambda g: affinity.translate(g, xoff=360)))


def build_weights(polygons, grid: Grid) -> Weights:
    """exactextract coverage fractions for ``polygons`` (GeoSeries/GeoDataFrame in
    EPSG:4326, index = ids) on ``grid``."""
    import geopandas as gpd
    from exactextract import exact_extract
    from exactextract.raster import NumPyRasterSource

    geoms = polygons.geometry if hasattr(polygons, "geometry") else polygons
    if geoms.crs is not None and geoms.crs.to_epsg() != 4326:
        geoms = geoms.to_crs(4326)
    bad = ~geoms.is_valid
    if bad.any():  # repair, keeping only the polygonal parts
        geoms = geoms.copy()
        geoms[bad] = geoms[bad].make_valid().map(_polygonal)
    geoms = _to_grid_lon(geoms, grid)
    west, south, east, north = geoms.total_bounds
    r0, r1 = grid.row_range(south, north)
    c0, c1 = grid.col_range(west, east)
    nr, nc = r1 - r0, c1 - c0

    # north-up raster of zeros over the window (exactextract drops NaN cells, so no NaN here)
    lat_w = grid.lat[r0:r1]
    top = lat_w.max() + grid.dlat / 2
    bottom = lat_w.min() - grid.dlat / 2
    left = grid.lon[c0] - grid.dlon / 2
    right = grid.lon[c1 - 1] + grid.dlon / 2
    gdf = gpd.GeoDataFrame(geometry=geoms.reset_index(drop=True), crs=4326)
    rast = NumPyRasterSource(np.zeros((nr, nc)), left, bottom, right, top, srs_wkt=gdf.crs.to_wkt())
    ex = exact_extract(rast, gdf, ["cell_id", "coverage"], output="pandas", strategy="feature-sequential")

    rows, cols, vals, fallback = [], [], [], []
    for p, (cid, cov) in enumerate(zip(ex["cell_id"], ex["coverage"])):
        cid = np.asarray(cid, dtype=np.int64)
        cov = np.asarray(cov, dtype=float)
        keep = cov > MIN_COVERAGE * (cov.max() if cov.size else 0)
        cid, cov = cid[keep], cov[keep]
        if cid.size == 0:  # degenerate polygon: cell of its representative point
            pt = geoms.iloc[p].representative_point()
            rr = int(np.argmin(np.abs(lat_w - pt.y)))
            cc = int(np.argmin(np.abs(grid.lon[c0:c1] - pt.x)))
            cid = np.array([(rr if not grid.lat_ascending else nr - 1 - rr) * nc + cc])
            cov = np.array([1.0])
            fallback.append(geoms.index[p])
        rr, cc = np.divmod(cid, nc)  # raster rows run north to south
        if grid.lat_ascending:
            rr = nr - 1 - rr
        rows.append(np.full(cid.size, p))
        cols.append(rr * nc + cc)
        vals.append(cov)
    cov = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(len(geoms), nr * nc))
    return Weights(np.asarray(geoms.index, dtype=np.int64), cov, (r0, r1, c0, c1), lat_w.copy(), grid.dlat,
                   grid.signature(), np.asarray(fallback, dtype=np.int64))


def cached_weights(polygons, grid: Grid, cache_dir: Path, log=print) -> Weights:
    """build_weights, cached in cache_dir/weights_<hash>.npz keyed on grid and polygons."""
    import shapely

    geoms = polygons.geometry if hasattr(polygons, "geometry") else polygons
    h = hashlib.sha1(grid.signature().encode())
    h.update(np.asarray(geoms.index, dtype=np.int64).tobytes())
    for wkb in shapely.to_wkb(geoms.to_numpy()):
        h.update(wkb)
    path = Path(cache_dir) / f"weights_{h.hexdigest()[:16]}.npz"
    if path.exists():
        return Weights.load(path)
    t0 = time.time()
    w = build_weights(polygons, grid)
    path.parent.mkdir(parents=True, exist_ok=True)
    w.save(path)
    log(f"weights for {len(w.ids)} polygons on window {w.window} built in {time.time() - t0:.0f}s -> {path.name}"
          + (f"; {len(w.fallback_ids)} polygons got their representative-point cell" if len(w.fallback_ids) else ""))
    return w


# ---------------------------------------------------------------------------
# basin means
# ---------------------------------------------------------------------------
def basin_means(field: np.ndarray, W: sp.csr_matrix) -> tuple[np.ndarray, np.ndarray]:
    """Weighted means of ``field`` (nt, window rows, window cols) per polygon, NaN cells
    excluded and weights renormalised per day. Returns (means, valid_frac), each (nt, n_poly)."""
    x = np.asarray(field, dtype=float).reshape(field.shape[0], -1)
    ok = np.isfinite(x)
    num = (W @ np.where(ok, x, 0.0).T).T
    den = (W @ ok.T.astype(float)).T
    total = np.asarray(W.sum(axis=1)).ravel()
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(den > 0, num / den, np.nan)
        frac = den / total
    return mean, frac


def read_month(path, weights: Weights, variables=("prcp",)) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    """Dates and, per variable, the window (nt, rows, cols) of one monthly file."""
    import xarray as xr

    month = FILE_RE.search(Path(path).name).group(1)
    r0, r1, c0, c1 = weights.window
    with xr.open_dataset(path, decode_times=False, mask_and_scale=True) as ds:
        _, tdim, lat, lon = _names(ds, variables[0])
        g = Grid(ds[lat].to_numpy(), ds[lon].to_numpy())
        if g.signature() != weights.grid_signature:
            raise ValueError(f"{Path(path).name}: grid {g.signature()} differs from weights grid "
                             f"{weights.grid_signature}")
        fields = {v: ds[v].isel({lat: slice(r0, r1), lon: slice(c0, c1)}).transpose(tdim, lat, lon)
                  .to_numpy().astype(float) for v in variables}
    nt = next(iter(fields.values())).shape[0]
    start = pd.Timestamp(f"{month[:4]}-{month[4:]}-01")
    if nt != start.days_in_month:
        raise ValueError(f"{Path(path).name}: {nt} time steps, expected {start.days_in_month}")
    return pd.date_range(start, periods=nt, freq="D"), fields


def month_frame(dates, fields, weights: Weights, weightings=("area",)) -> pd.DataFrame:
    """Long table (id, date, one column per variable and weighting, valid_frac) for one month.

    ``fields`` is {variable: array} as from read_month, or a single prcp array.
    """
    if not isinstance(fields, dict):
        fields = {"prcp": fields}
    out = pd.DataFrame({"id": np.repeat(weights.ids, len(dates)),
                        "date": np.tile(np.asarray(dates, dtype="datetime64[ns]"), len(weights.ids))})
    frac = None
    for var, field in fields.items():
        for w in weightings:
            mean, f = basin_means(field, weights.matrix(w))
            out[column(var, w)] = mean.T.ravel()
            frac = f if frac is None else frac
    out["valid_frac"] = frac.T.ravel().astype("float32")
    return out


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def emearth_dir(path=None) -> Path:
    path = path or os.environ.get("EMEARTH_DIR")
    if not path:
        raise ValueError("give the EM-Earth directory as an argument or set EMEARTH_DIR")
    return Path(path).expanduser()


def is_local(path) -> bool:
    """False for a cloud-only placeholder (reading it would start a download)."""
    st = os.stat(path)
    if getattr(st, "st_flags", 0) & SF_DATALESS:
        return False
    return st.st_size == 0 or getattr(st, "st_blocks", 1) > 0


def month_files(directory) -> dict[str, Path]:
    """{YYYYMM: path} of the monthly EM-Earth files in ``directory``."""
    out = {}
    for p in Path(directory).iterdir():
        m = FILE_RE.search(p.name)
        if m:
            out[m.group(1)] = p
    return dict(sorted(out.items()))


def extract(directory, polygons, cache_dir, weightings=("area",), months=None, include_cloud=False,
            overwrite=False, log=print, variables=("prcp",)) -> dict[str, str]:
    """Basin means for every monthly file in ``directory`` not yet in ``cache_dir``.

    polygons: GeoDataFrame/GeoSeries in EPSG:4326 indexed by id. months: optional
    iterable of YYYYMM to restrict to. Returns {YYYYMM: status}, status one of
    written, done (already there), cloud (placeholder skipped) or "error: ...".
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    files = month_files(directory)
    if months is not None:
        files = {m: p for m, p in files.items() if m in set(months)}
    status, todo = {}, {}
    for m, p in files.items():
        if (cache_dir / f"prcp_{m}.parquet").exists() and not overwrite:
            status[m] = "done"
        elif not include_cloud and not is_local(p):
            status[m] = "cloud"
        else:
            todo[m] = p
    weights = None
    grid_file = cache_dir / "grid.txt"  # every month in one cache must share the grid
    for m, p in todo.items():
        t0 = time.time()
        try:
            if weights is None:
                grid = Grid.from_file(p)
                if grid_file.exists() and grid_file.read_text() != grid.signature():
                    raise ValueError(f"{p.name}: grid {grid.signature()} differs from weights grid "
                                     f"{grid_file.read_text()}")
                weights = cached_weights(polygons, grid, cache_dir, log)
                grid_file.write_text(grid.signature())
            dates, fields = read_month(p, weights, variables)
            df = month_frame(dates, fields, weights, weightings)
            tmp = cache_dir / f".prcp_{m}.parquet.tmp"
            df.to_parquet(tmp, index=False)
            os.replace(tmp, cache_dir / f"prcp_{m}.parquet")
            status[m] = "written"
            log(f"{m}: {len(weights.ids)} basins, {time.time() - t0:.1f}s")
        except Exception as e:  # noqa: BLE001 - e.g. a file still downloading; retried next run
            status[m] = f"error: {type(e).__name__}: {e}"
            log(f"{m}: {status[m]}")
    return status


def load(cache_dir, ids=None, column: str = "prcp_mmd", start=None, end=None) -> pd.DataFrame:
    """Cached basin means as a wide table (index date, one column per id)."""
    files = sorted(Path(cache_dir).glob("prcp_??????.parquet"))
    if start is not None or end is not None:
        lo = pd.Timestamp(start or "1800-01-01").strftime("%Y%m")
        hi = pd.Timestamp(end or "2200-01-01").strftime("%Y%m")
        files = [f for f in files if lo <= f.stem[-6:] <= hi]
    if not files:
        return pd.DataFrame()
    filters = [("id", "in", [int(i) for i in ids])] if ids is not None else None
    df = pd.concat([pd.read_parquet(f, columns=["id", "date", column], filters=filters) for f in files],
                   ignore_index=True)
    wide = df.pivot(index="date", columns="id", values=column).sort_index()
    if start is not None or end is not None:
        wide = wide.loc[start:end]
    return wide


def cached_months(cache_dir) -> list[str]:
    return sorted(f.stem[-6:] for f in Path(cache_dir).glob("prcp_??????.parquet"))


def write_manifest(cache_dir, status: dict[str, str]) -> None:
    """Record the last run's per-month status next to the cache."""
    path = Path(cache_dir) / "extract_status.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    old.update(status)
    path.write_text(json.dumps(dict(sorted(old.items())), indent=0))
