# stormflow-behavior-diagnostics

Independent robustness diagnostics for

> Ameli, A. A., Sharif, H. & McDonnell, J. J. *A global classification of hydrologic functional diversity in gauged and ungauged catchments.* Nature Water (2026). https://doi.org/10.1038/s44221-026-00699-6

The paper sorts rain-dominated catchments into three seasonal functional types (simple, intermediate, complex) from event-scale rainfall–runoff behaviour in gauged catchments, then extrapolates the labels to 77,585 ungauged catchments with two season-specific XGBoost classifiers. This repository re-runs the authors' released code and data and tests whether the headline conclusions survive reasonable changes to the analysis.

## Provenance

| Item | Source | Pinned |
|---|---|---|
| Authors' code and trained models | [h-sharif/stormflow-behavior](https://github.com/h-sharif/stormflow-behavior) | git submodule `upstream/` at `932f810` |
| Data (streamflow, climate, event catalogue, attributes) | Figshare, https://figshare.com/s/24fca5b7d89829035ff1 (paper ref. 79) | see [data/README.md](data/README.md) |

The diagnostics never modify `upstream/`; any change to the authors' pipeline lives in this repository.

## Layout

```
upstream/      authors' code, models and gauged/ungauged attribute tables (submodule, read-only)
data/          Figshare package, not tracked by git
experiments/   one folder per diagnostic
results/       generated tables and figures
```

## Setup

```bash
git clone --recurse-submodules https://github.com/chrimerss/stormflow-behavior-diagnostics.git
cd stormflow-behavior-diagnostics
mamba env create -f environment.yml
mamba activate stormflow-diag
```

Then place the Figshare package under `data/` as described in [data/README.md](data/README.md).

## Status

- [x] Repository and upstream pin
- [ ] Data in place
- [ ] Baseline reproduction of the authors' reported results
- [ ] Diagnostic experiments (plan pending)

## License

MIT for code in this repository. `upstream/` keeps its own MIT license (© 2025 Hamed Sharif). The Figshare data follow the terms stated there.
