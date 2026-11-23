"""Regenerates every number and figure of the revised manuscript.

    python -m maverick_r1.experiments --out results_r1 [--quick]
"""
from __future__ import annotations
import argparse, json, os, time
import numpy as np, pandas as pd
from .sim import run_one, fixture
from .configs import C, MAIN
from .params import BASE
from . import stats as S
from .faults import NAMES, CAT, targets, profile, mutate
from .ledger import aeb_fixture

SEEDS = 500

def run_set(cfgs, seeds, fx="aeb", P=None):
    return pd.DataFrame([run_one(c, s, fx, P) for c in cfgs for s in range(seeds)]).fillna(0)

def summarize(df):
    rows = []
    for c, g in df.groupby("cfg", sort=False):
        lk = g.escapes.sum() / g.injected.sum()
        rows.append(dict(
            cfg=c, label=C[c]["label"],
            tc_final=g.tc_final.mean(), tc_final_ci=S.boot_ci(g.tc_final),
            tc_first=g.tc_first.mean(), tc_first_ci=S.boot_ci(g.tc_first),
            leakage=lk, leakage_ci=S.boot_ratio_ci(g.escapes, g.injected),
            esc_per_release=g.escapes.mean(), esc_ci=S.boot_ci(g.escapes),
            St=int(g.st.sum()), Sm=int(g.sm.sum()), LI=int(g.li.sum()),
            residual=g.residual.mean(), minutes=g.minutes.mean(), minutes_ci=S.boot_ci(g.minutes),
            retries=g.retries.mean(),
            **{k: g[k].mean() for k in g.columns if k.startswith("r_")},
            escalations=g.escalations.mean(), advisories=g.advisories.mean(),
            field_escapes=g.field_escapes.mean(), coverage=g.coverage.mean(),
            injected=g.injected.mean(),
            **{k: int(g[k].sum()) for k in g.columns if k.startswith("c_")}))
    return pd.DataFrame(rows)

def effect_sizes(df, ref="M"):
    a = df[df.cfg == ref].sort_values("seed").escapes.values
    rows = []
    for c in df.cfg.unique():
        if c == ref: continue
        b = df[df.cfg == c].sort_values("seed").escapes.values
        d = S.cliffs_delta(a, b)
        rows.append(dict(vs=c, delta=d, ci=S.cliffs_ci(a, b), mag=S.magnitude(d), p=S.wilcoxon_p(a, b)))
    out = pd.DataFrame(rows); out["p_holm"] = S.holm(out.p.values)
    return out

def break_even(df):
    m, b3 = df[df.cfg == "M"], df[df.cfg == "B3"]
    ratio = (b3.escapes.sum() / b3.injected.sum()) / (m.escapes.sum() / m.injected.sum())
    rng = np.random.default_rng(1); n = len(m); v = []
    me, mi, be, bi = m.escapes.values, m.injected.values, b3.escapes.values, b3.injected.values
    for _ in range(2000):
        i = rng.integers(0, n, n)
        v.append((be[i].sum() / bi[i].sum()) / (me[i].sum() / mi[i].sum()))
    return dict(ratio=ratio, ci=(float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))),
                assumed_density_ratio=BASE["p_llm"] / BASE["p_human"])

def equal_p(seeds=200):
    rows = []
    for p in [0.05, 0.10, 0.15, 0.25, 0.50, 0.75]:
        d = run_set(["M", "B3"], seeds, P=dict(p_llm=p, p_human=p))
        lm = d[d.cfg == "M"].escapes.sum() / d[d.cfg == "M"].injected.sum()
        lb = d[d.cfg == "B3"].escapes.sum() / d[d.cfg == "B3"].injected.sum()
        rows.append(dict(p=p, leak_M=lm, leak_B3=lb, ratio=lb / lm))
    return pd.DataFrame(rows)

def corr_sweep(seeds=500):
    rows = []
    for corr in [0.0, 0.2, 0.5]:
        d = run_set(["M", "M-critic", "B4"], seeds, P=dict(corr=corr))
        for c, g in d.groupby("cfg"):
            rows.append(dict(corr=corr, cfg=c, leakage=g.escapes.sum() / g.injected.sum(),
                             esc=g.escapes.mean()))
    return pd.DataFrame(rows)

def audit_sweep(seeds=500):
    rows = []
    m = run_set(["M"], seeds)
    for r in [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99]:
        d = run_set(["B5"], seeds, P=dict(audit_recall=r))
        rows.append(dict(audit_recall=r, B5_gate_leakage=d.escapes.sum() / d.injected.sum(),
                         B5_field_esc=d.field_escapes.mean(), M_esc=m.escapes.mean()))
    return pd.DataFrame(rows)

GUA_RANGES = dict(
    p_llm=(0.30, 0.90), p_human=(0.05, 0.30), critic_recall=(0.40, 0.90), critic_far=(0.02, 0.25),
    corr=(0.0, 0.5), h_st=(0.75, 0.98), h_sm=(0.60, 0.95), h_li=(0.50, 0.90), fatigue_slope=(0.0, 0.6),
    test_scale=(0.5, 1.5), p_fix_llm=(0.60, 0.95), p_self_approval=(0.0, 0.4),
    llm_reviewer_recall=(0.2, 0.7), release_st=(0.25, 0.70), audit_recall=(0.6, 0.95))
