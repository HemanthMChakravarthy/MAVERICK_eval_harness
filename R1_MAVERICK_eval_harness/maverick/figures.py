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
# --- R1 page-8 additions: compact single-column figures used in the manuscript ---
# Fig 2 (manuscript): GUA win rates and PRCC, single column
lab = {"B3": "B3", "B4": "B4", "B5": "B5", "B6": "B6", "B7": "B7", "B8": "B8",
       "M-ledger": "M\u2212led.", "M-critic": "M\u2212crit.", "M-policy": "M\u2212pol."}
fig, (a1, a2) = plt.subplots(1, 2, figsize=(3.5, 1.75), dpi=300, gridspec_kw={"width_ratios": [1, 1]})
a1.barh(range(len(ks)), [w[k] * 100 for k in ks], color="#1f77b4")
a1.barh(len(ks), s["gua"]["win_rate_abs_escapes_vs_B3"] * 100, color="#ff7f0e")
a1.set_yticks(range(len(ks) + 1)); a1.set_yticklabels([lab.get(k, k) for k in ks] + ["B3 (abs.)"], fontsize=6)
a1.set_xlabel("Points where M is lower (%)", fontsize=6.5); a1.set_xlim(0, 100); a1.invert_yaxis()
a1.tick_params(axis="x", labelsize=6); a1.set_title("(a) M vs. configuration", fontsize=7)
nm = {"critic_recall": "critic recall", "h_sm": "sem. review", "corr": "correlation", "h_li": "LI review",
      "fatigue_slope": "fatigue", "test_scale": "test strength", "critic_far": "critic FAR", "p_human": "human density", "p_llm": "LLM density", "p_fix_llm": "repair success", "p_fix_escalation": "escalation success", "p_self_approval": "self-approval", "llm_reviewer_recall": "LLM reviewer", "release_st": "release review", "audit_recall": "audit recall", "h_st": "struct. review"}
it = items[:7]
a2.barh(range(len(it)), [v for _, v in it], color=["#d62728" if v > 0 else "#2ca02c" for _, v in it])
a2.set_yticks(range(len(it))); a2.set_yticklabels([nm.get(k, k) for k, _ in it], fontsize=6); a2.invert_yaxis()
a2.axvline(0, color="k", lw=0.5); a2.set_xlim(-1, 1); a2.tick_params(axis="x", labelsize=6)
a2.set_xlabel("PRCC with M leakage", fontsize=6.5); a2.set_title("(b) Drivers", fontsize=7)
fig.tight_layout(pad=0.3, w_pad=0.6); fig.savefig(f"{out}/fig2_gua_1col.png"); plt.close(fig)
# Fig 3 (manuscript): break-even vs. defect-density ratio and audit-recall sweep
G = pd.read_csv(f"{out}/gua_points.csv"); r = G.p_llm / G.p_human
q = (G.esc_M + 0.01) / (G.esc_B3 + 0.01)
fig, (b1, b2) = plt.subplots(1, 2, figsize=(3.5, 1.55), dpi=300)
b1.scatter(r, q, s=3, c=np.where(G.esc_M < G.esc_B3, "#1f77b4", "#ff7f0e"), linewidths=0)
b1.set_xscale("log"); b1.set_yscale("log"); b1.axhline(1, color="k", lw=0.5)
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator
for ax_, tv in ((b1.xaxis, [1, 2, 5, 10]), (b1.yaxis, [0.2, 0.5, 1, 2, 5])):
    ax_.set_major_locator(FixedLocator(tv)); ax_.set_major_formatter(FixedFormatter([f"{v:g}" for v in tv])); ax_.set_minor_locator(NullLocator()); ax_.set_minor_formatter(matplotlib.ticker.NullFormatter())
b1.set_xlabel("LLM/human defect density", fontsize=6.5); b1.set_ylabel("M/B3 escapes", fontsize=6.5)
b1.tick_params(labelsize=6); b1.set_title("(a) Break-even", fontsize=7)
A = pd.read_csv(f"{out}/audit_sweep.csv")
b2.plot(A.audit_recall, A.B5_field_esc, "o-", ms=2, lw=1, color="#ff7f0e", label="B5 after audit")
b2.plot(A.audit_recall, A.M_esc, "-", lw=1, color="#1f77b4", label="M at gate")
b2.set_xlabel("Assumed audit recall", fontsize=6.5); b2.set_ylabel("Escapes/release", fontsize=6.5)
b2.tick_params(labelsize=6); b2.legend(fontsize=5.5, frameon=False); b2.set_title("(b) Post-hoc audit", fontsize=7)
fig.tight_layout(pad=0.3, w_pad=0.6); fig.savefig(f"{out}/fig3_breakeven_1col.png"); plt.close(fig)
print("ok (R1 single-column figures)")
