# Phase 2 daily streamflow

Daily mean flow for the stations in `results/phase2/station_inventory.csv`, downloaded from national agencies by

```bash
mamba run -n stormflow-diag python scripts/phase2_streamflow.py --source usgs|hydat|nrfa|hubeau
```

Only this README is tracked by git.

## Files

`streamflow/<source>/<UCIN>.parquet`, one row per calendar day from the first to the last valid day within 1950-01-01 to 2019-12-31:

| column | meaning |
|---|---|
| `date` | datetime64[ns], the day the mean refers to |
| `q_m3s` | daily mean flow in m³/s, NaN when missing |
| `q_mmd` | `q_m3s * 86.4 / Area`, where `Area` (km²) is the authors' polygon area from the inventory |
| `flag` | the provider's quality or estimate code for that day, as a string (empty when none) |

Per-station notes (series choice, regulation) are stored in the parquet metadata as pandas `attrs["note"]` and repeated in `results/phase2/streamflow_manifest.csv`. The manifest has one row per inventory station attempted, with `status` (ok, not_found, error, unmapped), record dates, `frac_missing_1979_2019` (missing share of all days 1979–2019) and `n_years_ge_300_valid_days` (calendar years 1979–2019 with at least 300 valid days). It adds `area_km2` (authors' polygon), `national_area_km2` (provider's drainage area) and `mean_q_mmd`. The note says `AREA MISMATCH` when the polygon area is outside 0.8–1.25 times the provider's area; `q_mmd` is then unreliable.

## Sources

All accessed 2026-09-27.

| source | provider and service | station ID | units and flags | terms |
|---|---|---|---|---|
| `usgs` | USGS NWIS daily values, https://waterservices.usgs.gov/nwis/dv, via `dataretrieval.nwis.get_dv` 1.3.0; parameter 00060, statistic 00003 | GSIM `reference.no` with leading zeros restored (7 digits to 8, 9 digits to 10), checked against the NWIS site service | ft³/s × 0.0283168. Flags are NWIS qualifiers joined by ", ": A approved, P provisional, e estimated, Ice, Eqp, Bkw, etc. | USGS data are in the public domain; cite USGS. Provisional (P) values may be revised. |
| `hydat` | Environment and Climate Change Canada, HYDAT national archive, `Hydat_sqlite3_20260717.zip` from https://collaboration.cmc.ec.gc.ca/cmc/hydrometrics/www/, kept in `data/hydat/` (278,852,677 bytes, SHA-256 `b05eb121a547ca4a179a27aa47c354089fd902e93e5dc1e4a5416fc4641eb298`) | GSIM `reference.no` = HYDAT `STATION_NUMBER` | m³/s from `DLY_FLOWS` (FLOW1–FLOW31). `FLOW_SYMBOL`: A partial day, B backwater (ice), D dry, E estimated, R revised. `STN_REGULATION.REGULATED = 1` is noted as "HYDAT: regulated". | ECCC Data Servers End-use Licence v2.1.1 (open use including redistribution; acknowledge ECCC as source). |
| `nrfa` | UK National River Flow Archive API, https://nrfaapps.ceh.ac.uk/nrfa/ws/time-series, data type `gdf` (gauged daily flow) | no national ID in GSIM (GRDC/EWA numbers only); position and area match, see below | m³/s; flag E = estimated | NRFA API licence (https://eidc.ceh.ac.uk/licences/nrfa-data-terms-and-conditions-for-api-access-to-time-series-data-and-metadata/) clause 3.5 allows only temporary storage (≤ 30 days) of unmodified data. **No NRFA series are kept here.** Acknowledge "Data from the UK National River Flow Archive". |
| `hubeau` | Hub'Eau hydrométrie v2, https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab, `grandeur_hydro_elab=QmnJ` (daily mean flow), data from HydroPortail / SCHAPI | GSIM FR rows: 8-character site code from the position and area match below. CAMELS-FR rows: the 10-character station code in `Source ID` | l/s ÷ 1000. A site code returns the site series and its stations' series; the site series is kept. Flag = qualification/méthode/statut, e.g. `Bonne/Expertisée/Donnée validée` | Licence Ouverte Etalab (free reuse with attribution); Hub'Eau asks users to download only the subset they need. |

## Matching GSIM stations without a national ID (GB, FR)

GSIM gives only GRDC or EWA numbers for Great Britain and France, and neither provider API carries those numbers. A GSIM station is mapped to a national station when the national station lies within 5 km of the GSIM coordinates and its catchment area is within 1 % (NRFA) or 2 % (Hub'Eau site `surface_bv`) of the area GSIM reports (the agencies supplied that area to GRDC/EWA; NRFA areas usually agree to 0.1 km²). If several qualify, the nearest is used only when the next is at least 3 times farther; otherwise the station is unmapped. Names are never used to make a match. A match is rejected when no word of the GSIM river name resembles (similarity ≥ 0.8) a word of the national station name, which catches wrong GSIM coordinates. The mapping tables are `results/phase2/streamflow_mapping_{nrfa,hubeau}.csv`.

## Authors' gauged US stations (cross-check)

`streamflow/usgs_gauged/<GCIN>.parquet`: the same USGS NWIS series for the 681 gauged catchments with Source ID `GSIM_US_*`, same columns, with `q_mmd` from the authors' `Area` for that GCIN. Written by `scripts/phase2_us_gauged_streamflow.py`, which compares them with `streamflow_mmd` in `Event_Inputs/<GCIN>.csv` (`results/phase2/us_streamflow_vs_authors.csv`).

## EM-Earth basin-mean precipitation

`forcing/emearth/<set>/prcp_YYYYMM.parquet`, one file per EM-Earth month (`EM_Earth_deterministic_daily_prcp_YYYYMM.nc`), long format: `id` (UCIN or GCIN), `date`, `prcp_mmd` (area-weighted mean over the polygon, mm/day), `prcp_mmd_coverage` (coverage-fraction weights only; `us_gauged` only) and `valid_frac` (share of the polygon's weight with data that day). Sets: `us_validation` (UCIN polygons of the US validation set) and `us_gauged` (the authors' `GSIM_US_*` gauged polygons, for the check against their `precipitation_mmd`). `weights_<hash>.npz` caches the exactextract coverage fractions, `grid.txt` the grid they belong to, `extract_status.json` the last status of each month. Written by `scripts/phase2_emearth.py` (see `src/stormflow_diag/forcing.py` for the method).