GUA_CFGS = ["M", "B3", "B4", "B5", "B6", "B7", "B8", "M-ledger", "M-critic", "M-policy"]

def gua(points=256, seeds=100):
    keys = list(GUA_RANGES); U = S.lhs(points, len(keys), seed=7)
    X = np.array([[GUA_RANGES[k][0] + u * (GUA_RANGES[k][1] - GUA_RANGES[k][0]) for k, u in zip(keys, row)] for row in U])
    recs = []
    for j, x in enumerate(X):
        P = dict(zip(keys, x))
        d = run_set(GUA_CFGS, seeds, P=P)
        rec = dict(P)
        for c, g in d.groupby("cfg"):
            rec[f"leak_{c}"] = g.escapes.sum() / max(1, g.injected.sum())
            rec[f"esc_{c}"] = g.escapes.mean()
            rec[f"tcF_{c}"] = g.tc_final.mean(); rec[f"tcFmin_{c}"] = g.tc_final.min()
            rec[f"st_{c}"] = g.st.sum(); rec[f"tc1_{c}"] = g.tc_first.mean()
            rec[f"res_{c}"] = g.residual.mean(); rec[f"min_{c}"] = g.minutes.mean()
        recs.append(rec)
    G = pd.DataFrame(recs)
    win = {c: float((G["leak_M"] < G[f"leak_{c}"]).mean()) for c in GUA_CFGS if c != "M"}
    win_abs_B3 = float((G["esc_M"] < G["esc_B3"]).mean())
    pr = {}
    for target, y in [("dleak_B4_minus_M", G["leak_B4"] - G["leak_M"]),
                      ("esc_ratio_M_over_B3", G["esc_M"] / G["esc_B3"].clip(lower=1e-9)),
                      ("leak_M", G["leak_M"])]:
        pr[target] = dict(zip(keys, S.prcc(X, y.values)))
    return G, dict(win_rate_leakage=win, win_rate_abs_escapes_vs_B3=win_abs_B3, prcc=pr)

def mechanism_matrix():
    """Type-A evidence: deterministic invariant verdicts on single injected faults."""
    L = aeb_fixture(); rows = []
    for n in NAMES:
        ts = targets(L, n); ps = [profile(L, n, t, pk) for t in ts for pk in (0, 1)]
        fired = sorted(set(sum([p["fired"] for p in ps], [])))
        rows.append(dict(fault=n, category=CAT[n], instances=len(ps),
                         detected_by_invariants=sum(p["inv"] for p in ps),
                         detected_by_ALM_existence=sum(p["alm"] for p in ps), invariants_fired=",".join(fired)))
    # hash-chain tamper test and suspect propagation
    L2 = aeb_fixture(); art = L2.a["R3"]; art.payload = dict(art.payload, text="tampered"); tamper = not L2.chain_ok(art)
    L3 = aeb_fixture(); L3.revise("R3", payload={"text": "TTC < 2.0 s"})
    suspect = sorted(k for k, v in L3.a.items() if v.status == "suspect")
    return pd.DataFrame(rows), dict(hash_tamper_detected=tamper, suspect_after_R3_change=suspect)

def evidence_classes(G):
    """Classify M outcomes by their variance over the GUA parameter space."""
    out = {}
    for m in ["tcF", "tcFmin", "st", "res", "tc1", "leak", "esc", "min"]:
        v = G[f"{m}_M"]; out[m] = dict(min=float(v.min()), max=float(v.max()))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="results_r1")
    ap.add_argument("--quick", action="store_true"); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); t0 = time.time()
    seeds = 60 if a.quick else SEEDS
    main_df = run_set(MAIN, seeds); main_df.to_csv(f"{a.out}/per_seed_aeb.csv", index=False)
    summ = summarize(main_df); summ.to_json(f"{a.out}/table_main.json", orient="records", indent=1)
    es = effect_sizes(main_df); es.to_json(f"{a.out}/effect_sizes.json", orient="records", indent=1)
    be = break_even(main_df)
    eqp = equal_p(40 if a.quick else 200); eqp.to_csv(f"{a.out}/equal_p.csv", index=False)
    cs = corr_sweep(seeds); cs.to_csv(f"{a.out}/corr_sweep.csv", index=False)
    au = audit_sweep(seeds); au.to_csv(f"{a.out}/audit_sweep.csv", index=False)
    d_df = run_set(["B3", "B4", "M", "M-ledger", "M-critic", "M-policy"], seeds, fx="steer")
    d_df.to_csv(f"{a.out}/per_seed_asild.csv", index=False)
    summ_d = summarize(d_df); summ_d.to_json(f"{a.out}/table_asild.json", orient="records", indent=1)
    es_d = effect_sizes(d_df); es_d.to_json(f"{a.out}/effect_sizes_asild.json", orient="records", indent=1)
    mm, mt = mechanism_matrix(); mm.to_csv(f"{a.out}/mechanism_matrix.csv", index=False)
    G, gsum = gua(24 if a.quick else 256, 30 if a.quick else 100); G.to_csv(f"{a.out}/gua_points.csv", index=False)
    ev = evidence_classes(G)
    json.dump(dict(break_even=be, mechanism_tests=mt, gua=gsum, evidence_classes=ev,
                   seconds=time.time() - t0, seeds=seeds), open(f"{a.out}/summary.json", "w"), indent=1, default=str)
    print("done in", round(time.time() - t0, 1), "s")

if __name__ == "__main__":
    main()
