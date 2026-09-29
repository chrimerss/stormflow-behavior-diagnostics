---
title: Findings
nav_order: 2
---

# Findings log

Newest first. Each entry gives the numbers, how they were produced, and what they do and do not show.

---

## F13. One in six gauged labels changes with the rainfall product, and 5–9 % with the record period {#f13}
*2026-09-29 · Phase 4 (US, the authors' own gauges)*

We kept the authors' own inputs (dates and streamflow from `Event_Inputs`) for their 681 US `GSIM_US_*` gauges and replaced only the rainfall with our EM-Earth series over the same polygons. We then relabelled with the reproduced pipeline.

| Authors' US gauges | Change | Labels kept (dormant) | Labels kept (growing) | Dormant simple kept |
|---|---|---:|---:|---:|
| 190 with EM-Earth inputs | record cut from 1950–2019 to 1979–2019 | 95.2 % (κ 0.91) | 91.0 % (κ 0.79) | 6 / 7 |
| 491 with EMDNA-like inputs ([F11](#f11)) | the authors' 1979–2018 rainfall (probably EMDNA) → EM-Earth, same flow and period | 84.8 % (κ 0.72) | 81.9 % (κ 0.59) | 8 / 21 |

"Labels kept" counts gauge-seasons that still have ≥ 15 events after the change. 2 and 2 of the 190, and 5 and 7 of the 491, fall below that. With the authors' own rainfall, the reproduced pipeline returns all 1,354 labels of these 681 gauges unchanged ([F9](#f9)), so every difference here comes from the swap or the period.

- **Rainfall product.** Swapping the product changes about one label in six. Simple is the most fragile class: 13 of 21 dormant simple gauges become intermediate.
- **Record period.** Dropping 1950–1978 changes 5–9 % of labels.
- **A reference level for validation.** Labels for the same gauges under the two rainfall products agree 85 % (dormant) and 82 % (growing). A model that reproduced the authors' US labels perfectly would score about that against EM-Earth labels. This is not a strict ceiling: a model of the underlying class could score higher against either noisy label set. [F12](#f12) uses it as a reference.

Code: `scripts/phase4_us_rainfall_swap.py`. Output: `results/phase4/us_rainfall_swap.csv`.

---

## F12. On independent US gauges the model does no better than copying the nearest gauge, and its "simple" predictions are mostly wrong {#f12}
*2026-09-29 · Phase 2 + 3 (US)*

**Validation set.** The set is 1,485 USGS stations that the authors treated as ungauged. Each polygon is within 0.8–1.25× of the USGS drainage area ([F10](#f10)), and each record has at least 10 years with ≥ 300 valid days in 1979–2019. We labelled each one with the reproduced pipeline (Phase 0): USGS daily flow, EM-Earth `prcp_corrected` over the authors' polygon, the authors' phenology for that catchment, and the ≥ 15 events rule. That gives 1,322 dormant and 1,309 growing labels. Predictions are the authors' released models applied to their own attribute table; our application reproduces their published predicted class for all of these catchments.

| Season | Model | n | Accuracy | Balanced acc. | κ |
|---|---|---:|---:|---:|---:|
| Dormant | **authors' XGBoost** | 1,322 | 0.671 | 0.511 | 0.37 |
| | nearest gauged catchment's label | 1,322 | 0.672 | 0.536 | 0.38 |
| | climate only (RW5 + AI, same training) | 1,322 | 0.469 | 0.392 | 0.04 |
| | always complex | 1,322 | 0.433 | 0.333 | 0 |
| Growing | **authors' XGBoost** | 1,309 | 0.573 | 0.385 | 0.15 |
| | nearest gauged catchment's label | 1,296 | 0.595 | 0.386 | 0.16 |
| | climate only | 1,309 | 0.592 | 0.335 | 0.01 |
| | always complex | 1,309 | **0.607** | 0.333 | 0 |

For reference, the same models score κ 0.54 (dormant) and 0.47 (growing) on the authors' own held-out split ([F6](#f6)). The authors' labels under the two rainfall products agree about 85 % (dormant) and 82 % (growing) ([F13](#f13)).

- **No gain over a neighbouring gauge.** On gauges the model never saw, its predictions score the same as copying the label of the nearest gauged catchment. κ is 0.37 vs 0.38 (dormant) and 0.15 vs 0.16 (growing), and the 95 % bootstrap intervals of the differences are −0.06 to +0.04 and −0.07 to +0.05.
  - The baseline may draw on any of the authors' 4,552 gauged catchments, including some outside the training set. Restricted to training gauges it scores κ 0.34 and 0.17, again indistinguishable from the model.
  - A model on RW5 and AI alone has almost no skill: κ ≤ 0.06 for XGBoost, logistic regression or random forest.
  - On these gauges, the 27 predictors add nothing measurable beyond a neighbouring gauge's label. This test does not show where the model's remaining skill comes from.
- **Growing season.** Accuracy (0.573) is no higher than the "always complex" baseline (0.607). The difference is −0.03 (95 % bootstrap interval −0.07 to 0.00).
- **Simple class.**
  - Dormant: 7 of the 41 gauges predicted simple are observed simple (precision 0.17), and 7 of the 41 observed simple gauges are found (recall 0.17).
  - The median linear R² of predicted-simple gauges is 0.65; only 17 % reach 0.75.
  - Growing: none of the 11 predicted-simple gauges is observed simple.
  - For comparison, in the EMDNA-like group of [F13](#f13), 8 of 21 dormant simple labels stay simple after the rainfall swap (38 %, 95 % interval 21–59 %), and 8 of the 14 new simple labels were simple before (57 %). The model's 7 of 41 (17 %, interval 9–31 %) is lower than both, but the difference from 8 of 21 is not significant (Fisher p = 0.12).
- **Distance from the authors' gauges.** Skill is highest where a validation polygon is nested in one of the authors' gauged polygons (dormant κ 0.62; 57 of the 81 nested polygons lie in a training gauge). It is lowest for catchments more than 10 km from any of their gauged polygons: dormant κ 0.26, growing κ 0.06, against 0.34 and 0.08 for the nearest-gauge baseline. In the growing season, accuracy for those distant catchments is 0.51, against 0.46 for "always complex".
- **Record length and area.** In the dormant season, skill is lowest for 10–20-year records (κ 0.23, against 0.42 for 20–30 and 0.39 for > 30 years) and for catchments under 100 km² (κ 0.23, against 0.36–0.37 above). The growing season shows no such pattern (κ 0.18, 0.13, 0.14 by record length; 0.14, 0.16, 0.14 by area).

**Non-overlapping gauges in detail.** These are validation catchments whose polygon does not overlap any of the authors' 4,552 gauged polygons. The table sets the model's predicted class against the class from the regression test on the gauge's own events.

| | Dormant, no overlap | Growing, no overlap | Dormant, > 10 km | Growing, > 10 km |
|---|---:|---:|---:|---:|
| n | 886 | 889 | 506 | 511 |
| Accuracy (always complex) | 0.672 (0.369) | 0.552 (0.529) | 0.640 (0.352) | 0.507 (0.464) |
| κ, model / nearest gauge / climate only | 0.34 / 0.36 / 0.00 | 0.13 / 0.15 / −0.01 | 0.26 / 0.34 / −0.08 | 0.06 / 0.08 / −0.01 |
| Predicted simple → observed simple | 6 / 28 | 0 / 8 | 1 / 9 | 0 / 4 |
| Observed simple found | 6 / 31 | 0 / 25 | 1 / 20 | 0 / 19 |
| Median linear R² (predicted simple / intermediate / complex) | 0.65 / 0.58 / 0.42 | 0.46 / 0.51 / 0.45 | 0.52 / 0.57 / 0.45 | 0.36 / 0.52 / 0.49 |
| Spearman(predicted class, linear R²) | 0.38 | 0.17 | 0.25 | 0.07 |

In the dormant season the predicted class tracks the regression test weakly, ordering catchments roughly by R². In the growing season it barely does, and for catchments more than 10 km from any gauged polygon it does not at all (ρ = 0.07). Of the 36 non-overlapping catchment-seasons the model calls simple (28 dormant, 8 growing), 6 pass the R² ≥ 0.75 test.

**Caveats.**
1. Our labels use EM-Earth. About 760 of the authors' 950 US gauged catchments (80 %) appear to use EMDNA-like rainfall ([F11](#f11)); under that swap their own labels agree only about 85 % ([F13](#f13)). The nearest-gauge baseline faces the same mismatch, so the comparison between the two is fair.
2. Our records cover 1979–2019, while 190 of the authors' US gauges used 1950–2019.
3. The US has the densest training data. We would expect sparser regions to do worse, but that is untested here.
4. The validation catchments are US rivers with a median area of 577 km² (272 km² for the authors' gauges). 98 % of the paper's dormant simple predictions are BCUB basins of a few km² that this test does not cover ([F7](#f7)), and the 1,746 US catchments with sliver polygons cannot be tested ([F10](#f10)).

An independent audit recomputed every number in this entry from the raw files, including three catchments relabelled end to end from NWIS and EM-Earth. All values reproduced.

Code: `scripts/phase2_us_labels.py`, `scripts/phase3_us_scores.py`. Output: `results/phase2/us_labels.csv`, `results/phase3/us_{scores,predictions,simple}.csv`.

---

## F11. Most US training rainfall is not EM-Earth, although the metadata says it is {#f11}
*2026-09-28, updated 2026-09-29 with the full 1979–2019 record · Phase 2, rainfall provenance*

We averaged EM-Earth daily precipitation over the authors' gauged polygons and compared the result with the rainfall in their inputs (`Event_Inputs/<GCIN>.csv`). We did this for all 681 US gauges whose metadata gives `precipitation_source = EM-Earth`.

- **How they built the EM-Earth series.** They used the gauge-undercatch-corrected variable `prcp_corrected`, not `prcp`, averaged with plain cell-coverage weights (the exactextract mean). With that choice our series equals theirs on every day of 1979–2019, to within 1.4e-3 mm/day (median of the per-gauge maximum 3e-4 mm/day, float32 rounding of the grid coordinates).
- **Only 190 of the 681 gauges match.** They are exactly the 190 whose inputs run 1950–2019. None of the 491 gauges whose inputs run 1979–2018 match:

| US gauges, compared with EM-Earth `prcp_corrected` | Days compared (median) | Correlation (median) | Mean abs. difference | Days equal |
|---|---:|---:|---:|---:|
| Metadata EM-Earth, inputs 1950–2019 (190) | 14,975 | 1.000 | 0.00001 mm | 100 % |
| Metadata EM-Earth, inputs 1979–2018 (491) | 14,610 | 0.973 | 0.69 mm | 17 % |
| Metadata EMDNA (269 `WRR_` gauges; Aug 1999, 2008, 2013 only) | 93 | 0.966 | 0.87 mm | 9 % |

- **The 491 look like EMDNA.** 1979–2018 is exactly the period of EMDNA, the North American dataset from the same group. The 269 gauges labelled EMDNA use the same window, and the 491 differ from EM-Earth in the same way they do. The same window appears for 31 Canadian gauges labelled EM-Earth. We have not yet compared these series with EMDNA itself, so this is an inference, not a proof.
- **Consequences.**
  - If the inference holds, about 760 of the 950 US gauged catchments (80 %) use EMDNA rainfall, not the 269 the metadata implies.
  - The metadata column `precipitation_source` would then be wrong for 522 of the 4,552 gauged catchments (11 %): 491 in the US and 31 in Canada.
  - Validating US predictions on EM-Earth alone would mix a model test with a rainfall-product swap. We will label the US validation gauges with both products, and count flips between them as a Phase 4 result.

Code: `scripts/phase2_emearth.py us-gauged --months …` then `check`. Output: `results/phase2/emearth_vs_authors.csv`.

---

## F10. About 1,800 "ungauged" catchments are slivers: their polygons cover under half of the real catchment {#f10}
*2026-09-27 · Phase 1 / Phase 2 · the catchment-area problem*

We compared the authors' polygon `Area` for the 14,476 GSIM "ungauged" catchments with the drainage area the national agency reports: the USGS site service, HYDAT, Hub'Eau, or GSIM's reported area for other countries, with US values converted from mi². 11,172 stations have a reference area.

| Polygon / reported area | Catchments | of which US |
|---|---:|---:|
| < 1 % | 1,426 | 1,234 |
| 1–50 % | 371 | 297 |
| 50–80 % | 278 | 75 |
| 0.8–1.25× | 8,820 | 1,881 |
| > 1.25× | 277 | 120 |

Examples, confirmed against the USGS site service and the polygon geometry itself:

| USGS site | Station | USGS drainage area | Authors' polygon |
|---|---|---:|---:|
| 10312000 | Carson River near Fort Churchill, NV | 3,372 km² | 3.0 km² |
| 14025000 | Birch Creek at Rieth, OR | 754 km² | 0.46 km² |
| 01673800 | Po River near Spotsylvania, VA | 201 km² | 0.12 km² |
| 02087359 | Walnut Creek near Raleigh, NC | 77 km² | 0.12 km² |

- **Where they come from.** The polygons match GSIM's own estimated area (`area.est`), and 1,785 of the 1,797 cases have GSIM quality "Caution", meaning GSIM had no reported area to check its delineation against. These look like failed GSIM delineations snapped to a few grid cells near the gauge, carried unchecked into the ungauged set.
- **How many are affected.** 42 % of US GSIM stations (1,531 of 3,607) are affected, and scattered cases occur elsewhere.
- **What it means.** For these catchments, all 27 predictors and the predicted class describe a patch of hillslope next to the gauge, not the gauged river. They count toward the paper's catchment tallies: dormant predictions are 885 complex, 841 intermediate and 71 simple. By area they contribute almost nothing.
- **The training set is not affected.** The authors' gauged polygons agree with reported areas ([F4](#f4)).
- **For Phase 2.** Validation uses only stations whose polygon is within 0.8–1.25× the reported area. The rest are reported separately. 3,304 GSIM stations, mostly Australian, still need a reference area from the national agency.

Output: `results/phase2/gsim_polygon_area_check.csv`, and `AREA MISMATCH` notes in `results/phase2/streamflow_manifest.csv`.

---

## F9. Phase 0 passes: labels rebuild from raw data, but a quarter of the season splits cannot {#f9}
*2026-09-27 · Phase 0, Check B · decision: **go***

**Event detection.** We ported DMCA-ESR (Giani et al. 2022) from the reference MATLAB code to Python. Checked against that code running in GNU Octave 10.3, the port is bit-for-bit identical on the bundled example gauge and on five of the authors' gauges. Run on the authors' daily series (`Event_Inputs.zip`) with R_min = 1.2 mm/day and L_max = 16 days, it reproduces their catalogue:

- 2,030,547 of 2,030,569 events match on all four dates (99.9989 %), with 26 extra on our side. 4,528 of 4,552 gauges are identical.
- On matched events, volumes agree to the last printed digit.
- The 48 leftover differences are at 24 CAMELS-GB gauges, where rainfall is stored to two decimals. A fluctuation can then sit exactly on the R_min threshold, and MATLAB and Octave round the moving mean differently there.

Conventions we had to infer from their catalogue, each confirmed event by event:

- Series are divided by 24 (mm/h), as in the reference `example.m`.
- NaN streamflow stays in the series. Events with any missing flow in the stormflow window are dropped.
- Kept events have 0 < runoff ratio ≤ 1, a rainfall duration of 2–15 days and a stormflow duration of at most 15 days.
- Each event's season value is the mean of the gauge's monthly phenology values over the calendar months it spans; below zero is dormant.

**Labels from raw data, end to end** (our events → our regression → rule):

| Season split | Agreement with their labels | Simple reproduced (dormant / growing) |
|---|---:|---:|
| Their catalogue's season for each event | 8,995 / 9,000 (**99.94 %**) | 210 / 210, 73 / 73 |
| Released phenology file (`Gauged_Catchments_Growing_Dormancy_Probability.csv`) | 8,402 / 8,988 (93.5 %) | 177 / 210, 60 / 73 |

**Decision.** Event detection and labelling reproduce, so we can label new gauges exactly as the authors would (go threshold: ≥ 95 % and all 210 dormant simple). Phase 2 proceeds.

**The season problem.** For the 3,407 gauges not prefixed `WRR_`, the released phenology file reproduces every event's season, and label agreement is 99.9 %. The other 1,145 gauges (Source ID `WRR_*`: 483 Brazil, 269 US, 208 Australia, 124 GB, 37 Chile, 18 Canada, 6 Mexico) do not follow it. Their catalogue values are multiples of 1/18, which suggests a different phenology product.

- Rebuilding their seasons from the released file puts only 58.9 % of their events in the same season as the catalogue does.
- Labels then agree for only 72.4 % (dormant) and 76.4 % (growing) of these gauges.
- These gauges carry 119 of the 210 dormant simple labels and 45 of the 73 growing ones. Under the released seasons, 33 of those 119 and 13 of those 45 change class.

So a quarter of the gauged labels cannot be rebuilt from the released data. They also depend strongly on how the season is defined. A reasonable alternative split changes about one label in four.

Code: `scripts/phase0_check_b_pilot.py`, `scripts/phase0_check_b_labels.py`. Output: `results/phase0/check_b_*.csv`. DMCA-ESR port: `src/stormflow_diag/stage1/events.py` (translation of https://github.com/giuliagiani/DMCA-ESR, with attribution), tests in `tests/test_events.py`.

---

## F8. Independent halves of a record give the same label only ~70 % of the time {#f8}
*2026-09-27 · Phase 4 (using the authors' event catalogue)*

The paper supports label robustness with a jackknife: 100 random 80 % subsamples per catchment-season, and certainty is the share that keep the full-sample label. We reran that exact procedure with our pipeline. For every simple gauge and 200 random intermediate and 200 complex gauges per season, it reproduces their reported medians:

| Median certainty | Paper, dormant | Ours, dormant | Paper, growing | Ours, growing |
|---|---:|---:|---:|---:|
| Simple | 98 % | 97 % | 86 % | 88 % |
| Intermediate | 96 % | 98 % | 92 % | 92 % |
| Complex | 100 % | 100 % | 100 % | 100 % |

Any two 80 % subsamples share at least 60 % of their events, and each shares 80 % with the full record, so this test mostly measures overlap. A stricter test splits each record into two **disjoint** halves, each labelled with the same rule and each needing at least 15 events. The median half holds 102 (dormant) or 120 (growing) events.

| Disjoint halves agree | Dormant | Growing |
|---|---:|---:|
| Chronological (first vs second half of the record) | 69.3 % | 70.2 % |
| Random halves | 69.9 % | 72.5 % |
| Simple gauges (chronological / random) | 64.5 / 60.9 % | 48.6 / 50.0 % |
| Intermediate gauges | 59.5 / 60.9 % | 51.8 / 57.5 % |
| Complex gauges | 75.4 / 75.8 % | 76.5 / 77.8 % |

- **No sign of drift over time.** Chronological halves agree almost as often as random halves (a gap of 0.6 and 2.3 points), so labels do not shift systematically between early and late periods.
- **Large sampling instability.** About 30 % of catchments change class between two independent sets of ~100 storms. For simple gauges, the two halves agree only about half the time in the growing season.
- **Caveat.** Each half has half the events, so it is noisier than the full record the paper labels. This result bounds full-record reproducibility from below. It applies directly to validation gauges with shorter records and to gauges near the 15-event minimum.

**Implication.** The jackknife numbers show that labels are stable to resampling the same storms, not that another sample of storms from the same catchment would give the same class. How much of the XGBoost "error" in [F5](#f5)–[F6](#f6) is label noise rather than model error is an open question for Phase 3.

Code: `scripts/phase4_split_half.py`, `scripts/phase4_jackknife.py`. Output: `results/phase4/`.

---

## F7. Almost all "simple" ungauged predictions are tiny British Columbia–area basins below the training range of area {#f7}
*2026-09-27 · Phase 2 scoping*

What the 77,585 "ungauged" catchments are (`Polygon Source` in the Figshare table):

| Source | Catchments | Median area (km²) | Predicted simple (dormant) |
|---|---:|---:|---:|
| BCUB (British Columbia and adjacent US, 46–60° N, 121–141° W) | 60,349 | 5.0 | 33,823 |
| GSIM stations | 14,476 | 270 | 544 |
| CAMELS-DK (ungauged part) | 2,240 | 14.9 | 5 |
| CAMELS-DE | 374 | 184 | 1 |
| CAMELS-FR | 146 | 266 | 3 |

- **98.4 % of dormant predicted-simple catchments (33,823 of 34,376) are BCUB polygons.** By count, simple is the largest predicted class (44 %); by area, it covers 1.7 %.
- **Most BCUB catchments are smaller than nearly every training catchment.** The dormant training set's area runs from 0.79 km² (minimum) through 9.5 km² (1st percentile) to 303 km² (median). 63.5 % of BCUB catchments are below that 1st percentile and 78 % below the 5th (22.8 km²). Only 15 training gauges are under 5 km², three of them simple; about 31,000 BCUB catchments are.
- The paper's DBSCAN analysis finds that ungauged catchments sit mostly inside the training domain in the joint predictor space. That can hold while area alone is far out of range: the model has almost no labelled evidence about 1–10 km² catchments, which make up most of its ungauged predictions.
- 17,236 "ungauged" catchments are GSIM or CAMELS stations. Many have daily streamflow available from national agencies, and these are the Phase 2 validation set.

**Implication, combined with [F5](#f5):** the ungauged "simple clusters" rest on a class whose held-out precision is 0.49 (dormant) and on catchments mostly smaller than the training data covers. Phase 2 tests this directly where gauges exist.

---

## F6. On the 246 boundary-flagged gauges the models barely beat "always complex" {#f6}
*2026-09-27 · Phase 1*

The authors labelled 246 gauges but left them out of training and out of the paper because their boundaries were flagged; 143 are in Denmark. None is in either training set, so they are a free out-of-sample test. Our Python port of the feature construction reproduces the authors' own predicted class for all 4,306 unflagged gauges in both seasons (100 %), so the predictions below come from exactly their models.

| Set | Season | n | Accuracy | "Always complex" | Balanced acc. | κ |
|---|---|---:|---:|---:|---:|---:|
| Authors' test split | dormant | 859 | 0.768 | 0.618 | 0.719 | 0.54 |
| Flagged gauges | dormant | 246 | 0.606 | 0.504 | 0.562 | 0.28 |
| &nbsp;&nbsp;Denmark | dormant | 143 | 0.650 | 0.650 | 0.347 | 0.06 |
| &nbsp;&nbsp;elsewhere | dormant | 103 | 0.544 | 0.301 | 0.588 | 0.32 |
| Authors' test split | growing | 840 | 0.783 | 0.749 | 0.688 | 0.47 |
| Flagged gauges | growing | 243 | 0.724 | 0.671 | 0.559 | 0.35 |
| &nbsp;&nbsp;Denmark | growing | 143 | 0.790 | 0.818 | 0.332 | −0.01 |
| &nbsp;&nbsp;elsewhere | growing | 100 | 0.630 | 0.460 | 0.573 | 0.33 |

- In Denmark the models carry no information beyond the base rate (κ ≈ 0). 67 of 95 dormant intermediates overall are predicted complex.
- Outside Denmark, skill falls to about κ 0.33 from the test-split 0.47–0.54.
- Dormant simple: 15 of 23 predicted-simple flagged gauges are observed simple (precision 0.65), and 15 of 27 observed simple are found (recall 0.56).

**Caveat.** These boundaries were flagged for a reason, so their attributes may be computed over the wrong area. A drop here mixes model error with input error. Phase 2 (independent gauges with good polygons) is the clean test.

Code: `scripts/phase1_flagged.py`, `src/stormflow_diag/{predict,validate}.py`. Output: `results/phase1/`.

---

## F5. The reported "precision" is recall, and "specificity" is negative predictive value {#f5}
*2026-09-27 · Phase 1 · audit of the released evaluation code*

In `upstream/code/Reproducing_XGBoost_Models_Results.Rmd`, `eval_metrics_exe()` builds the confusion table with `caret::confusionMatrix(predicted, observed)`, which puts **predictions in rows and observations in columns**. `calculate_class_metrics()` then reads the rows as observed classes: it takes the column sum as TP + FP and the row sum as TP + FN. The two are swapped, so the function returns

- recall under the name *precision*, and
- negative predictive value, TN / (TN + FN), under the name *specificity*.

We confirmed this by running the authors' functions, extracted verbatim from the Rmd, on their released models and split (`scripts/phase1_metric_audit.R`, R 4.3, xgboost 1.7.6, caret 6.0-94). The output reproduces every number in their rendered HTML report. Recomputing with the definitions stated in the paper's Methods gives:

| Held-out test gauges | Reported "precision" | True precision | Reported "specificity" | True specificity |
|---|---:|---:|---:|---:|
| Dormant simple (n obs = 36) | 0.67 | **0.49** (24 / 49) | 0.99 | 0.97 |
| Dormant intermediate | 0.65 | 0.68 | 0.82 | 0.84 |
| Dormant complex | 0.84 | 0.84 | 0.74 | 0.75 |
| Growing simple (n obs = 13) | 0.62 | **0.24** (8 / 34) | 0.99 | 0.97 |
| Growing intermediate | 0.61 | **0.57** | 0.88 | 0.86 |
| Growing complex | 0.84 | 0.89 | 0.60 | 0.69 |
| Growing non-complex (binary) | 0.69 | **0.60** | 0.89 | 0.84 |

**How this reaches the paper.** The held-out figures in the Methods section on model evaluation match the swapped values exactly: complex 0.84 in both seasons, dormant non-complex 0.75, growing non-complex 0.69, and every three-class metric at or above 0.60 (Supplementary Table 2). Under the paper's own definition of precision, the ≥ 0.60 statement fails for dormant simple (0.49), growing simple (0.24) and growing intermediate (0.57). By the paper's own benchmarks, growing-season simple predictions fall well below "acceptable": about three in four gauges the model calls simple are not.

**What is unaffected.** The trained models, the predictions and the confusion matrices are unchanged; only the summary metrics are mislabelled. Complex-class precision is 0.84 and 0.89, so claims about complex catchments stand or improve.

**Not yet checked.** The regional medians over 200 cross-validation trials (Supplementary Table 5) come from code that was not released. If that code uses the same function, those precisions are also recalls. The released notebook's regional table also scores each region on all its gauges, training gauges included. Both need Phase 3's re-run of the 200-trial protocol.

---

## F4. Catchment areas agree with the GSIM polygons; polygon quality is the open question {#f4}
*2026-09-27 · Phase 1 (preliminary)*

1,980 of the 4,552 gauged catchments are GSIM stations. For all of them we compared the authors' `Area` with the GSIM catalogue (Do et al. 2018, `GSIM_metadata.zip`).

- Against the GSIM polygon area (`area.est`) the authors' `Area` agrees within 10 % for 99.6 % of gauges (median ratio 1.004). The same values appear in `upstream/data`, so the model saw these areas.
- Against the GSIM *reported* area, 29 % differ by more than 2×, but 577 of those 588 are US gauges at a median ratio of 2.61. That's km² per mi², so the gap is a unit issue in GSIM's reported field, not an error by the authors.
- The polygons themselves are a weaker point. GSIM rates 226 of the authors' unflagged polygons "Low" quality and 198 "Caution" (no reported area to check against). 19 unflagged polygons differ from the reported area by more than 50 %: 16 dormant complex, 3 intermediate.
- Not covered: the 2,572 gauges from CAMELS and other sources.

---

## F3. Two features of the labelling rule that the class names hide {#f3}
*2026-09-27 · Phase 0, Check A*

- **Most "simple" gauges have significant thresholds.** 177 of 210 dormant-season simple gauges (65 of 73 growing) also have a statistically significant breakpoint (score test, p < 0.05). The rule checks the linear fit first, so any gauge with linear R² ≥ 0.75 is simple no matter how clear its threshold is. "Simple" means *well fitted by a line*, not *free of threshold behaviour*.
- **Intermediates labelled through the segmented fit alone rest on a handful of events.** 44 dormant and 60 growing intermediates have linear R² < 0.5 and reach segmented R² ≥ 0.75. In every one, the segment above the upper breakpoint holds 5–15 % of the events: a median of 4.5 (dormant) and 6 (growing) events, and as few as 2. These are 2.8 % and 5.6 % of all intermediates, so the class totals barely depend on them. Their individual labels, though, depend on a few of the largest storms.

---

## F2. Phase 0 Check A passes: the regression step reproduces 99.94 % of labels {#f2}
*2026-09-27 · Phase 0, Check A*

We refitted every catchment-season in the authors' event catalogue (9,000 fits: 4,552 dormant, 4,448 growing with ≥ 15 events). The fits used R `segmented` 2.1.4 through rpy2: an OLS linear fit, then up to two breakpoints added one at a time, each kept only if its score test (Muggeo 2016) gives p < 0.05. Labels follow the Methods rule.

| Season | Agreement | Simple reproduced | Mismatches |
|---|---:|---:|---|
| Dormant | 4,548 / 4,552 (99.91 %) | 210 / 210 | 2 intermediate→complex, 2 complex→intermediate |
| Growing | 4,447 / 4,448 (99.98 %) | 73 / 73 | 1 intermediate→complex |

This is well above the go threshold (≥ 95 %, all 210 dormant simple). Four of the five mismatches are small samples (15–44 events), three of them with a score-test p-value between 0.04 and 0.10. The fifth, a growing-season gauge with 122 events, has segmented R² 0.72 against the 0.75 cut. All five are consistent with small differences in breakpoint optimisation, since `segmented` uses random restarts. Per-gauge detail is in the results file.

**Implementation cross-check.** Against the per-catchment R² in the authors' 2024 release (Zenodo 14253670), our fits match to within 0.0001 for all 528 linear models. For the 185 one-breakpoint models the median difference is 0.0000 (max 0.036).

**Readings of the Methods that do not match as well.** Muggeo's `selgmented()` selector gives 99.67 % / 99.89 %. Taking the best segmented fit regardless of significance gives 99.52 % / 99.62 %. Dropping the significance test changes 22 dormant and 16 growing labels.

**What this shows:** given their event catalogue, their labels are reproducible and the Methods describe the rule accurately.
**What it does not show:** that the event catalogue reproduces from raw data. That is Check B, in progress.

Code: `src/stormflow_diag/stage1/{regression.py,segfit.R}`, `scripts/phase0_check_a.py`. Per-gauge output: `results/phase0/check_a_fits.csv`.

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
