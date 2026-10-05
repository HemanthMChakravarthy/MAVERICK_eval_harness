"""Descriptive and inferential statistics for the harness.

- ``bootstrap_ci``: bootstrap 95% confidence intervals for a mean (seeded).
- ``wilcoxon_signed_rank``: paired Wilcoxon signed-rank test (normal
  approximation with tie correction and continuity correction), implemented
  directly on the standard library + numpy so the harness has no scipy
  dependency.
- ``cliffs_delta``: Cliff's delta effect size for two independent samples
  (with a paired-difference variant), the recommended companion/replacement
  for p-values at small n.
- ``holm``: Holm step-down correction for a family of p-values.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

import numpy as np


def bootstrap_ci(
    data: Sequence[float],
    n_boot: int = 2000,
    ci: float = 0.95,
    seed: int = 12345,
) -> Tuple[float, float, float]:
    """Return (mean, lower, upper) bootstrap CI for the mean."""
    arr = np.asarray(list(data), dtype=float)
    if arr.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    boots = rng.choice(arr, size=(n_boot, arr.size), replace=True).mean(axis=1)
    alpha = 1.0 - ci
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(arr.mean()), float(lo), float(hi)


def wilcoxon_signed_rank(
    x: Sequence[float], y: Sequence[float]
) -> Tuple[float, float]:
    """Paired Wilcoxon signed-rank test; returns (statistic W+, two-sided p).

    Normal approximation with tie correction and continuity correction.
    Zero differences are dropped (standard).
    """
    xa = np.asarray(list(x), dtype=float)
    ya = np.asarray(list(y), dtype=float)
    d = xa - ya
    d = d[d != 0.0]
    n = d.size
    if n == 0:
        return 0.0, 1.0
    ad = np.abs(d)
    order = np.argsort(ad, kind="mergesort")
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:  # average ranks for ties
        j = i
        while j + 1 < n and ad[order[j + 1]] == ad[order[i]]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    w_plus = float(ranks[d > 0].sum())
    _, counts = np.unique(ad, return_counts=True)
    tie_correction = float(np.sum(counts**3 - counts)) / 48.0
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie_correction
    mean = n * (n + 1) / 4.0
    if var <= 0:
        return w_plus, 1.0
    z = (w_plus - mean - 0.5 * math.copysign(1.0, w_plus - mean)) / math.sqrt(var)
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return w_plus, float(min(max(p, 0.0), 1.0))


def cliffs_delta(
    x: Sequence[float], y: Sequence[float]
) -> Tuple[float, str]:
    """Cliff's delta effect size for paired samples (x vs y).

    Computed on the paired differences d = x - y as
    ``delta = (#(d > 0) - #(d < 0)) / n`` -- the matched-pairs rank-biserial
    correlation, which coincides with Cliff's delta for the difference
    distribution. Positive delta means x tends to exceed y.

    Returns (delta, magnitude) with the conventional thresholds
    (Romano et al.): |d| < 0.147 negligible, < 0.33 small, < 0.474 medium,
    otherwise large.
    """
    xa = np.asarray(list(x), dtype=float)
    ya = np.asarray(list(y), dtype=float)
    d = xa - ya
    n = d.size
    if n == 0:
        return float("nan"), "n/a"
    delta = (np.sum(d > 0) - np.sum(d < 0)) / n
    a = abs(float(delta))
    if a < 0.147:
        mag = "negligible"
    elif a < 0.33:
        mag = "small"
    elif a < 0.474:
        mag = "medium"
    else:
        mag = "large"
    return float(delta), mag


def holm(pvals: Sequence[float]) -> List[float]:
    """Holm step-down adjusted p-values (family-wise error control)."""
    p = np.asarray(list(pvals), dtype=float)
    m = p.size
    if m == 0:
        return []
    order = np.argsort(p, kind="mergesort")
    adj = np.empty(m, dtype=float)
    for rank, idx in enumerate(order):
        adj[idx] = min((m - rank) * p[idx], 1.0)
    for i in range(1, m):  # enforce monotonicity
        if adj[order[i]] < adj[order[i - 1]]:
            adj[order[i]] = adj[order[i - 1]]
    return [float(v) for v in adj]
