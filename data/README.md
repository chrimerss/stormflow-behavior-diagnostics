# Data

Nothing under this folder except this README is tracked by git. Code reads data through `src/stormflow_diag/paths.py`; set `STORMFLOW_DATA` to point elsewhere.

| Folder | Source | Archive | Size (bytes) | SHA-256 | Downloaded |
|---|---|---|---:|---|---|
| `figshare/` | Figshare package for the paper (ref. 79), https://figshare.com/s/24fca5b7d89829035ff1 | `data.zip` | 4,149,492,029 | `396d022b7e835470336e588d3ff9d1b0c696599e981446e5c9ed9bb89402893e` | 2026-09-27 |
| `zenodo_14253670/` | Sharif & Ameli (2024), *Searching for Functional Simplicity of Stormflow Generation*, https://zenodo.org/records/14253670 | `timeseries.zip` | 167,867,436 | `1449a6eabb32c576580563e1b2021b0d3f1b9dc217d43b3c022972aefc75878d` | 2026-09-27 |
| | | `regression_and_spectral_analysis.zip` | 6,882,275 | `bca448504949c8d43110779a9f45c7a9821d44b83fb091c02ec0e553eeb4dc7a` | 2026-09-27 |

Locally, `figshare/` is a symlink to the unpacked `data.zip` one level above the repo. To set up from scratch, unpack `data.zip` so that `data/figshare/README.txt` exists, and download the Zenodo record into `data/zenodo_14253670/`.

## Figshare contents

- `Gauged_Catchments_Metadata_and_Attributes.csv`: 4,552 gauged catchments (GCIN), observed and predicted class per season, 27 predictors
- `Identified_Rainfall_Runoff_Events_{Dormant,Growing}.csv`: the authors' event catalogue
- `Event_Inputs.zip`: daily precipitation and streamflow (mm/day) per GCIN
- `Gauged_Catchments_Growing_Dormancy_Probability.csv`: monthly phenology value per gauge (negative = dormant, positive = growing)
- `Gauged_Catchments_Boundaries.gpkg`, `*_Ungauged_Catchments_Boundaries.gpkg`: polygons
- `Ungauged_Catchments_*.csv`: attributes and phenology for 77,585 ungauged catchments
