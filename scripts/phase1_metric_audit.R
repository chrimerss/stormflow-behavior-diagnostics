# Audit of the performance metrics in upstream/code/Reproducing_XGBoost_Models_Results.Rmd
#
# Runs the authors' own code, extracted verbatim from the Rmd (setup chunk and
# "handy functions" chunk; only the map-drawing libraries are skipped), on
# their released models and train/test split. It then prints:
#   1. the orientation of caret's confusion table (which margin is Prediction),
#   2. the authors' metric table (should reproduce their rendered HTML),
#   3. the same metrics computed with the conventional definitions.
#
# Run from the repo root:  Rscript scripts/phase1_metric_audit.R
# (conda env `stormflow-r`: R 4.3, xgboost 1.7.6, caret)

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
})

rmd <- readLines("upstream/code/Reproducing_XGBoost_Models_Results.Rmd")
chunk <- function(header) {
  start <- grep(header, rmd, fixed = TRUE)[1] + 1
  end <- start + which(rmd[start:length(rmd)] == "```")[1] - 2
  rmd[start:end]
}
skip <- "library\\((tidyverse|maptiles|tidyterra|sf|scales|ggthemes|rnaturalearth)\\)"
setup <- chunk("```{r get packages and data")
setup <- setup[!grepl(skip, setup)]

old <- setwd("upstream")          # here() resolves to upstream/ (stormflow-behavior.Rproj)
suppressPackageStartupMessages(library(here))
i_am("code/Reproducing_XGBoost_Models_Results.Rmd")
eval(parse(text = setup))
eval(parse(text = chunk("```{r handy functions}")))
setwd(old)

conventional <- function(model, dmatrix, obs_labels) {
  pred <- max.col(predict(model, newdata = dmatrix, reshape = TRUE)) - 1
  obs <- as.numeric(obs_labels) - 1
  keep <- !is.na(obs)
  pred <- pred[keep]; obs <- obs[keep]
  one <- function(k) {
    tp <- sum(pred == k & obs == k); fp <- sum(pred == k & obs != k)
    fn <- sum(pred != k & obs == k); tn <- sum(pred != k & obs != k)
    c(precision = tp / (tp + fp), recall = tp / (tp + fn),
      specificity = tn / (tn + fp), npv = tn / (tn + fn))
  }
  out <- t(sapply(0:2, one))
  data.frame(behavioral_class = c("Simple", "Intermediate", "Complex"), round(out, 3))
}

for (season in c("dormant", "growing")) {
  model <- if (season == "dormant") dormant_model else growing_model
  train_ids <- if (season == "dormant") training_ids_dormant else training_ids_growing
  cls <- paste0(season, "_gauged_class")

  test <- xgboost_gauged_atts %>%
    dplyr::filter(period == season) %>%
    dplyr::filter(!GCIN %in% train_ids) %>%
    left_join(df_atts_gauged %>% dplyr::select(all_of(c("GCIN", cls))), by = "GCIN") %>%
    dplyr::select(-c(GCIN, period)) %>%
    rename(Class = all_of(cls)) %>%
    drop_na(Class)                  # as in the authors' growing-season chunk
  feats <- test %>% dplyr::select(-Class)
  dtest <- xgb.DMatrix(data = as.matrix(feats), label = as.numeric(test$Class) - 1)

  cat("\n==========", toupper(season), "test set ==========\n")
  pred <- max.col(predict(model, newdata = dtest, reshape = TRUE)) - 1
  cm <- caret::confusionMatrix(ordered(pred, levels = c(0, 1, 2)),
                               ordered(as.numeric(test$Class) - 1, levels = c(0, 1, 2)))
  cat("caret confusion table (0 = simple, 1 = intermediate, 2 = complex):\n")
  print(cm$table)

  cat("\nAuthors' eval_metrics_exe() (as rendered in their HTML):\n")
  print(eval_metrics_exe(model, dtest, test$Class) %>% mutate(across(where(is.numeric), ~ round(.x, 3))))

  cat("\nConventional definitions (precision = TP / predicted, recall = TP / observed):\n")
  print(conventional(model, dtest, test$Class))
}
