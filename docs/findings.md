---
title: Findings
nav_order: 2
---

# Findings log

Newest first. Each entry gives the numbers, how they were produced, and what they do and do not show.

---

## F1. Linear R² from the authors' catalogue reproduces the linear-determined labels {#f1}
*2026-09-27 · Phase 0, Check A (partial)*

For each gauge and season we regressed event stormflow volume on event rainfall volume (OLS with intercept) using the authors' published event catalogue (Figshare, `Identified_Rainfall_Runoff_Events_*.csv`), and applied the Methods thresholds.

| Their label | Our linear R² class | Dormant | Growing |
|---|---|---:|---:|
| simple | R² ≥ 0.75 | 210 / 210 | 73 / 73 |
| intermediate | 0.50 ≤ R² < 0.75 | 1,513 / 1,559 | 1,003 / 1,064 |
| intermediate | R² < 0.50 (must come from the segmented fit) | 46 / 1,559 | 61 / 1,064 |
| complex | R² < 0.50 | 2,783 / 2,783 | 3,311 / 3,311 |

No gauge falls on the wrong side of a linear threshold. The same R² definition matches the per-catchment values in the authors' earlier release (Zenodo 14253670) to four decimals for all 314 dormant and 214 growing linear-model catchments.

**What this shows:** their labels follow from their catalogue under the stated linear rule.
**What it does not show:** that the catalogue itself reproduces from raw data (Check B), or that the 46 + 61 segmented-only intermediates hold up. Those gauges reach segmented R² ≥ 0.75 from linear R² as low as 0.165 (dormant) and 0.172 (growing), a large jump that will be examined once the segmented fits are in.

### Data notes from the same pass
- Figshare holds 4,552 gauged catchments: the paper's 4,306 plus 246 with `Catchment_Boundary_Flagged = True`. The flagged set is exactly the set without model predictions; 143 of the 246 are in Denmark. Among them, 27 are dormant-season simple.
- 104 gauges have no growing-season label. All 104 have fewer than 15 growing-season events (8 have none), and no labelled gauge has fewer than 15, so the filter was applied as stated.
- The growing-season catalogue includes 14,966 events whose monthly phenology value is exactly 0; they were counted as growing.
- The shortest events in the catalogue are 2 days (rainfall) and 3 days (stormflow), so the "shorter than 1 day" filter never binds; the 15-day cap does.
