---
title: Status
nav_order: 1
---

# Stormflow behaviour diagnostics

An independent test of whether the conclusions of

> Ameli, A. A., Sharif, H. & McDonnell, J. J. *A global classification of hydrologic functional diversity in gauged and ungauged catchments.* Nature Water (2026). [doi:10.1038/s44221-026-00699-6](https://doi.org/10.1038/s44221-026-00699-6)

hold up when the analysis is rebuilt and extended. The paper labels 4,306 gauged catchments as simple, intermediate or complex from the R² of event rainfall–runoff regressions, then extrapolates those labels to 77,585 ungauged catchments with XGBoost.

**Last updated:** 2026-09-27

## Progress

| Phase | Question | Status |
|---|---|---|
| 0A | Does the authors' regression rule reproduce their labels from their own event catalogue? | Linear part reproduced exactly; segmented part running |
| 0B | Does DMCA-ESR on the raw series reproduce their event catalogue? | Porting the method |
| 1 | Do the 246 boundary-flagged gauges agree with the model? Are catchment areas right? | Not started |
| 2 | Assemble ~15,000 independent validation gauges | Not started |
| 3 | Score the model on them against simple baselines | Not started |
| 4 | Is the label stable across record halves and rainfall products? | Not started |
| 5 | Brand-new gauges in simple-rich regions (optional) | Not started |

Go/no-go for Phase 0: at least 95 % label agreement on about 300 gauges, including all 210 dormant-season simple gauges.

## Headline findings so far

1. **The linear half of the labelling rule is internally consistent.** Recomputing the linear R² from the authors' published event catalogue gives the same label for every gauge whose label depends only on the linear fit: 210/210 simple and 1,513/1,513 linear-intermediate gauges in the dormant season, 73/73 and 1,003/1,003 in the growing season. [Details](findings.html#f1)

See [Findings](findings.html) for the full dated log, and [Plan](PLAN.html) for the experiment design.
