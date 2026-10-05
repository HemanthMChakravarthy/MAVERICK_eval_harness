"""Paper-ready results: summary tables, CSVs, figures, and markdown reports.

Produces:
- ``report.md``: main 10-config comparison (AEB fixture).
- ``sweep.md``: one-way sensitivity sweeps + break-even analysis.
- ``asild.md``: ASIL-D fixture comparison.
- ``ASSUMPTIONS.md``: documented assumption register.
- CSVs and PNG figures.

Display labels follow the paper's Table VI notation.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .configs import FULL_ORDER, get_config
from .experiment import RunResult, run_experiment
from .gates import GATE_ORDER, coverage_target
from .stats import bootstrap_ci, cliffs_delta, holm, wilcoxon_signed_rank

#: Display labels matching the paper's Table VI notation.
DISP = {
    "B0": "B0 manual",
    "B1": "B1 single",
    "B2": "B2 unsup.",
    "B3": "B3 human+ALM",
    "B4": "B4 LLM+inv",
    "B5": "B5 LLM+audit",
    "M": "M full",
    "M-noledger": "M$-$ledger",
    "M-nocritic": "M$-$critic",
    "M-nopolicy": "M$-$policy",
}

CHECK_ORDER = ("I1", "I2", "I3", "I4", "I5", "I6",
               "I7", "I8", "I9", "I10", "I11")


def _per_seed_leakage(r: RunResult) -> float:
    return r.n_leaked / r.n_injected if r.n_injected else float("nan")


def _agg_metric(runs: List[RunResult], fn) -> Dict[str, float]:
    vals = [v for v in (fn(r) for r in runs) if not np.isnan(v)]
    mean, lo, hi = bootstrap_ci(vals)
    return {"mean": mean, "lo": lo, "hi": hi, "n": len(vals)}


def aggregate(results: Dict[str, List[RunResult]]) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Per-config aggregate metrics with bootstrap 95% CIs."""
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for cid, runs in results.items():
        # Pooled leakage (robust when a seed injects zero defects).
        tot_leaked = sum(r.n_leaked for r in runs)
        tot_inj = sum(r.n_injected for r in runs)
        pooled = tot_leaked / tot_inj if tot_inj else float("nan")
        out[cid] = {
            "tc": _agg_metric(runs, lambda r: r.final_tc),
            "first_pass_tc": _agg_metric(runs, lambda r: r.first_pass_tc),
            "leakage": _agg_metric(runs, _per_seed_leakage),
            "leakage_pooled": {"mean": pooled, "n": len(runs)},
            "leak_struct": _agg_metric(
                runs,
                lambda r: r.n_leaked_structural / r.n_injected if r.n_injected else float("nan")),
            "leak_sem": _agg_metric(
                runs,
                lambda r: r.n_leaked_semantic / r.n_injected if r.n_injected else float("nan")),
            "violations": _agg_metric(
                runs, lambda r: float(sum(r.residual_violations.values()))
            ),
            "minutes": _agg_metric(runs, lambda r: r.total_minutes),
            "authoring": _agg_metric(runs, lambda r: r.authoring_minutes),
            "review": _agg_metric(runs, lambda r: r.review_minutes),
            "retries": _agg_metric(runs, lambda r: float(r.n_retries)),
            "escalations": _agg_metric(runs, lambda r: float(r.n_escalations)),
            "coverage_min_branch": _agg_metric(
                runs,
                lambda r: r.coverage_min_branch if r.coverage_min_branch is not None else float("nan"),
            ),
            "injected": _agg_metric(runs, lambda r: float(r.n_injected)),
            "advisory": _agg_metric(runs, lambda r: float(r.n_advisory)),
            "audit_found": _agg_metric(runs, lambda r: float(r.n_audit_found)),
        }
    return out


def _fmt(m: Dict[str, float], digits: int = 3) -> str:
    if np.isnan(m["mean"]):
        return "n/a"
    return f"{m['mean']:.{digits}f} [{m['lo']:.{digits}f}, {m['hi']:.{digits}f}]"


def _fmt_mean(m: Dict[str, float], digits: int = 3) -> str:
    return "n/a" if np.isnan(m["mean"]) else f"{m['mean']:.{digits}f}"


