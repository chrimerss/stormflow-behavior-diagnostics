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
| 0B | Does DMCA-ESR on the raw series reproduce their event catalogue? | **Pass**: 99.999 % of events, 99.94 % of labels; **go** ([F9](findings.html#f9)) |
| 1 | Do the 246 boundary-flagged gauges agree with the model? Are catchment areas right? | Done: flagged gauges ([F6](findings.html#f6)), Area ([F4](findings.html#f4)); metric audit ([F5](findings.html#f5)) |
| 2 | Assemble ~15,000 independent validation gauges | Streamflow in hand for USGS (3,614), HYDAT (154), Hub'Eau (828). 1,797 polygons fail the area check ([F10](findings.html#f10)). EM-Earth rainfall via Globus pending |
| 3 | Score the model on them against simple baselines | Not started |
| 4 | Is the label stable across record halves and rainfall products? | Record halves done on the authors' catalogue ([F8](findings.html#f8)); rainfall swaps need Phase 2 data |
| 5 | Brand-new gauges in simple-rich regions (optional) | Not started |

Go/no-go for Phase 0: at least 95 % label agreement on about 300 gauges, including all 210 dormant-season simple gauges.

## Headline findings so far

1. **About 1,800 "ungauged" catchments are slivers of the real catchment.** For 1,797 GSIM stations, 1,531 of them in the US, the authors' polygon covers under half of the agency-reported drainage area. For 1,426 it covers under 1 %, for example 3 km² for the 3,372 km² Carson River. These are failed GSIM delineations; their predictors and predicted class describe the wrong land. [F10](findings.html#f10)
2. **Phase 0 go: the labelling reproduces from raw data, but a quarter of the season splits cannot.** Our DMCA-ESR port rebuilds 99.999 % of their 2.03 million events and 99.94 % of their labels. For the 1,145 `WRR_` gauges, which carry over half the simple labels, the released phenology file does not reproduce their dormant/growing split. Using it changes about one label in four. [F9](findings.html#f9)
3. **The paper's held-out "precision" is recall.** The released evaluation code swaps the rows and columns of caret's confusion table. With the paper's own definition, precision for predicted-simple gauges is 0.49 in the dormant season and 0.24 in the growing season, not 0.67 and 0.62; growing intermediate is 0.57. The ≥ 0.60 claim fails for those three. Complex-class precision (0.84 / 0.89) is unaffected. Verified by running the authors' own functions. [F5](findings.html#f5)
4. **Ungauged "simple" predictions come from tiny basins outside the training range.** 98 % of the 34,376 dormant predicted-simple catchments are small basins in and around British Columbia (median 5 km²), and 64 % of those polygons are smaller than the 1st percentile of training catchment area. [F7](findings.html#f7)
5. **Labels are not reproducible across independent samples of storms.** Two disjoint halves of the same gauge's record give the same class only ~70 % of the time (simple gauges: 49–65 %). Early and late halves agree as often as random halves, so this is sampling noise, not change over time. The paper's 96–100 % jackknife certainty reproduces exactly, but it compares heavily overlapping subsamples. [F8](findings.html#f8)
6. **Skill drops on unseen flagged gauges.** On the 246 boundary-flagged gauges, which were never used in training, κ falls from 0.54 to 0.28 (dormant). In Denmark (143 gauges) the models do no better than "always complex". The flagged boundaries themselves are a confounder. [F6](findings.html#f6)
7. **The labelling step reproduces from the authors' event catalogue.** Refitting all 9,000 catchment-seasons with the stated rule reproduces 99.94 % of labels, including every simple gauge. The five mismatches are small-sample or near-threshold cases. [F2](findings.html#f2)
8. **"Simple" does not mean "no threshold".** 177 of 210 dormant simple gauges also have a significant breakpoint. They are simple because the linear fit is checked first. The ~100 intermediates labelled through the segmented fit alone rest on a median of 4–6 large events (as few as 2). [F3](findings.html#f3)
9. **Catchment areas match the GSIM polygons.** An apparent 2.6× discrepancy for US gauges is a mi²/km² unit issue in GSIM, not an error by the authors. [F4](findings.html#f4)

See [Findings](findings.html) for the full dated log, and [Plan](PLAN.html) for the experiment design.
