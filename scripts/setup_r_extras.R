# R packages the upstream notebook needs that conda-forge does not provide.
# Run once inside the activated env:  Rscript scripts/setup_r_extras.R

options(repos = c(CRAN = "https://cloud.r-project.org"))

if (!requireNamespace("tidyterra", quietly = TRUE)) {
  install.packages("tidyterra")
}
if (!requireNamespace("rnaturalearthhires", quietly = TRUE)) {
  install.packages("rnaturalearthhires", repos = "https://ropensci.r-universe.dev", type = "source")
}
