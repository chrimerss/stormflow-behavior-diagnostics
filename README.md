# stormflow-behavior-diagnostics

Independent robustness diagnostics for

> Ameli, A. A., Sharif, H. & McDonnell, J. J. *A global classification of hydrologic functional diversity in gauged and ungauged catchments.* Nature Water (2026). https://doi.org/10.1038/s44221-026-00699-6

The paper sorts rain-dominated catchments into three seasonal functional types (simple, intermediate, complex) from event-scale rainfall–runoff behaviour in gauged catchments, then extrapolates the labels to 77,585 ungauged catchments with two season-specific XGBoost classifiers. This repository re-runs the authors' released code and data and tests whether the headline conclusions survive reasonable changes to the analysis.

**Progress and findings:** https://chrimerss.github.io/stormflow-behavior-diagnostics/ (plan in [docs/PLAN.md](docs/PLAN.md))

## Provenance

| Item | Source | Pinned |
|---|---|---|
| Authors' code and trained models | [h-sharif/stormflow-behavior](https://github.com/h-sharif/stormflow-behavior) | git submodule `upstream/` at `932f810` |
| Data (streamflow, climate, event catalogue, attributes) | Figshare, https://figshare.com/s/24fca5b7d89829035ff1 (paper ref. 79) | see [data/README.md](data/README.md) |

The diagnostics never modify `upstream/`; any change to the authors' pipeline lives in this repository.

## Layout

```
upstream/             authors' code, models and gauged/ungauged attribute tables (submodule, read-only)
data/                 Figshare and Zenodo packages, not tracked by git
src/stormflow_diag/   Python package: stage1 (events + labels), predict, validate
scripts/              entry points for each check
experiments/          one folder per diagnostic
results/              generated tables and figures
docs/                 GitHub Pages site: status, findings log, plan
```

## Setup

```bash
git clone --recurse-submodules https://github.com/chrimerss/stormflow-behavior-diagnostics.git
cd stormflow-behavior-diagnostics
mamba env create -f environment.yml      # Python diagnostics (+ R segmented via rpy2)
mamba env create -f environment-r.yml    # authors' R code (xgboost 1.7.6, caret)
mamba run -n stormflow-diag pip install -e .
```

To render the authors' full notebook with maps, also run `mamba run -n stormflow-r Rscript scripts/setup_r_extras.R`.

Then place the Figshare package under `data/` as described in [data/README.md](data/README.md).

## Status

See the [status page](https://chrimerss.github.io/stormflow-behavior-diagnostics/).

## Third-party code and data

`src/stormflow_diag/stage1/events.py` is a Python translation of the DMCA-ESR event-separation code by Giulia Giani (https://github.com/giuliagiani/DMCA-ESR), described in Giani, Rico-Ramirez & Woods (2022), *Water Resources Research*. That repository states no licence; please cite the paper when using the port. `tests/fixtures/dmca_example_27071.csv.gz` is the example series shipped with that repository, and `tests/fixtures/octave/` runs the original MATLAB code in GNU Octave to check the port.

## License

MIT for code in this repository. `upstream/` keeps its own MIT license (© 2025 Hamed Sharif). The Figshare data follow the terms stated there.
