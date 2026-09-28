---
title: Findings
nav_order: 2
---

# Findings log

Newest first. Each entry gives the numbers, how they were produced, and what they do and do not show.

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
