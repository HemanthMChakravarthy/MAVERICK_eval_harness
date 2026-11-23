# Assumption register — harness v2.0 (revision R1)

All values are modelling assumptions, not measurements. "GUA range" is the
interval sampled in the global uncertainty analysis.

| Parameter | Value | GUA range | Rationale / role |
|---|---|---|---|
| p_llm (per-class injection, LLM configs) | 0.75 | 0.30–0.90 | Stress setting that exposes mechanism differences |
| p_human (B3 human authoring) | 0.15 | 0.05–0.30 | Lower defect density of human authoring |
| p_manual (B0) | 0.05 | – | Rare authoring slips |
| B1 correlation | 30 % degraded runs at p = 0.95 | – | No agent isolation; mean p preserved |
| B2 amplification | +0.15 per active upstream defect | – | Shared-context propagation (negative control) |
| B7 dehallucination | −20 % relative injection | – | Instructor/assistant clarification in chat chains |
| critic_recall | 0.70 | 0.40–0.90 | LLM critic, different model family |
| critic_far | 0.10 per artifact | 0.02–0.25 | False-alarm rate; drives alert fatigue and disposition effort |
| corr | 0 | 0–0.5 | Probability of a shared critic–generator blind spot |
| h_st / h_sm / h_li | 0.90 / 0.85 / 0.80 | 0.75–0.98 / 0.60–0.95 / 0.50–0.90 | Different-person review recall by fault category |
| B0 review recall | 0.97 / 0.95 / 0.93 | – | Near-perfect review at 2.5× effort |
| fatigue_slope | 0.30 | 0–0.6 | Human recall × (1 − slope × FAR) |
| self_review_factor | 0.60 | – | Recall multiplier when approver authored/prompted the artifact |
| p_self_approval | 0.20 | 0–0.4 | Share of self-approvals when independence is not enforced (M−policy) |
| release review (B1, B2, B6, B7) | 0.45 / 0.40 / 0.30 | release_st 0.25–0.70 | Single end-of-pipeline human sign-off |
| LLM reviewer agent (B6, B7) | recall 0.40, corr 0.5 | 0.2–0.7 | Same-family code-review role (stage ≥ SWE.3 only) |
| test detection | catalog value × test_scale | test_scale 0.5–1.5 | Only behavioural faults (inverted inequality, unit conversion 0.5; untestable req 0.2) |
| exec-feedback / same-agent test factor | 0.8 / 0.3 | – | Tests derived in the producing context are less independent |
| p_fix_llm / p_fix_human | 0.85 / 0.95 | 0.60–0.95 / – | Probability one rework iteration removes the defect |
| retry budget k | 3 (ASIL B), 5 (ASIL D) | – | Escalation to a human author when exhausted |
| ASIL-D second independent review (policy) | recall 0.50, +100 % review effort | – | ASIL-indexed rigor enforced by the policy engine |
| audit_recall (B5) | 0.85 | 0.60–0.95; sweep 0.50–0.99 | Post-hoc audit; cannot block; affects field escapes only |
| Effort model | see `params.py` | – | Authoring/review minutes per artifact type; LLM drafting 0.05× |
| Coverage | deterministic stub | – | Coverage is **assumption-determined**; not used as evidence |

Deterministic (not assumed): invariant verdicts I1–I11, hash-chain
verification, suspect propagation, gate-closure rule TC = 1 at H6, retry
accounting. These are verified by `tests/test_mechanisms.py`.
