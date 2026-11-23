import numpy as np
from scipy import stats as st

def boot_ci(x, fn=np.mean, B=2000, seed=0):
    x = np.asarray(x); rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), (B, len(x)))
    v = np.array([fn(x[i]) for i in idx])
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

def boot_ratio_ci(num, den, B=2000, seed=0):
    """CI of sum(num)/sum(den) resampling seeds."""
    num, den = np.asarray(num, float), np.asarray(den, float); rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(num), (B, len(num)))
    v = num[idx].sum(1) / den[idx].sum(1)
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

def cliffs_delta(a, b):
    a, b = np.asarray(a), np.asarray(b)
    gt = (a[:, None] > b[None, :]).sum(); lt = (a[:, None] < b[None, :]).sum()
    return (gt - lt) / (len(a) * len(b))

def cliffs_ci(a, b, B=1000, seed=0):
    a, b = np.asarray(a), np.asarray(b); rng = np.random.default_rng(seed); n = len(a)
    v = []
    for _ in range(B):
        i = rng.integers(0, n, n)      # paired resampling of seeds
        v.append(cliffs_delta(a[i], b[i]))
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

def wilcoxon_p(a, b):
    d = np.asarray(a) - np.asarray(b)
    if np.all(d == 0):
        return 1.0
    return float(st.wilcoxon(a, b, zero_method="wilcox").pvalue)

def holm(pvals):
    p = np.asarray(pvals); m = len(p); order = np.argsort(p); adj = np.empty(m); run = 0
    for r, i in enumerate(order):
        run = max(run, (m - r) * p[i]); adj[i] = min(1.0, run)
    return adj

def magnitude(d):
    d = abs(d)
    return "negligible" if d < 0.147 else "small" if d < 0.33 else "medium" if d < 0.474 else "large"

def lhs(n, k, seed=0):
    rng = np.random.default_rng(seed)
    cut = np.linspace(0, 1, n + 1)
    u = rng.random((n, k)) * (cut[1:] - cut[:-1])[:, None] + cut[:-1][:, None]
    for j in range(k):
        u[:, j] = u[rng.permutation(n), j]
    return u

def prcc(X, y):
    """Partial rank correlation coefficients of each column of X with y."""
    from scipy.stats import rankdata
    R = np.column_stack([rankdata(c) for c in X.T]); ry = rankdata(y)
    out = []
    for j in range(R.shape[1]):
        others = np.delete(R, j, axis=1); A = np.column_stack([np.ones(len(ry)), others])
        rx = R[:, j] - A @ np.linalg.lstsq(A, R[:, j], rcond=None)[0]
        rr = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
        out.append(float(np.corrcoef(rx, rr)[0, 1]))
    return out
