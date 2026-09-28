---
title: Plan
nav_order: 3
---

# Diagnostic plan

## Phase 0: reproduce the labelling step (go/no-go)

Rebuild the authors' gauged-catchment labelling in Python and run two checks.

- **Event detection.** Port DMCA-ESR (Giani et al. 2022; reference MATLAB at https://github.com/giuliagiani/DMCA-ESR) with R_min = 1.2 mm/d and L_max = 16 d. Filters: runoff ratio ≤ 1, events 1–15 days long, at least 15 events per season. Seasons from MODIS phenology (`*_Growing_Dormancy_Probability.csv`: negative = dormant, positive = growing).
- **Regression.** For each catchment and season, OLS of event stormflow volume on event rainfall volume, plus segmented regression with up to two breakpoints tested by the score test (R `segmented`, Muggeo 2016, via rpy2). Rule from Methods:
  - simple: linear R² ≥ 0.75
  - intermediate: 0.50 ≤ linear R² < 0.75, or segmented R² ≥ 0.75
  - complex: linear R² < 0.50 and segmented R² < 0.75
- **Check A (regression only).** Feed in their event catalogue and compare our labels with theirs.
- **Check B (event detection).** Start from the raw daily series (`Event_Inputs/`) and compare our events with their catalogue, then our labels with theirs.
- **Go threshold.** ≥ 95 % label agreement on ~300 gauges, including all 210 dormant-season simple gauges. If the labels do not reproduce, stop and report; that is a finding in its own right.

## Phase 1: checks that need no new data

- Run the 246 boundary-flagged gauges through the authors' models and compare with their observed labels.
- Check the catchment Area values against the GSIM catalogue.

## Phase 2: main validation set (~15,000 gauges)

- Map GSIM IDs to national station IDs with the GSIM catalogue.
- Download daily streamflow, starting with sources rich in predicted-simple gauges that allow bulk download:

| Source | Gauges | Predicted simple |
|---|---:|---:|
| US: USGS NWIS (`dataretrieval`) | 3,636 | 139 |
| CA: HYDAT sqlite | 169 | 104 |
| ES: CEDEX Anuario de Aforos | 1,130 | 101 |
| AU: BoM Water Data Online | 2,550 | 68 |
| BR: ANA HidroWeb | 3,174 | 50 |
| JP: MLIT (hard; GRDC fallback) | 527 | 43 |
| GB: NRFA API | 109 | 31 |
| FR: Hub'Eau | 1,189 | 25 |
| DE: CAMELS-DE + state portals | 745 | 4 |
| IN, IT, TH, CN, ZA, IE and others: GRDC request | ~1,400 | ~70 |

- Rainfall: the same product the authors used in each region. That's EM-Earth daily 0.1° from AWS, EMDNA in North America where they used it, and the CAMELS forcings for GB and AU. Basin means over their polygons with exactextract, 1979–2019.
- Apply their record filters. Flag short or gappy records instead of dropping them, since they are the likely reason these gauges were left out of training.

## Phase 3: scoring

- Confusion matrix per season and region, plus precision, recall, balanced accuracy, κ, and the complex vs non-complex split.
- Simple class: share of predicted-simple gauges that are observed simple, and how far their linear R² falls from 0.75.
- Baselines: "always complex", and a climate-only model (RW₅ + AI), to show what the other 25 predictors add.
- Stratify by nesting in or adjacency to training catchments, record length, and area.

## Phase 4: is the label a property of the catchment?

- Label each half of a record separately and check agreement.
- Swap rainfall products (ERA5-Land or MSWEP globally, Stage IV in the US, CEH-GEAR in GB) and count label flips.
- For predicted-simple gauges, relabel with all 25 EM-Earth ensemble members.

## Phase 5 (optional): brand-new gauges

Only if simple-rich regions are still thin: coastal BC, the Pacific Northwest, New Zealand, Tasmania. Candidate sources: HYSETS, CAMELS-NZ/CH/SE/IND, LamaH. This needs the 27 predictors rebuilt from MERIT Hydro, GLiM, depth to bedrock, CGLS-LC100, EM-Earth, Singer PET and ERA5-Land, checked first against 200 of the authors' gauged catchments.

## Deliverables

- Python package `stormflow_diag` with `stage1` (events + labels), `predict`, `validate`.
- Per-gauge table: predicted label, observed label, R² values, event count, record length.
- Confusion-matrix and label-flip figures.

## Inputs on hand

| Input | Location | Notes |
|---|---|---|
| Figshare package (paper ref. 79) | `data/figshare/` → `../../data` | 4,552 gauged catchments (4,306 in the paper + 246 with `Catchment_Boundary_Flagged`), daily P/Q per GCIN in `Event_Inputs.zip`, event catalogues per season, attributes, polygons, monthly phenology |
| Zenodo 14253670 (Sharif & Ameli 2024) | `data/zenodo_14253670/` | 619 catchments: per-catchment linear/segmented R², class, events, daily series |
| Authors' code and XGBoost models | `upstream/` | pinned at `932f810` |
