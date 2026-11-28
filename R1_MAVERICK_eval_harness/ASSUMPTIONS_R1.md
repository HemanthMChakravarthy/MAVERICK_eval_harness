# Assumption register — harness v2.1.1

All behavioural values are modelling assumptions, not empirical measurements. This release changes the rework semantics and random-number design relative to R1; numerical outputs are not directly comparable with the prior R1 release.

| Parameter | Default | Treatment |
|---|---:|---|
| `p_llm` | 0.75 | Per-fault-class injection probability for LLM configurations. |
| `p_human` | 0.15 | Per-fault-class injection probability for human authoring. |
| `p_manual` | 0.05 | Per-fault-class injection probability for manual baseline. |
| `critic_recall` | 0.70 | Assumed semantic/link-integrity critic recall. |
| `critic_far` | 0.10 | Assumed critic false-alarm rate per artifact. |
| `h_st`, `h_sm`, `h_li` | 0.90 / 0.85 / 0.80 | Assumed human review recall by fault category. |
| `test_scale` | 1.0 | Multiplier on catalogued test detection probabilities. |
| `p_fix_llm` / `p_fix_human` | 0.85 / 0.95 | Per-attempt rework resolution probabilities. |
| `p_fix_escalation` | 0.95 | Assumed probability that human escalation resolves a defect after bounded rework fails. A modelling assumption, not a measurement; varied 0.80–0.99 in the GUA. |
| `k_retry` / `k_retry_asil_d` | 3 / 5 | Maximum rework attempts before escalation. |
| `corr` | 0.0 | Assumed probability of shared critic–generator blind spot. |
| `audit_recall` | 0.85 | Assumed post-hoc audit recall for B5. |
| Effort parameters | See `params.py` | Assumed authoring, review, rework, disposition, and escalation minutes. |
| Coverage | Deterministic stub | Assumption-determined; not empirical test coverage evidence. |

## Randomness and pairing

Injection, review-policy, coverage, detection, repair, escalation, and audit events use separate deterministic streams. Detection draws are keyed to the experiment seed, fault instance, and a stable layer identifier (common random numbers across configurations). A different number of repair attempts therefore cannot shift detection draws for later faults. This improves causal isolation and reproducibility; it does not validate the chosen probability distributions.

## Rework state semantics

A defect is removed from the residual population only when a repair attempt succeeds or the separate human-escalation resolution event succeeds. If both paths fail, the defect remains in the pipeline and may be detected by later controls. If the unresolved detection came from a deterministic blocking check (ledger invariant or ALM existence check), the release gate re-evaluates that check and withholds the release (`held`); otherwise an unresolved defect is counted as an escape. `unresolved_detected` counts failed resolution events, not necessarily unique defects.

## Ledger scope and threat model

The ledger hash covers artifact identity and classification fields, payload, links, version, and previous hash. The in-memory revision history is checked locally. This detects accidental or uncoordinated changes to retained records, but it is not a cryptographically authenticated audit service: there are no signatures, external anchors, access controls, or durable append-only storage.

I11 requires an explicit `verdict: pass`; missing and non-pass verdicts are violations. Result links must target supported test artifact types.

## Evidence boundary

Deterministic graph-invariant tests establish only that the implemented structural rules fire on the tested mutations. Semantic fault detection, human review, LLM critic behaviour, repair effectiveness, escalation effectiveness, and effort remain probabilistic assumptions. B6–B8 remain mechanism emulations, not executions of the original frameworks.

## ASIL-D second review and effort
The ASIL-D second review is an assumed additional detection layer (recall 0.50); the
simulation does not model reviewer identity, expertise, or an access-control workflow.
Effort results are dominated by the assumed LLM drafting factor (0.05 of human
authoring minutes) and are estimates, not measured productivity.

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
