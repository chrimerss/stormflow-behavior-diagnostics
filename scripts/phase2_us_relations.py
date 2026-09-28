"""Phase 2: where the US validation catchments sit relative to the gauged (training) catchments.

  python scripts/phase2_us_relations.py

For each US validation station (streamflow_manifest usgs/ok, >= 10 years with
>= 300 valid days, polygon 0.8-1.25x the USGS drainage area) the UCIN polygon
is compared with all 4,552 gauged polygons of the authors. Classes, first
that applies:

- nested:      >= 90 % of the validation polygon lies inside one gauged polygon
- contains:    >= 90 % of some gauged polygon lies inside the validation polygon
- overlapping: gauged polygons cover > 5 % of the validation polygon
- adjacent:    a gauged polygon within 10 km (boundary to boundary), overlap <= 5 %
- independent: no gauged polygon within 10 km

`relation_gcin` is the gauged catchment behind the class (tightest container,
largest contained, largest overlap, or nearest). `same_catchment` marks mutual
>= 90 % overlap, i.e. effectively the same basin as a gauged one. Areas are in
EPSG:5070 (Albers equal-area; equal-area everywhere, so also for HI and PR).
Distances are exact to within projection error of a local azimuthal
equidistant projection centred on each validation polygon; candidates come
from EPSG:5070 with a 25 % + 10 km margin. Distance is 0 where polygons
touch or overlap; the nearest gauged GCIN is then the one with the largest
overlap.

Writes results/phase2/us_validation_relations.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shapely

from stormflow_diag import forcing, paths
from stormflow_diag import streamflow as sf
from stormflow_diag.predict import training_ids

OUT_CSV = paths.RESULTS / "phase2" / "us_validation_relations.csv"
EA = "EPSG:5070"
NEST, CONTAIN, OVERLAP, NEAR_KM = 0.90, 0.90, 0.05, 10.0
CLASSES = ["nested", "contains", "overlapping", "adjacent", "independent"]


def _valid(gs):
    bad = ~gs.is_valid
    if bad.any():
        gs = gs.copy()
        gs[bad] = gs[bad].make_valid()
    return gs


def exact_distances(v_geom_ll, g_ll) -> np.ndarray:
    """Boundary-to-boundary distances (km) in an azimuthal equidistant projection
    centred on the validation polygon."""
    c = v_geom_ll.centroid
    aeqd = f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m"
    import geopandas as gpd

    v = gpd.GeoSeries([v_geom_ll], crs=4326).to_crs(aeqd).iloc[0]
    g = g_ll.to_crs(aeqd)
    return shapely.distance(v, g.to_numpy()) / 1000


def main() -> None:
    val = sf.validation_set("usgs")
    print(f"{len(val)} US validation stations")
    vpoly = forcing.boundaries("ungauged", val.UCIN)
    gpoly = forcing.boundaries("gauged")
    train = training_ids()

    V = _valid(vpoly.geometry.to_crs(EA))
    G = _valid(gpoly.geometry.to_crs(EA))
    va, ga = V.area.to_numpy(), G.area.to_numpy()
    gids = G.index.to_numpy()

    # overlaps
    vi, gi = G.sindex.query(V.to_numpy(), predicate="intersects")
    inter = shapely.intersection(V.to_numpy()[vi], G.to_numpy()[gi])
    ov = pd.DataFrame({"v": vi, "g": gi, "ia": shapely.area(inter)})
    ov["fv"] = ov.ia / va[ov.v]  # share of the validation polygon inside the gauged one
    ov["fg"] = ov.ia / ga[ov.g]  # share of the gauged polygon inside the validation one
    ov = ov[ov.ia > 0]
    union = {v: shapely.area(shapely.union_all(inter[idx])) / va[v]
             for v, idx in pd.Series(np.arange(len(vi))).groupby(vi).groups.items()}

    # nearest by boundary distance: candidates from EA, exact distance in local AEQD
    near_i, near_d = G.sindex.nearest(V.to_numpy(), return_distance=True, return_all=False)
    coarse = pd.Series(near_d, index=near_i[0])

    rows = []
    for k, (ucin, geom_ll) in enumerate(vpoly.geometry.items()):
        o = ov[ov.v == k]
        r = {"UCIN": ucin, "area_km2": va[k] / 1e6, "n_gauged_intersecting": len(o),
             "overlap_frac_total": union.get(k, 0.0), "max_frac_in_gauged": o.fv.max() if len(o) else 0.0,
             "n_gauged_contained": int((o.fg >= CONTAIN).sum())}
        if len(o):  # touching/overlapping: distance 0, nearest = largest overlap
            best = o.loc[o.ia.idxmax()]
            r["nearest_gcin"], r["nearest_dist_km"] = gids[int(best.g)], 0.0
        else:
            d0 = coarse[k]
            cand = G.sindex.query(V.iloc[k], predicate="dwithin", distance=1.25 * d0 + 10_000)
            d = exact_distances(geom_ll, gpoly.geometry.iloc[cand])
            j = int(np.argmin(d))
            r["nearest_gcin"], r["nearest_dist_km"] = gids[cand[j]], float(d[j])

        nested = o[o.fv >= NEST]
        contained = o[o.fg >= CONTAIN]
        if len(nested):
            rel, g = "nested", nested.loc[nested.fg.idxmax()]  # tightest container
        elif len(contained):
            rel, g = "contains", contained.loc[contained.fv.idxmax()]  # largest contained
        elif r["overlap_frac_total"] > OVERLAP:
            rel, g = "overlapping", o.loc[o.ia.idxmax()]
        else:
            rel, g = ("adjacent" if r["nearest_dist_km"] <= NEAR_KM else "independent"), None
        r["relation"] = rel
        if g is not None:
            r.update(relation_gcin=gids[int(g.g)], relation_frac_val_in_gauged=g.fv, relation_frac_gauged_in_val=g.fg)
        else:
            r["relation_gcin"] = r["nearest_gcin"]
        r["same_catchment"] = bool(((o.fv >= NEST) & (o.fg >= CONTAIN)).any())
        rows.append(r)
    res = pd.DataFrame(rows)

    meta = gpoly[["dormant_gauged_class", "growing_gauged_class", "Catchment_Boundary_Flagged", "Source.ID"]]
    for who in ("nearest", "relation"):
        m = meta.reindex(res[f"{who}_gcin"].to_numpy())
        res[f"{who}_source_id"] = m["Source.ID"].to_numpy()
        res[f"{who}_dormant_gauged_class"] = m.dormant_gauged_class.to_numpy()
        res[f"{who}_growing_gauged_class"] = m.growing_gauged_class.to_numpy()
        res[f"{who}_flagged"] = m.Catchment_Boundary_Flagged.to_numpy()
        for s in ("dormant", "growing"):
            res[f"{who}_in_train_{s}"] = res[f"{who}_gcin"].isin(train[s])

    res = val[["UCIN", "Source ID", "national_id", "dormant_predicted_class", "growing_predicted_class",
               "n_years_ge_300_valid_days"]].merge(res, on="UCIN")
    res["relation"] = pd.Categorical(res.relation, CLASSES)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT_CSV, index=False, float_format="%.6g")

    print(pd.crosstab(res.relation, res.dormant_predicted_class, margins=True).to_string())
    print(f"\nsame catchment as a gauged polygon: {res.same_catchment.sum()}")
    print(f"nearest gauged in dormant training set: {res.nearest_in_train_dormant.sum()}")
    print(res.groupby("relation", observed=False).nearest_dist_km.describe().to_string())


if __name__ == "__main__":
    main()
