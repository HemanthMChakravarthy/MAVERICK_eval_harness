"""Statistics per Sec. V-C: medians, bootstrap 95% CI, Wilcoxon signed-rank with Holm correction."""
import numpy as np
from scipy.stats import wilcoxon

def median_ci(x, B=10000, seed=0):
    x = np.asarray(x, float); rng = np.random.default_rng(seed)
    bs = np.median(rng.choice(x, (B, len(x))), axis=1)
    return float(np.median(x)), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))

def holm(pvals):
    k = sorted(pvals, key=pvals.get); m = len(k); out, run = {}, 0
    for i, key in enumerate(k):
        run = max(run, min(1, (m - i) * pvals[key])); out[key] = run
    return out

def compare(runs, ref="MAVERICK", metric="tc"):
    """runs: {config: [dict(metric=value) per paired run]} -> Holm-adjusted p vs ref."""
    p = {}
    for c, r in runs.items():
        if c == ref: continue
        a = [x[metric] for x in runs[ref]]; b = [x[metric] for x in r]
        p[c] = 1.0 if np.allclose(a, b) else float(wilcoxon(a, b).pvalue)
    return holm(p)
