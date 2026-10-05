"""Pipeline configurations: baselines, MAVERICK, and ablations.

Each configuration is an explicit, documented *behavioral model* -- a set of
mechanisms (ledger invariant checks, supervisor policy, LLM critic,
different-person human review, coverage enforcement) plus calibrated human /
critic performance parameters. The parameters below are modelling
*assumptions* chosen to be plausible and to make mechanism differences
visible; they are not measurements of real LLMs or real reviewers. Every
assumption is stated in the ``notes`` so a reader can challenge or
recalibrate it.

Configurations
--------------
B0          Manual baseline: humans author everything. Rare slips
            (inject_p=0.05), near-perfect review (catch 0.99), but high effort
            (effort_scale=2.5). Optimistic about human thoroughness; the point
            of comparison is *effort*, not quality.
B1          Single LLM agent does every step. Correlated cross-step defects
            (correlation_bonus): if it errs once it likely errs downstream.
            No ledger protocol, no supervisor, cursory self-review possible,
            no coverage enforcement, low review effort.
B2          Unsupervised multi-agent with a shared message pool: defect
            *amplification* across steps (hallucination propagation:
            active upstream defects raise downstream injection probability).
            No invariant checks, no supervisor, cursory review.
M           Full MAVERICK: ledger invariant checks pre-promotion, supervisor
            deterministic policy, LLM critic (recall 0.7), enforced
            different-person human review (semantic catch 0.85), structural
            coverage enforcement, retry budget k=3 then escalation.
B3          Human + ALM: humans author; automated ALM-style link-existence
            checks catch missing links/artifacts only (never wrong-target,
            spurious or rationale faults). No critic, no coverage enforcement.
B4          LLM pipeline with automated invariant checks as *non-blocking*
            post-checks (advisory findings; no critic, no ASIL policy
            enforcement). Models "we run the checks but nothing blocks".
B5          LLM pipeline + post-hoc audit pass (Sameh & Elbanna style): the
            audit finds issues with high recall but cannot block the release;
            every found issue costs rework. Leakage counts defects that
            escaped the gate pipeline even if the audit later finds them.
M-noledger  M without ledger invariant checks / suspect propagation /
            baselined-only consumption (supervisor policy + critic remain).
M-nocritic  M without the LLM critic (policy + human review remain).
M-nopolicy  M without the supervisor deterministic policy checks
            (ledger + critic remain).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .gates import RETRY_BUDGET_K


@dataclass
class PipelineConfig:
    config_id: str
    name: str
    description: str
    notes: str  # honest statement of the behavioural assumption
    # mechanisms
    ledger_checks: bool  # invariant checks pre-promotion + suspect propagation
    supervisor_policy: bool  # deterministic policy checks
    critic_enabled: bool
    different_person_enforced: bool
    coverage_enforced: bool
    # agent fallibility model
    inject_p: float  # per-defect injection probability at the producing step
    correlation_bonus: float = 0.0  # B1: cross-step correlation
    amplification_bonus: float = 0.0  # B2: shared-pool amplification per active defect
    # human / critic performance model
    critic_recall: float = 0.0
    critic_fp_rate: float = 0.0
    human_catch_struct: float = 0.0  # P(human catches a structural defect in review)
    human_catch_sem: float = 0.0  # P(human catches a semantic defect in review)
    effort_scale: float = 1.0  # multiplier on reviewer minutes
    authoring_scale: float = 1.0  # multiplier on authoring minutes (1.0 = human)
    retry_budget: int = RETRY_BUDGET_K
    # extended mechanisms (mock-review overhaul)
    alm_checks: bool = False  # B3: ALM-style link-existence checks only
    advisory_checks: bool = False  # B4: invariant checks as non-blocking post-checks
    audit_pass: bool = False  # B5: post-hoc audit (finds, cannot block)
    audit_recall: float = 0.85  # P(audit finds an escaped defect)
    audit_minutes_per_artifact: float = 10.0  # manual audit effort per artifact
    audit_rework_minutes: float = 45.0  # rework per audit-found issue
    corr_p: float = 0.0  # P(critic fails in a correlated way with the generator)
    fatigue_factor: float = 0.3  # alert-fatigue slope (recall *= 1 - slope*FAR)


def _m_base(**over) -> dict:
    base = dict(
        ledger_checks=True,
        supervisor_policy=True,
        critic_enabled=True,
        different_person_enforced=True,
        coverage_enforced=True,
        inject_p=0.75,
        critic_recall=0.70,
        critic_fp_rate=0.10,
        human_catch_struct=0.90,
        human_catch_sem=0.85,
        effort_scale=1.0,
        authoring_scale=0.05,  # LLM drafting is cheap vs human authoring
    )
    base.update(over)
    return base


CONFIGS: Dict[str, PipelineConfig] = {
    "B0": PipelineConfig(
        config_id="B0",
        name="Manual baseline",
        description="Humans author and review every artifact (no LLM).",
        notes=(
            "Optimistic manual baseline: rare authoring slips (inject_p=0.05), "
            "near-perfect review (catch 0.99), full manual traceability "
            "(ledger_checks=True models the manual trace matrix), but 2.5x "
            "review effort. Compares on effort, not quality."
        ),
        ledger_checks=True, supervisor_policy=True, critic_enabled=False,
        different_person_enforced=True, coverage_enforced=True,
        inject_p=0.05, critic_recall=0.0, critic_fp_rate=0.0,
        human_catch_struct=0.99, human_catch_sem=0.99, effort_scale=2.5,
    ),
    "B1": PipelineConfig(
        config_id="B1",
        name="Single LLM agent",
        description="One LLM agent performs all V-model steps; cursory review.",
        notes=(
            "Same per-step fallibility as M (inject_p=0.75) but failures "
            "correlate across steps (+0.20 once an error occurred: no agent "
            "isolation). No ledger protocol, no supervisor, approver may be "
            "the author (self-review), coverage not enforced, low effort."
        ),
        ledger_checks=False, supervisor_policy=False, critic_enabled=False,
        different_person_enforced=False, coverage_enforced=False,
        inject_p=0.75, correlation_bonus=0.20,
        human_catch_struct=0.40, human_catch_sem=0.25, effort_scale=0.5,
        authoring_scale=0.05,
    ),
    "B2": PipelineConfig(
        config_id="B2",
        name="Unsupervised multi-agent (shared pool)",
        description="Role agents share one message pool; no ledger, no supervisor.",
        notes=(
            "Defect amplification: each active upstream defect adds +0.15 to "
            "downstream injection probability (hallucination propagation via "
            "the shared pool, capped at 3 defects). No invariant checks, no "
            "supervisor, cursory human review."
        ),
        ledger_checks=False, supervisor_policy=False, critic_enabled=False,
        different_person_enforced=True, coverage_enforced=False,
        inject_p=0.75, amplification_bonus=0.15,
        human_catch_struct=0.50, human_catch_sem=0.35, effort_scale=0.6,
        authoring_scale=0.05,
    ),
    "B3": PipelineConfig(
        config_id="B3",
        name="Human + ALM link checks",
        description="Humans author; automated ALM-style link-existence checks.",
        notes=(
            "Human authoring (authoring_scale=1.0, inject_p=0.15) plus "
            "automated link-existence checks (alm_checks=True) that catch "
            "missing links/artifacts deterministically (S1/S2/S3/S5/S6/M3) "
            "but never wrong-target (W1), spurious (W2) or rationale (R1) "
            "faults, and no ASIL-inheritance checking (S4/M4 need the "
            "supervisor policy / human review). Review effort is human-rate "
            "but lower than B0 (effort_scale=1.0 vs 2.5) because the ALM "
            "checks absorb the traceability-matrix portion of review."
        ),
        ledger_checks=False, supervisor_policy=True, critic_enabled=False,
        different_person_enforced=True, coverage_enforced=False,
        inject_p=0.15, alm_checks=True,
        human_catch_struct=0.90, human_catch_sem=0.85, effort_scale=1.0,
        authoring_scale=1.0,
    ),
    "B4": PipelineConfig(
        config_id="B4",
        name="LLM + advisory invariant checks",
        description="LLM pipeline; invariant checks run as non-blocking post-checks.",
        notes=(
            "Models 'we run the checks but nothing blocks': every artifact is "
            "produced by the LLM pipeline (inject_p=0.45), invariant checks "
            "run post-promotion and record advisory findings (charged 5 "
            "reviewer-minutes each) but trigger no rework. Human review "
            "catches 90%/85% at reduced effort (effort_scale=0.5)."
        ),
        ledger_checks=False, supervisor_policy=True, critic_enabled=False,
        different_person_enforced=True, coverage_enforced=False,
        inject_p=0.45, advisory_checks=True,
        human_catch_struct=0.90, human_catch_sem=0.85, effort_scale=0.5,
        authoring_scale=0.05,
    ),
    "B5": PipelineConfig(
        config_id="B5",
        name="LLM + post-hoc audit",
        description="LLM pipeline plus a Sameh & Elbanna-style post-hoc audit.",
        notes=(
            "LLM pipeline (inject_p=0.45) with light human review; after "
            "release-equivalent (H6) a manual audit pass finds escaped "
            "defects with recall 0.85 (assumption inspired by Sameh & Elbanna "
            "2026) at 10 reviewer-minutes per artifact, and each found issue "
            "costs 45 minutes of rework. The audit cannot block: defects it "
            "finds still count as gate-pipeline escapes (leaked=True)."
        ),
        ledger_checks=False, supervisor_policy=False, critic_enabled=False,
        different_person_enforced=True, coverage_enforced=False,
        inject_p=0.45, audit_pass=True,
        human_catch_struct=0.90, human_catch_sem=0.85, effort_scale=0.3,
        authoring_scale=0.05,
    ),
    "M": PipelineConfig(
        config_id="M",
        name="Full MAVERICK",
        description="Ledger + supervisor policy + critic + enforced human gates.",
        notes=(
            "Full pipeline: invariant checks pre-promotion, deterministic "
            "supervisor policy, LLM critic at recall 0.70 / fp 0.10, "
            "different-person review catching 85% of residual semantic "
            "defects, coverage enforced, retry k=3 then human escalation."
        ),
        **_m_base(),
    ),
    "M-noledger": PipelineConfig(
        config_id="M-noledger",
        name="MAVERICK without ledger protocol",
        description="M minus invariant checks, suspect propagation, lifecycle enforcement.",
        notes=(
            "Ablation: supervisor policy + critic + human review remain, but "
            "structural defects are no longer caught deterministically "
            "pre-promotion; only the policy subset (S2, M4) and humans catch "
            "them. Expect TC < 1 and structural leakage."
        ),
        **_m_base(ledger_checks=False),
    ),
    "M-nocritic": PipelineConfig(
        config_id="M-nocritic",
        name="MAVERICK without LLM critic",
        description="M minus the critic; policy + human review remain.",
        notes=(
            "Ablation: semantic defects (M1, M2, M5, M6) must be caught by "
            "humans (85%) or coverage (M2). Expect higher semantic leakage "
            "than M at similar effort."
        ),
        **_m_base(critic_enabled=False, critic_recall=0.0, critic_fp_rate=0.0),
    ),
    "M-nopolicy": PipelineConfig(
        config_id="M-nopolicy",
        name="MAVERICK without supervisor policy",
        description="M minus deterministic policy checks; ledger + critic remain.",
        notes=(
            "Ablation: ledger invariant checks already catch the policy "
            "subset (S2, M4) deterministically, so the expected effect is "
            "small -- a negative control showing the policy layer is "
            "redundant when the ledger protocol is active."
        ),
        **_m_base(supervisor_policy=False),
    ),
}

FULL_ORDER = ["B0", "B1", "B2", "B3", "B4", "B5",
              "M", "M-noledger", "M-nocritic", "M-nopolicy"]


def get_config(config_id: str) -> PipelineConfig:
    return CONFIGS[config_id]
