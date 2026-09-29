"""Crop global EM-Earth monthly files to a North America window, verify, and
optionally delete the global original to free disk space.

  python scripts/phase2_crop_emearth.py --src DIR --dst DIR [--delete] [--workers N] [--months YYYYMM ...]

Window: 157 W - 65 W, 17.5 N - 60.5 N (the union of the US, Puerto Rico and
Canadian catchment polygons, gauged and station-based ungauged, plus margin,
extended north to 60.5 N for British Columbia). Both precipitation variables
(prcp, prcp_corrected) are kept, float32, zlib-compressed.

For each month: read the window from the original, write it to
<dst>/<same file name> through a temporary file, reopen the copy and check
that every value of both variables equals the original window (NaN == NaN)
and that there is one time step per day. Only then, with --delete, is the
original removed. A manifest (<dst>/crop_manifest.csv) records each month.
Months whose cropped copy already exists and verifies are not rewritten, so
the script can be rerun after an interruption.
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from stormflow_diag.forcing import FILE_RE

LON = (-157.0, -65.0)
LAT = (17.5, 60.5)
VARIABLES = ("prcp", "prcp_corrected")


def _window(ds) -> xr.Dataset:
    lat_desc = ds.lat[0] > ds.lat[-1]
    lat_sel = slice(LAT[1], LAT[0]) if lat_desc else slice(*LAT)
    return ds[list(VARIABLES)].sel(lat=lat_sel, lon=slice(*LON))


def _same(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and np.array_equal(a, b, equal_nan=True)


def crop_one(src: Path, dst_dir: Path, delete: bool) -> dict:
    t0 = time.time()
    month = FILE_RE.search(src.name).group(1)
    dst = dst_dir / src.name
    row = {"month": month, "src_bytes": src.stat().st_size, "dst": str(dst)}
    with xr.open_dataset(src, decode_times=True, mask_and_scale=False) as ds:
        win = _window(ds).load()
    expected_days = pd.Timestamp(f"{month[:4]}-{month[4:]}-01").days_in_month
    if win.sizes["time"] != expected_days:
        raise ValueError(f"{src.name}: {win.sizes['time']} days, expected {expected_days}")

    if not dst.exists():
        enc = {v: {"zlib": True, "complevel": 4, "shuffle": True,
                   "chunksizes": (1, win.sizes["lat"], win.sizes["lon"])} for v in VARIABLES}
        tmp = dst_dir / f".{src.name}.tmp"
        win.to_netcdf(tmp, encoding=enc, format="NETCDF4")
        os.replace(tmp, dst)

    with xr.open_dataset(dst, decode_times=True, mask_and_scale=False) as chk:
        ok = (chk.sizes["time"] == expected_days
              and np.array_equal(chk.time.values, win.time.values)
              and np.allclose(chk.lat.values, win.lat.values) and np.allclose(chk.lon.values, win.lon.values)
              and all(_same(chk[v].values, win[v].values) for v in VARIABLES))
    row.update(dst_bytes=dst.stat().st_size, n_days=expected_days, n_lat=win.sizes["lat"],
               n_lon=win.sizes["lon"], verified=ok, deleted=False)
    if not ok:
        dst.unlink()
        raise ValueError(f"{src.name}: cropped copy does not match the original window; copy removed")
    if delete:
        src.unlink()
        row["deleted"] = True
    row["seconds"] = round(time.time() - t0, 1)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--delete", action="store_true", help="remove each original after its copy verifies")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--months", nargs="+")
    a = ap.parse_args()
    src_dir, dst_dir = Path(a.src), Path(a.dst)
    dst_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in src_dir.iterdir() if FILE_RE.search(p.name))
    if a.months:
        files = [p for p in files if FILE_RE.search(p.name).group(1) in set(a.months)]
    manifest = dst_dir / "crop_manifest.csv"
    log = dst_dir / "crop_log.csv"  # one line per attempt, appended as months finish
    print(f"{len(files)} files to crop into {dst_dir} (delete originals: {a.delete})", flush=True)

    rows = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(crop_one, p, dst_dir, a.delete): p for p in files}
        for i, f in enumerate(as_completed(futs), 1):
            p = futs[f]
            try:
                r = f.result()
                print(f"[{i}/{len(files)}] {r['month']}: {r['src_bytes']/1e6:.0f} -> {r['dst_bytes']/1e6:.0f} MB, "
                      f"verified, {'deleted' if r['deleted'] else 'kept'} original, {r['seconds']}s", flush=True)
            except Exception as e:  # noqa: BLE001 - keep going; the month stays for a rerun
                r = {"month": FILE_RE.search(p.name).group(1), "error": f"{type(e).__name__}: {e}"}
                print(f"[{i}/{len(files)}] {r['month']}: ERROR {r['error']}", flush=True)
            rows.append(r)
            pd.DataFrame([r]).to_csv(log, index=False, mode="a", header=not log.exists())
    out = pd.read_csv(log, dtype={"month": str}).drop_duplicates("month", keep="last")
    out.sort_values("month").to_csv(manifest, index=False)
    n_err = int(out.get("error", pd.Series(dtype=object)).notna().sum())
    print(f"done: {len(rows)} processed this run; manifest has {len(out)} months, {n_err} with errors", flush=True)


if __name__ == "__main__":
    main()