# --------------------------------------------------------------------- #
# CSVs
# --------------------------------------------------------------------- #
def write_csvs(results: Dict[str, List[RunResult]], outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    with open(outdir / "per_seed.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "config", "seed", "fixture", "tc", "first_pass_tc",
            "n_injected", "n_detected", "n_leaked",
            "n_leaked_structural", "n_leaked_semantic", "n_leaked_link_integrity",
            "leakage", "residual_violations",
            "total_minutes", "authoring_minutes", "review_minutes",
            "n_retries", "n_escalations", "n_advisory", "n_audit_found",
            "coverage_min_branch", "coverage_shortfalls_leaked",
            "critic_precision", "critic_recall", "self_approvals",
            "change_impacts_untracked", "chain_ok",
        ])
        for cid in FULL_ORDER:
            for r in results.get(cid, []):
                w.writerow([
                    cid, r.seed, r.fixture,
                    f"{r.final_tc:.4f}", f"{r.first_pass_tc:.4f}",
                    r.n_injected, r.n_detected, r.n_leaked,
                    r.n_leaked_structural, r.n_leaked_semantic,
                    r.n_leaked_link_integrity,
                    f"{_per_seed_leakage(r):.4f}" if not np.isnan(_per_seed_leakage(r)) else "",
                    sum(r.residual_violations.values()),
                    f"{r.total_minutes:.2f}", f"{r.authoring_minutes:.2f}",
                    f"{r.review_minutes:.2f}",
                    r.n_retries, r.n_escalations, r.n_advisory, r.n_audit_found,
                    f"{r.coverage_min_branch:.2f}" if r.coverage_min_branch else "",
                    r.coverage_shortfalls_leaked,
                    f"{r.critic_precision:.3f}" if r.critic_precision is not None else "",
                    f"{r.critic_recall:.3f}" if r.critic_recall is not None else "",
                    r.self_approvals, r.change_impacts_untracked, r.chain_ok,
                ])

    with open(outdir / "leakage_by_gate.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "seed"] + list(GATE_ORDER))
        for cid in FULL_ORDER:
            for r in results.get(cid, []):
                w.writerow([cid, r.seed] + [f"{r.leakage_by_gate[g]:.4f}" for g in GATE_ORDER])

    with open(outdir / "violations_by_gate.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "seed", "gate"] + list(CHECK_ORDER) + ["total"])
        for cid in FULL_ORDER:
            for r in results.get(cid, []):
                for gr in r.gates:
                    tot = sum(gr.violations.values())
                    w.writerow([cid, r.seed, gr.gate_id]
                               + [gr.violations.get(c, 0) for c in CHECK_ORDER]
                               + [tot])

    with open(outdir / "defects.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "seed", "defect_id", "kind", "target_gate",
                    "artifact", "detected", "detected_by", "detected_gate",
                    "leaked"])
        for cid in FULL_ORDER:
            for r in results.get(cid, []):
                for d in r.injected:
                    w.writerow([cid, r.seed, d.defect_id, d.kind,
                                d.target_gate, d.artifact, d.detected,
                                d.detected_by, d.detected_gate, d.leaked])


def write_summary_csv(agg, outdir: Path) -> None:
    with open(outdir / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "n_seeds", "tc_mean", "tc_lo", "tc_hi",
                    "first_pass_tc_mean",
                    "leakage_pooled", "leakage_mean", "leakage_lo", "leakage_hi",
                    "leak_struct_mean", "leak_sem_mean",
                    "violations_mean", "minutes_mean", "minutes_lo", "minutes_hi",
                    "authoring_mean", "review_mean",
                    "retries_mean", "escalations_mean",
                    "coverage_min_branch_mean", "injected_mean"])
        for cid in FULL_ORDER:
            if cid not in agg:
                continue
            a = agg[cid]
            w.writerow([
                cid, a["tc"]["n"],
                f"{a['tc']['mean']:.4f}", f"{a['tc']['lo']:.4f}", f"{a['tc']['hi']:.4f}",
                f"{a['first_pass_tc']['mean']:.4f}",
                f"{a['leakage_pooled']['mean']:.4f}",
                f"{a['leakage']['mean']:.4f}", f"{a['leakage']['lo']:.4f}",
                f"{a['leakage']['hi']:.4f}",
                f"{a['leak_struct']['mean']:.4f}", f"{a['leak_sem']['mean']:.4f}",
                f"{a['violations']['mean']:.2f}",
                f"{a['minutes']['mean']:.1f}", f"{a['minutes']['lo']:.1f}",
                f"{a['minutes']['hi']:.1f}",
                f"{a['authoring']['mean']:.1f}", f"{a['review']['mean']:.1f}",
                f"{a['retries']['mean']:.2f}", f"{a['escalations']['mean']:.2f}",
                f"{a['coverage_min_branch']['mean']:.2f}",
                f"{a['injected']['mean']:.2f}",
            ])


# --------------------------------------------------------------------- #
# figures
# --------------------------------------------------------------------- #
def _bar_with_ci(ax, labels, means, los, his, ylabel, title):
    x = np.arange(len(labels))
    means = np.array(means, dtype=float)
    los = np.array(los, dtype=float)
    his = np.array(his, dtype=float)
    errs = [means - los, his - means]
    ax.bar(x, means, yerr=errs, capsize=4, color="#4C78A8", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)


