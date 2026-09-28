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
| 0A | Does the authors' regression rule reproduce their labels from their own event catalogue? | **Pass**: 99.94 % ([F2](findings.html#f2)) |
| 0B | Does DMCA-ESR on the raw series reproduce their event catalogue? | Porting the method |
| 1 | Do the 246 boundary-flagged gauges agree with the model? Are catchment areas right? | Done: flagged gauges ([F6](findings.html#f6)), Area ([F4](findings.html#f4)); metric audit ([F5](findings.html#f5)) |
| 2 | Assemble ~15,000 independent validation gauges | Not started |
| 3 | Score the model on them against simple baselines | Not started |
| 4 | Is the label stable across record halves and rainfall products? | Not started |
| 5 | Brand-new gauges in simple-rich regions (optional) | Not started |

Go/no-go for Phase 0: at least 95 % label agreement on about 300 gauges, including all 210 dormant-season simple gauges.

## Headline findings so far

1. **The paper's held-out "precision" is recall.** The released evaluation code swaps the rows and columns of caret's confusion table. With the paper's own definition, precision for predicted-simple gauges is 0.49 in the dormant season and 0.24 in the growing season, not 0.67 and 0.62; growing intermediate is 0.57. The ≥ 0.60 claim fails for those three. Complex-class precision (0.84 / 0.89) is unaffected. Verified by running the authors' own functions. [F5](findings.html#f5)
2. **Ungauged "simple" predictions come from tiny basins outside the training range.** 98 % of the 34,376 dormant predicted-simple catchments are small basins in and around British Columbia (median 5 km²), and 64 % of those polygons are smaller than the 1st percentile of training catchment area. [F7](findings.html#f7)
3. **Skill drops on unseen flagged gauges.** On the 246 boundary-flagged gauges, which were never used in training, κ falls from 0.54 to 0.28 (dormant). In Denmark (143 gauges) the models do no better than "always complex". The flagged boundaries themselves are a confounder. [F6](findings.html#f6)
4. **The labelling step reproduces from the authors' event catalogue.** Refitting all 9,000 catchment-seasons with the stated rule reproduces 99.94 % of labels, including every simple gauge. The five mismatches are small-sample or near-threshold cases. [F2](findings.html#f2)
5. **"Simple" does not mean "no threshold".** 177 of 210 dormant simple gauges also have a significant breakpoint. They are simple because the linear fit is checked first. The ~100 intermediates labelled through the segmented fit alone rest on a median of 4–6 large events (as few as 2). [F3](findings.html#f3)
6. **Catchment areas match the GSIM polygons.** An apparent 2.6× discrepancy for US gauges is a mi²/km² unit issue in GSIM, not an error by the authors. [F4](findings.html#f4)

See [Findings](findings.html) for the full dated log, and [Plan](PLAN.html) for the experiment design.
