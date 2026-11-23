"""Figures for the revised manuscript.  python -m maverick_r1.figures results_r1"""
import sys, json, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
out = sys.argv[1] if len(sys.argv) > 1 else "results_r1"
t = pd.read_json(f"{out}/table_main.json")
plt.rcParams.update({"font.size": 8, "font.family": "serif"})
# Fig 2: leakage with CI, coloured by evidence role
fig, ax = plt.subplots(figsize=(3.5, 2.3), dpi=300)
role = {"B0": "#7f7f7f", "B3": "#7f7f7f", "B1": "#d62728", "B2": "#d62728", "B4": "#ff7f0e", "B5": "#ff7f0e",
        "B6": "#9467bd", "B7": "#9467bd", "B8": "#9467bd", "M": "#1f77b4", "M-ledger": "#aec7e8",
        "M-critic": "#aec7e8", "M-policy": "#aec7e8"}
x = np.arange(len(t)); lo = t.leakage - t.leakage_ci.str[0]; hi = t.leakage_ci.str[1] - t.leakage
ax.bar(x, t.leakage * 100, yerr=[lo * 100, hi * 100], color=[role[c] for c in t.cfg], capsize=1.5, linewidth=0)
ax.set_xticks(x); ax.set_xticklabels([c.replace("M-", "M\u2212") for c in t.cfg], rotation=60, fontsize=7)
ax.set_ylabel("Pooled leakage (%)"); ax.set_ylim(0, 62)
for i, v in enumerate(t.leakage * 100): ax.text(i, v + hi.iloc[i] * 100 + 1, f"{v:.1f}", ha="center", fontsize=5.5)
fig.tight_layout(); fig.savefig(f"{out}/fig2_leakage.png"); plt.close(fig)
# Fig 3: GUA win rates and PRCC
s = json.load(open(f"{out}/summary.json"))
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.3), dpi=300)
w = s["gua"]["win_rate_leakage"]; ks = list(w)
a1.barh(range(len(ks)), [w[k] * 100 for k in ks], color="#1f77b4")
a1.barh(len(ks), s["gua"]["win_rate_abs_escapes_vs_B3"] * 100, color="#ff7f0e")
a1.set_yticks(range(len(ks) + 1)); a1.set_yticklabels([f"M < {k.replace('M-','M−')} (leakage)" for k in ks] + ["M < B3 (escapes/release)"], fontsize=6.5)
a1.set_xlabel("Share of 256 parameter points (%)"); a1.set_xlim(0, 105); a1.invert_yaxis()
pr = s["gua"]["prcc"]["leak_M"]; items = sorted(pr.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
a2.barh(range(len(items)), [v for _, v in items], color=["#d62728" if v > 0 else "#2ca02c" for _, v in items])
a2.set_yticks(range(len(items))); a2.set_yticklabels([k for k, _ in items], fontsize=6.5); a2.invert_yaxis()
a2.set_xlabel("PRCC with M leakage"); a2.axvline(0, color="k", lw=0.5); a2.set_xlim(-1, 1)
fig.tight_layout(); fig.savefig(f"{out}/fig3_gua.png"); plt.close(fig)
print("ok")