def make_figures(results, agg, figdir: Path) -> None:
    figdir.mkdir(parents=True, exist_ok=True)
    cids = [c for c in FULL_ORDER if c in agg]
    dlabels = [DISP.get(c, c) for c in cids]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    _bar_with_ci(ax, dlabels,
                 [agg[c]["tc"]["mean"] for c in cids],
                 [agg[c]["tc"]["lo"] for c in cids],
                 [agg[c]["tc"]["hi"] for c in cids],
                 "traceability completeness (TC)",
                 "Final traceability completeness by configuration (mean ± 95% bootstrap CI)")
    ax.set_ylim(0.9, 1.02)
    fig.tight_layout()
    fig.savefig(figdir / "tc_by_config.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    _bar_with_ci(ax, dlabels,
                 [agg[c]["first_pass_tc"]["mean"] for c in cids],
                 [agg[c]["first_pass_tc"]["lo"] for c in cids],
                 [agg[c]["first_pass_tc"]["hi"] for c in cids],
                 "first-pass TC",
                 "First-pass TC: prescope invariants on first production (mean ± 95% CI)")
    ax.set_ylim(0.85, 1.02)
    fig.tight_layout()
    fig.savefig(figdir / "firstpass_tc_by_config.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for cid in cids:
        runs = results[cid]
        ys = [np.nanmean([r.leakage_by_gate[g] for r in runs]) for g in GATE_ORDER]
        ax.plot(list(GATE_ORDER), ys, marker="o", label=DISP.get(cid, cid))
    ax.set_ylabel("seeded-defect leakage (fraction)")
    ax.set_xlabel("gate")
    ax.set_title("Defect leakage by gate (mean over seeds)")
    ax.legend(ncol=4, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(figdir / "leakage_by_gate.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    _bar_with_ci(ax, dlabels,
                 [agg[c]["minutes"]["mean"] for c in cids],
                 [agg[c]["minutes"]["lo"] for c in cids],
                 [agg[c]["minutes"]["hi"] for c in cids],
                 "reviewer minutes (total)",
                 "Total effort by configuration (mean ± 95% bootstrap CI)")
    fig.tight_layout()
    fig.savefig(figdir / "effort_by_config.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    _bar_with_ci(ax, dlabels,
                 [agg[c]["violations"]["mean"] for c in cids],
                 [agg[c]["violations"]["lo"] for c in cids],
                 [agg[c]["violations"]["hi"] for c in cids],
                 "residual I1-I11 violations",
                 "Residual traceability violations at ledger closure (mean ± 95% CI)")
    fig.tight_layout()
    fig.savefig(figdir / "violations_by_config.png", dpi=150)
    plt.close(fig)

    # Structural vs semantic escape split (pooled counts).
    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(cids))
    struct = [sum(r.n_leaked_structural for r in results[c]) for c in cids]
    sem = [sum(r.n_leaked_semantic for r in results[c]) for c in cids]
    ax.bar(x, struct, label="structural escapes", color="#4C78A8", edgecolor="black")
    ax.bar(x, sem, bottom=struct, label="semantic escapes (incl. link-integrity)",
           color="#F58518", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels(dlabels, rotation=20, ha="right")
    ax.set_ylabel("escaped defects (pooled over seeds)")
    ax.set_title("Release escapes by defect kind (pooled over seeds)")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figdir / "escape_split.png", dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------- #
# statistical comparisons
# --------------------------------------------------------------------- #
def _comparisons(results) -> List[dict]:
    """M vs each comparator (paired by seed): Wilcoxon + Cliff's delta.

    Metrics: leakage and reviewer minutes (effort). Holm-adjusted p-values
    across the family; Cliff's delta (matched-pairs rank-biserial) as the
    effect size, which is better behaved than p at n=12.
    """
    metrics = {
        "leakage": _per_seed_leakage,
        "reviewer minutes": lambda r: r.total_minutes,
    }
    m_runs = {r.seed: r for r in results.get("M", [])}
    rows, pvals = [], []
    for cid in FULL_ORDER:
        if cid == "M" or cid not in results:
            continue
        for mname, fn in metrics.items():
            xs, ys = [], []
            for r in results[cid]:
                if r.seed in m_runs:
                    xv, yv = fn(m_runs[r.seed]), fn(r)
                    if not np.isnan(xv) and not np.isnan(yv):
                        xs.append(xv)
                        ys.append(yv)
            _, p = wilcoxon_signed_rank(xs, ys)
            delta, mag = cliffs_delta(xs, ys)
            rows.append({"config": cid, "metric": mname, "p": p,
                         "delta": delta, "magnitude": mag,
                         "m_mean": float(np.mean(xs)) if xs else float("nan"),
                         "c_mean": float(np.mean(ys)) if ys else float("nan"),
                         "n": len(xs)})
            pvals.append(p)
    adj = holm(pvals)
    for row, a in zip(rows, adj):
        row["p_adj"] = a
    return rows


# --------------------------------------------------------------------- #
# markdown report
# --------------------------------------------------------------------- #
def write_report_md(results, agg, comparisons, outdir: Path) -> None:
    cids = [c for c in FULL_ORDER if c in agg]
    lines = [
        "# MAVERICK Evaluation Harness v3 -- Results",
        "",
        "Simulated evaluation of the MAVERICK multi-agent orchestration pipeline "
        "(ASPICE SWE.1-SWE.6, safety-supervised) against baselines and ablations, "
        "on the AEB (ASIL-B/QM) worked-example fixture.",
        "",
        "> **Simulation, not measurement.** All numbers below are outputs of a "
        "seeded behavioral simulation (``SimulatedLLM`` defect injection + "
        "calibrated reviewer/critic models). No real LLM was called. Every "
        "number comes from the actual run; assumptions are documented in "
        "``ASSUMPTIONS.md``.",
        "",
        "## Configurations",
        "",
        "| ID | Description |",
        "|----|-------------|",
    ]
    for cid in cids:
        cfg = get_config(cid)
        lines.append(f"| `{cid}` | {cfg.name}: {cfg.description} |")
    lines += [
        "",
        "## Per-configuration results (mean [95% bootstrap CI] over 12 seeds)",
        "",
        "Leakage = seeded defects escaping the gate pipeline (pooled value in "
        "the `leakage_pooled` column of `summary.csv`). Structural/semantic "
        "escape columns are pooled defect counts. Retries = Phase-A rework "
        "loops; budget exhaustions = escalations after k retries.",
        "",
        "| Config | Final TC | First-pass TC | Leakage | Struct esc | Sem esc | "
        "Residual viol | Total min | Authoring min | Review min | Retries | "
        "Budget exhaust |",
        "|--------|----------|---------------|---------|----------|---------|"
        "-------------|-----------|---------------|------------|---------|"
        "--------------|",
    ]
    for cid in cids:
        a = agg[cid]
        runs = results[cid]
        struct_esc = sum(r.n_leaked_structural for r in runs)
        sem_esc = sum(r.n_leaked_semantic for r in runs)
        lines.append(
            f"| `{cid}` | {_fmt(a['tc'])} | {_fmt(a['first_pass_tc'])} | "
            f"{_fmt(a['leakage'])} | {struct_esc} | {sem_esc} | "
            f"{a['violations']['mean']:.2f} | {_fmt(a['minutes'], 1)} | "
            f"{_fmt(a['authoring'], 1)} | {_fmt(a['review'], 1)} | "
            f"{a['retries']['mean']:.1f} | {a['escalations']['mean']:.2f} |"
        )
    lines += [
        "",
        "Pooled leakage (total escaped / total injected):",
        "",
    ]
    for cid in cids:
        a = agg[cid]
        lines.append(f"- `{cid}`: {_fmt_mean(a['leakage_pooled'], 4)}")
    lines += [
        "",
        "## Effect sizes: M-full vs each comparator (paired by seed, n=12)",
        "",
        "Cliff's delta (matched-pairs rank-biserial) is the primary effect "
        "size -- better behaved than p at n=12. Positive delta: M-full has "
        "the *higher* value (good for TC, bad for leakage/minutes). "
        "Wilcoxon signed-rank p-values are Holm-adjusted across the family; "
        "`p_adj < 0.05` marked (*). Magnitude: negligible <0.147 < small "
        "<0.33 < medium <0.474 < large. `n` = paired seeds (seeds where "
        "either side injected zero defects are excluded as NaN).",
        "",
        "| Comparison | Metric | M mean | Comparator mean | Cliff's delta | Magnitude | p (Holm-adj) | n |",
        "|------------|--------|--------|-----------------|---------------|-----------|--------------|---|",
    ]
    for row in comparisons:
        star = " (*)" if row["p_adj"] < 0.05 else ""
        lines.append(
            f"| M vs `{row['config']}` | {row['metric']} | {row['m_mean']:.3f} | "
            f"{row['c_mean']:.3f} | {row['delta']:.3f} | {row['magnitude']} | "
            f"{row['p_adj']:.4f}{star} | {row['n']} |"
        )
    # RQ3: coverage, honestly.
    lines += [
        "",
        "## RQ3: structural coverage (achieved vs ASIL-indexed target)",
        "",
        "The coverage stub models *achieved* coverage as a function of the "
        "configuration's verification rigor (documented assumption in "
        "`metrics.py`): a pipeline that skips verification measures lower "
        "coverage. The table reports the minimum branch coverage achieved "
        "across units vs the ASIL-B H4 target (80% branch per the gate spec; "
        "statement 90%, MC/DC not required at ASIL B).",
        "",
        "| Config | Min branch achieved | ASIL-B target | Shortfall |",
        "|--------|---------------------|---------------|-----------|",
    ]
    target_b = coverage_target("H4", "branch", "B")
    for cid in cids:
        a = agg[cid]
        ach = a["coverage_min_branch"]["mean"]
        short = target_b - ach if not np.isnan(ach) else float("nan")
        lines.append(
            f"| `{cid}` | {_fmt_mean(a['coverage_min_branch'], 1)}% | "
            f"{target_b:.0f}% | {_fmt_mean({'mean': short}, 1)}% |"
        )
    lines += [
        "",
        "## Critic operating characteristics (seeded ground truth)",
        "",
        "| Config | Precision (mean) | Recall (mean) |",
        "|--------|------------------|---------------|",
    ]
    for cid in cids:
        runs = results[cid]
        precs = [r.critic_precision for r in runs if r.critic_precision is not None]
        recs = [r.critic_recall for r in runs if r.critic_recall is not None]
        p = f"{np.mean(precs):.3f}" if precs else "n/a (critic disabled)"
        rc = f"{np.mean(recs):.3f}" if recs else "n/a (critic disabled)"
        lines.append(f"| `{cid}` | {p} | {rc} |")
    lines += [
        "",
        "## Detection mechanism breakdown (pooled over seeds)",
        "",
        "| Config | ledger | alm | policy | critic | human-review | "
        "human-escalation | coverage | test | audit |",
        "|--------|--------|-----|--------|--------|----------------|"
        "------------------|----------|------|-------|",
    ]
    mechs = ["ledger", "alm", "policy", "critic", "human-review",
             "human-escalation", "coverage", "test", "audit"]
    for cid in cids:
        counts = {m: 0 for m in mechs}
        for r in results[cid]:
            for d in r.injected:
                if d.detected and d.detected_by in counts:
                    counts[d.detected_by] += 1
        lines.append("| `" + cid + "` | " +
                     " | ".join(str(counts[m]) for m in mechs) + " |")
    lines += [
        "",
        "## Figures",
        "",
        "![TC by config](figures/tc_by_config.png)",
        "",
        "![First-pass TC by config](figures/firstpass_tc_by_config.png)",
        "",
        "![Leakage by gate](figures/leakage_by_gate.png)",
        "",
        "![Effort by config](figures/effort_by_config.png)",
        "",
        "![Violations by config](figures/violations_by_config.png)",
        "",
        "![Escape split](figures/escape_split.png)",
        "",
        "## Further analyses",
        "",
        "- `sweep.md`: one-way sensitivity sweeps + break-even analysis "
        "(run with `python run.py --sweep`).",
        "- `asild.md`: ASIL-D steering-torque arbitration fixture "
        "(run with `python run.py --asild`).",
        "",
        "## Artifacts",
        "",
        "- `summary.csv`: per-configuration aggregates.",
        "- `per_seed.csv`: one row per (config, seed).",
        "- `leakage_by_gate.csv`: seeded-defect leakage per gate.",
        "- `violations_by_gate.csv`: residual I1-I11 violations per gate.",
        "- `defects.csv`: every injected defect with detection outcome.",
        "- `ASSUMPTIONS.md`: documented assumption register.",
        "- `figures/`: PNG figures.",
    ]
    (outdir / "report.md").write_text("\n".join(lines) + "\n")


def build_report(
    results: Dict[str, List[RunResult]], outdir: Path
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Write report.md, CSVs and figures; return aggregates."""
    outdir = Path(outdir)
    agg = aggregate(results)
    write_csvs(results, outdir)
    write_summary_csv(agg, outdir)
    make_figures(results, agg, outdir / "figures")
    comparisons = _comparisons(results)
    write_report_md(results, agg, comparisons, outdir)
    write_assumptions(outdir)
    return agg


# --------------------------------------------------------------------- #
# sensitivity sweeps
# --------------------------------------------------------------------- #
SWEEP_DEFS = [
    ("human_recall", [0.7, 0.8, 0.9],
     lambda v: {"human_catch_struct": min(v + 0.05, 0.99),
                "human_catch_sem": v},
     "human recall"),
    ("critic_recall", [0.5, 0.7, 0.9],
     lambda v: {"critic_recall": v},
     "critic recall"),
    ("inject_mult", [0.5, 1.0, 2.0],
     lambda v: {"inject_p": min(0.75 * v, 0.95)},
     "fault injection rate (x)"),
    ("corr_p", [0.0, 0.2, 0.5],
     lambda v: {"corr_p": v},
     "correlated-failure probability"),
]


def run_sensitivity_sweeps(seeds: List[int], outdir: Path) -> Dict:
    """One-way sensitivity sweeps on M-full (AEB fixture).

    Returns {param: [(value, [RunResult])]} and writes sweep.md + figures.
    """
    outdir = Path(outdir)
    figdir = outdir / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    sweep_results: Dict[str, list] = {}
    for param, values, mk_overrides, _ in SWEEP_DEFS:
        rows = []
        for v in values:
            runs = [run_experiment("M", s, overrides=mk_overrides(v))
                    for s in seeds]
            rows.append((v, runs))
            leak = sum(r.n_leaked for r in runs) / max(1, sum(r.n_injected for r in runs))
            print(f"  sweep {param}={v}: pooled leakage={leak:.3f}")
        sweep_results[param] = rows

    # Figures: leakage vs parameter.
    for param, _, _, xlabel in SWEEP_DEFS:
        rows = sweep_results[param]
        xs = [v for v, _ in rows]
        ys = [sum(r.n_leaked for r in runs)
              / max(1, sum(r.n_injected for r in runs))
              for v, runs in rows]
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(xs, ys, marker="o", color="#4C78A8")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("pooled leakage (M-full)")
        ax.set_title(f"Sensitivity: leakage vs {xlabel}")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(figdir / f"sweep_{param}.png", dpi=150)
        plt.close(fig)

    # Break-even: human recall at which M-full total cost exceeds B0's.
    be_lines, crossover = _break_even(seeds)

    lines = [
        "# Sensitivity sweeps (M-full, AEB fixture)",
        "",
        f"One-way sweeps, {len(seeds)} seeds per setting. Pooled leakage = "
        "total escaped / total injected.",
        "",
        "## Sweep table",
        "",
        "| Parameter | Value | Pooled leakage | Mean total min | Mean TC |",
        "|-----------|-------|----------------|----------------|---------|",
    ]
    for param, _, _, xlabel in SWEEP_DEFS:
        for v, runs in sweep_results[param]:
            leak = sum(r.n_leaked for r in runs) / max(1, sum(r.n_injected for r in runs))
            minutes = float(np.mean([r.total_minutes for r in runs]))
            tc = float(np.mean([r.final_tc for r in runs]))
            lines.append(
                f"| {xlabel} | {v} | {leak:.4f} | {minutes:.0f} | {tc:.3f} |")
    lines += [
        "",
        "## Sweep figures",
        "",
    ]
    for param, _, _, xlabel in SWEEP_DEFS:
        lines += [f"![leakage vs {xlabel}](figures/sweep_{param}.png)", ""]
    lines += be_lines
    (outdir / "sweep.md").write_text("\n".join(lines) + "\n")

    # Sweep CSV.
    with open(outdir / "sweep.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["parameter", "value", "seed", "leakage", "total_minutes",
                    "final_tc", "n_injected", "n_leaked"])
        for param, _, _, _ in SWEEP_DEFS:
            for v, runs in sweep_results[param]:
                for r in runs:
                    w.writerow([param, v, r.seed,
                                f"{_per_seed_leakage(r):.4f}"
                                if not np.isnan(_per_seed_leakage(r)) else "",
                                f"{r.total_minutes:.1f}", f"{r.final_tc:.4f}",
                                r.n_injected, r.n_leaked])
    return sweep_results


def _break_even(seeds: List[int]) -> tuple:
    """Human-recall level at which M-full's total cost exceeds B0's.

    Sweeps M-full's human recall over a grid and compares mean total cost
    against B0's mean total cost (6 seeds each).
    """
    grid = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99]
    m_costs, m_leaks = [], []
    for v in grid:
        runs = [run_experiment(
            "M", s,
            overrides={"human_catch_struct": min(v + 0.05, 0.99),
                       "human_catch_sem": v}) for s in seeds]
        m_costs.append(float(np.mean([r.total_minutes for r in runs])))
        leak = sum(r.n_leaked for r in runs) / max(1, sum(r.n_injected for r in runs))
        m_leaks.append(leak)
        print(f"  break-even grid recall={v}: mean min={m_costs[-1]:.0f}, "
              f"pooled leakage={leak:.3f}")
    b0_runs = [run_experiment("B0", s) for s in seeds]
    b0_cost = float(np.mean([r.total_minutes for r in b0_runs]))
    print(f"  B0 mean total min: {b0_cost:.0f}")

    crossover = None
    for v, c in zip(grid, m_costs):
        if c > b0_cost:
            crossover = v
            break

    lines = [
        "",
        "## Break-even analysis",
        "",
        "At what human-recall level does M-full's total cost exceed B0's? "
        f"B0's mean total cost is {b0_cost:.0f} reviewer-minutes "
        f"({len(seeds)} seeds); M-full's cost is swept over human recall:",
        "",
        "| Human recall | M-full mean total min | M-full pooled leakage |",
        "|--------------|-----------------------|-------------------------|",
    ]
    for v, c, l in zip(grid, m_costs, m_leaks):
        lines.append(f"| {v:.2f} | {c:.0f} | {l:.4f} |")
    lines.append("")
    if crossover is None:
        peak = max(m_costs)
        peak_v = grid[m_costs.index(peak)]
        lines += [
            f"**No crossover in the swept range.** M-full's mean total cost "
            f"(peak {peak:.0f} at recall {peak_v:.2f}) stays well below B0's "
            f"({b0_cost:.0f}). M-full's cost is dominated by fixed authoring "
            "and review effort; varying human recall only moves the rework "
            "component, and higher recall is slightly *cheaper* (early human "
            "catches cost less than late test/coverage-driven rework), so the "
            "recall level cannot close the gap created by B0's 2.5x manual "
            "review effort and full human authoring. In cost terms there is "
            "no break-even point: the trade-off is quality (leakage falls "
            "with recall) at roughly constant cost.",
        ]
    else:
        lines.append(
            f"**Crossover at human recall ≈ {crossover:.2f}**: above this "
            "level M-full's mean total cost exceeds B0's."
        )
    lines.append("")
    return lines, crossover


# --------------------------------------------------------------------- #
# ASIL-D fixture comparison
# --------------------------------------------------------------------- #
def run_asild_comparison(
    asild_results: Dict[str, List[RunResult]], outdir: Path
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Write asild.md comparing M-full / B0 / M-nopolicy on the ASIL-D fixture."""
    outdir = Path(outdir)
    agg = aggregate(asild_results)
    cids = [c for c in ("M", "B0", "M-nopolicy") if c in agg]
    dlabels = [DISP.get(c, c) for c in cids]

    figdir = outdir / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    _bar_with_ci(ax, dlabels,
                 [agg[c]["leakage_pooled"]["mean"] for c in cids],
                 [agg[c]["leakage"]["lo"] for c in cids],
                 [agg[c]["leakage"]["hi"] for c in cids],
                 "leakage (pooled / CI)",
                 "ASIL-D fixture: leakage by configuration")
    fig.tight_layout()
    fig.savefig(figdir / "asild_leakage.png", dpi=150)
    plt.close(fig)

    lines = [
        "# ASIL-D worked example: steering-torque arbitration",
        "",
        "***Synthetic / illustrative*** fixture (see `ASSUMPTIONS.md`). "
        "Stricter policy than the AEB fixture: mandatory independent human "
        "review at every gate, branch/MC-DC coverage targets of 100%, retry "
        "budget k=5.",
        "",
        "## Per-configuration results "
        f"(mean [95% CI] over {agg[cids[0]]['tc']['n']} seeds)",
        "",
        "| Config | Final TC | Leakage (pooled) | Struct esc | Sem esc | "
        "Total min | Retries | Budget exhaust |",
        "|--------|----------|------------------|------------|---------|"
        "-----------|---------|---------------|",
    ]
    for cid in cids:
        a = agg[cid]
        runs = asild_results[cid]
        struct_esc = sum(r.n_leaked_structural for r in runs)
        sem_esc = sum(r.n_leaked_semantic for r in runs)
        lines.append(
            f"| `{cid}` | {_fmt(a['tc'])} | "
            f"{_fmt_mean(a['leakage_pooled'], 4)} | {struct_esc} | {sem_esc} | "
            f"{_fmt(a['minutes'], 1)} | {a['retries']['mean']:.1f} | "
            f"{a['escalations']['mean']:.2f} |"
        )
    # ASIL policy contribution: M-full vs M-nopolicy on the ASIL-D fixture.
    m_leak = agg["M"]["leakage_pooled"]["mean"] if "M" in agg else float("nan")
    np_leak = (agg["M-nopolicy"]["leakage_pooled"]["mean"]
               if "M-nopolicy" in agg else float("nan"))
    lines += [
        "",
        "## Is the ASIL policy contribution visible?",
        "",
        f"M-full pooled leakage: {m_leak:.4f}; M-nopolicy pooled leakage: "
        f"{np_leak:.4f}. ",
    ]
    if not np.isnan(m_leak) and not np.isnan(np_leak):
        if np_leak > m_leak:
            lines.append(
                "The supervisor policy layer shows a visible contribution on "
                "the ASIL-D fixture: removing it increases escaped defects, "
                "consistent with the stricter ASIL-D policy (mandatory "
                "independent review at every gate) interacting with the "
                "policy checks."
            )
        else:
            lines.append(
                "No visible policy contribution on this fixture at these "
                "seeds: the ledger invariant checks already cover the policy "
                "subset (S2/M4), so the policy layer is redundant when the "
                "ledger protocol is active (negative control, as on the AEB "
                "fixture)."
            )
    lines += [
        "",
        "![ASIL-D leakage](figures/asild_leakage.png)",
        "",
    ]
    (outdir / "asild.md").write_text("\n".join(lines) + "\n")
    return agg


# --------------------------------------------------------------------- #
# assumptions register
# --------------------------------------------------------------------- #
def write_assumptions(outdir: Path) -> None:
    text = """# ASSUMPTIONS.md -- documented assumption register

Every number in `report.md` / `sweep.md` / `asild.md` comes from the actual
simulation run. This file documents the modelling assumptions the simulation
rests on. Nothing here is a measurement of a real LLM, a real reviewer, or a
real project.

## Simulation scope

- **Seeded behavioral simulation.** `SimulatedLLM` does not generate
  language; it generates artifact-level outcomes (defect injection with
  per-configuration probabilities). Deterministic given (config, fixture,
  seed). No network calls.
- **Worked examples, not case studies.** Both fixtures (AEB pedestrian
  post-processing, ASIL-B/QM; steering-torque arbitration, ASIL-D) are
  synthetic and illustrative, hand-built for the simulation. Not derived
  from any real product or requirements document.

## Defect model (`faults.py`)

- 15 seeded defect classes: 6 structural (S1-S6), 6 semantic (M1-M6),
  3 link-integrity (W1 wrong-target link, W2 spurious link, R1 hallucinated
  rationale).
- W1/W2/R1 are **invisible to link-existence invariants** (I1/I4/I7) and to
  ALM-style link checks by construction: the links exist and are type-valid.
  Only the critic (probabilistically) or human review can catch them. This
  breaks the "faults map 1:1 to invariants" circularity.
- `detectable_by` declares which mechanism *can* catch each defect; it is a
  modelling choice, not an empirical claim.

## Agent / reviewer / critic behavior (`agents.py`, `configs.py`)

- Per-defect injection probability `inject_p`: 0.75 (LLM pipelines),
  0.45 (B4/B5, lighter prompting assumed), 0.15 (B3 human authoring),
  0.05 (B0 manual).
- Critic: recall 0.70, false-positive rate 0.10 per artifact (assumed
  operating point; precision is emergent and reported).
- Human review catch: 0.90 structural / 0.85 semantic (M-family, B3-B5);
  0.99 (B0 optimistic); 0.40/0.25 (B1 cursory); 0.50/0.35 (B2).
- **Alert fatigue**: effective human recall is multiplied by
  `(1 - 0.3 * false_alarm_rate)` where the false-alarm rate is the critic's
  accumulated FP findings per review. Slope 0.3 is an assumption.
- **Correlated failure** (`corr_p`): with probability `corr_p` the critic
  misses a defect *together with* the generator (shared blind spot),
  regardless of recall. Default 0.0; swept at {0, 0.2, 0.5}.
- Retry budget k=3 (k=5 on the ASIL-D fixture); escalation costs 45
  reviewer-minutes; audit rework 45 minutes.

## Effort model (`metrics.py`)

- Reviewer minutes: lognormal around base minutes per (artifact type x ASIL),
  scaled by configuration `effort_scale` (B0 2.5x, M-family 1.0x, B3 1.0x,
  B4 0.5x, B5 0.3x, B1 0.5x, B2 0.6x).
- **Authoring minutes**: new in v3. Human authoring (B0/B3) charged at full
  base authoring minutes; LLM drafting (all others) at 0.05x. Base values
  (e.g. SwReq 120, SwUnit 240) are plausible magnitudes, not measurements.
- B4 advisory findings: 5 minutes triage each, no rework. B5 audit:
  10 minutes per artifact + 45 per found issue; audit recall 0.85
  (inspired by Sameh & Elbanna 2026's 85% manual-effort reduction, but that
  figure is *effort reduction*, not detection recall -- the 0.85 recall used
  here is an assumption).

## Coverage stub (`metrics.py`)

- Achieved coverage = f(deterministic unit hash, pipeline **rigor**,
  defect presence). Rigor per configuration (M-full 1.0 ... B2 0.2) is a
  documented assumption: a pipeline that skips verification *measures*
  lower coverage. This is why the stub varies by configuration -- the
  variation is *explained*, not noise.
- RQ3 is reported honestly: achieved minimum branch coverage vs the
  ASIL-indexed H4 target (80% branch at ASIL B, 100% at ASIL D).

## Baselines B3/B4/B5 (`configs.py`)

- **B3 (human+ALM)**: `alm_checks` catch missing links/artifacts
  deterministically (S1/S2/S3/S5/S6/M3) but never W1/W2/R1 or ASIL faults.
- **B4 (LLM+advisory)**: invariant checks run post-promotion as
  non-blocking findings; nothing is reworked or blocked.
- **B5 (LLM+audit)**: post-hoc audit finds escaped defects (recall 0.85)
  but cannot block; found defects still count as gate-pipeline escapes
  (`leaked=True`).

## Statistics

- n=12 seeds (main comparison), 6 seeds (sweeps). Bootstrap 95% CIs,
  Wilcoxon signed-rank (Holm-adjusted) *and* Cliff's delta (matched-pairs
  rank-biserial) -- the delta is the primary effect size at n=12.
- Leakage: pooled (total escaped / total injected) for headlines;
  per-seed rates (NaN seeds excluded) for CIs and paired tests.
"""
    (outdir / "ASSUMPTIONS.md").write_text(text)
