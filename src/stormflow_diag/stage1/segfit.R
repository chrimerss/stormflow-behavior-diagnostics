# Rainfall-runoff regression for one catchment-season, following the Methods of
# Ameli, Sharif & McDonnell (2026): OLS of event stormflow volume on event rainfall
# volume, then segmented regression with up to two breakpoints whose significance
# is tested with Muggeo's (2016) score test.
#
# Returns a named list of scalars so rpy2 can convert it without surprises.
# Every quantity used by any labelling variant is returned; the labelling rule
# itself lives in Python (regression.py).

suppressPackageStartupMessages(library(segmented))

.seg_r2 <- function(fit) {
  if (is.null(fit) || !inherits(fit, "segmented")) return(NA_real_)
  summary(fit)$r.squared
}

.try_segmented <- function(olm, npsi, seed) {
  set.seed(seed)
  fit <- tryCatch(
    suppressWarnings(segmented(olm, seg.Z = ~x, npsi = npsi)),
    error = function(e) NULL
  )
  # segmented() returns the plain lm when it cannot place a breakpoint
  if (!is.null(fit) && !inherits(fit, "segmented")) fit <- NULL
  if (!is.null(fit) && nrow(fit$psi) != npsi) fit <- NULL
  fit
}

.pscore <- function(obj, more_break, seed) {
  set.seed(seed)
  tryCatch(
    suppressWarnings(pscore.test(obj, seg.Z = ~x, more.break = more_break)$p.value),
    error = function(e) NA_real_
  )
}

fit_catchment <- function(x, y, alpha = 0.05, seed = 1L) {
  d <- data.frame(x = as.numeric(x), y = as.numeric(y))
  # segmented() and pscore.test() re-evaluate the lm call; embed the data in
  # the call so they do not look for `d` in the global environment
  olm <- eval(bquote(lm(y ~ x, data = .(d))))

  seg1 <- .try_segmented(olm, 1, seed)
  seg2 <- .try_segmented(olm, 2, seed)

  # Sequential score tests: 0 vs 1 breakpoint on the linear fit, then
  # 1 vs 2 on the one-breakpoint fit.
  p01 <- .pscore(olm, FALSE, seed)
  p12 <- if (is.null(seg1)) NA_real_ else .pscore(seg1, TRUE, seed)

  k_seq <- 0L
  if (!is.na(p01) && p01 < alpha && !is.null(seg1)) {
    k_seq <- 1L
    if (!is.na(p12) && p12 < alpha && !is.null(seg2)) k_seq <- 2L
  }

  # Muggeo's own selector with the score test (applies its own alpha handling)
  set.seed(seed)
  sel <- tryCatch(
    suppressWarnings(selgmented(olm, seg.Z = ~x, Kmax = 2, type = "score",
                                alpha = alpha, msg = FALSE)),
    error = function(e) NULL
  )
  k_sel <- if (is.null(sel) || !inherits(sel, "segmented")) 0L else nrow(sel$psi)

  psi <- function(fit, i) if (is.null(fit) || nrow(fit$psi) < i) NA_real_ else fit$psi[i, "Est."]

  list(
    n = nrow(d),
    r2_lin = summary(olm)$r.squared,
    slope_lin = unname(coef(olm)[2]),
    intercept_lin = unname(coef(olm)[1]),
    r2_seg1 = .seg_r2(seg1),
    r2_seg2 = .seg_r2(seg2),
    psi1_seg1 = psi(seg1, 1),
    psi1_seg2 = psi(seg2, 1),
    psi2_seg2 = psi(seg2, 2),
    p_score_01 = p01,
    p_score_12 = p12,
    k_seq = k_seq,
    k_selgmented = k_sel,
    r2_selgmented = if (k_sel == 0L) summary(olm)$r.squared else .seg_r2(sel)
  )
}
