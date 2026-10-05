"""Safety gates H1-H6.

Gate configurations are *data* (per-ASIL verification methods and coverage
targets), following the paper's Tables III/IV. The method tables below are an
illustrative reconstruction of ASPICE/ISO 26262-6 practice -- projects should
substitute their own qualified method tables; the harness only needs the
*structure* (method per ASIL, coverage target per ASIL).

The promotion decision rule from the paper::

    promote(E) = Inv(E) AND Cov(E,a) AND (critic findings empty or dispositioned)
                 AND Approve(E,a)

with the additional protocol rules: the approver must differ from the
author/prompter, and a bounded retry budget (k=3 by default; k=5 on the
ASIL-D worked-example fixture) applies before escalation to a human.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: Bounded retry budget before escalation to a human (default; the ASIL-D
#: worked-example fixture raises this to k=5).
RETRY_BUDGET_K = 3


@dataclass(frozen=True)
class GateSpec:
    gate_id: str  # H1..H6
    name: str
    aspice: str  # SWE.x process
    artifact_types: Tuple[str, ...]  # envelope types produced/verified at this gate
    methods: Dict[str, str]  # ASIL -> verification method
    coverage: Dict[str, Dict[str, float]]  # metric -> {ASIL: target %} (empty if n/a)
    confirmations: Tuple[str, ...] = ()  # confirmation measures at this gate


GATES: Dict[str, GateSpec] = {
    "H1": GateSpec(
        gate_id="H1",
        name="Software requirements verification",
        aspice="SWE.1",
        artifact_types=("SwReq",),
        methods={
            "QM": "walk-through",
            "A": "walk-through",
            "B": "walk-through + checklist",
            "C": "inspection",
            "D": "semi-formal inspection",
        },
        coverage={},
        confirmations=("requirements review against system requirements",),
    ),
    "H2": GateSpec(
        gate_id="H2",
        name="Software architecture verification",
        aspice="SWE.2",
        artifact_types=("SwArch",),
        methods={
            "QM": "walk-through",
            "A": "walk-through",
            "B": "inspection",
            "C": "semi-formal inspection + interface consistency analysis",
            "D": "semi-formal inspection + interface consistency analysis",
        },
        coverage={},
        confirmations=("allocation review (every SwReq allocated)",),
    ),
    "H3": GateSpec(
        gate_id="H3",
        name="Detailed design & unit construction (static verification)",
        aspice="SWE.3",
        artifact_types=("SwDesign", "SwUnit"),
        methods={
            "QM": "coding-guideline check",
            "A": "coding-guideline check",
            "B": "static analysis",
            "C": "static analysis + enforced guideline set",
            "D": "static analysis + enforced guideline set",
        },
        coverage={},
        confirmations=("traceability SwUnit -> SwReq",),
    ),
    "H4": GateSpec(
        gate_id="H4",
        name="Software unit verification",
        aspice="SWE.4",
        artifact_types=("UnitTest", "Result"),
        methods={
            "QM": "unit test",
            "A": "unit test",
            "B": "unit test + structural coverage",
            "C": "unit test + structural coverage",
            "D": "unit test + structural coverage",
        },
        coverage={
            "statement": {"QM": 80.0, "A": 80.0, "B": 90.0, "C": 100.0, "D": 100.0},
            "branch": {"QM": 0.0, "A": 0.0, "B": 80.0, "C": 90.0, "D": 100.0},
            "mcdc": {"QM": 0.0, "A": 0.0, "B": 0.0, "C": 80.0, "D": 100.0},
        },
        confirmations=("coverage closure per unit",),
    ),
    "H5": GateSpec(
        gate_id="H5",
        name="Component & software integration verification",
        aspice="SWE.5",
        artifact_types=("CompTest", "IntTest", "Result"),
        methods={
            "QM": "integration test",
            "A": "integration test",
            "B": "integration test + interface coverage",
            "C": "integration test + interface coverage",
            "D": "integration test + interface coverage",
        },
        coverage={
            "function": {"QM": 80.0, "A": 80.0, "B": 90.0, "C": 100.0, "D": 100.0},
            "call": {"QM": 80.0, "A": 80.0, "B": 90.0, "C": 100.0, "D": 100.0},
        },
        confirmations=("interface consistency re-verification after change",),
    ),
    "H6": GateSpec(
        gate_id="H6",
        name="Software qualification test",
        aspice="SWE.6",
        artifact_types=("QualTest",),
        methods={
            "QM": "requirements-based test",
            "A": "requirements-based test",
            "B": "requirements-based test",
            "C": "requirements-based test + fault injection",
            "D": "requirements-based test + fault injection + back-to-back test",
        },
        coverage={},
        confirmations=(
            "ledger closure: TC == 1",
            "all artifacts baselined",
            "no suspect artifacts",
            "resource usage test (ASIL B and above)",
        ),
    ),
}

GATE_ORDER = ("H1", "H2", "H3", "H4", "H5", "H6")


def coverage_target(gate_id: str, metric: str, asil: str) -> float:
    """Coverage target in percent; 0.0 means 'not required'."""
    return GATES[gate_id].coverage.get(metric, {}).get(asil, 0.0)


#: Rigor calibration for the ASIL-indexed verification methods (Tables III/IV).
#: method -> (review-effort multiplier, human catch-probability bonus).
#: Modelling assumption: more rigorous methods (inspection, semi-formal,
#: structural coverage, fault injection) cost more reviewer time and catch a
#: larger fraction of residual defects. Documented here so it can be
#: challenged or recalibrated; it is not a measured quantity.
METHOD_RIGOR = {
    "walk-through": (1.00, 0.00),
    "walk-through + checklist": (1.10, 0.02),
    "inspection": (1.25, 0.05),
    "semi-formal inspection": (1.40, 0.08),
    "semi-formal inspection + interface consistency analysis": (1.50, 0.10),
    "coding-guideline check": (1.00, 0.00),
    "static analysis": (1.20, 0.05),
    "static analysis + enforced guideline set": (1.35, 0.08),
    "unit test": (1.00, 0.00),
    "unit test + structural coverage": (1.20, 0.05),
    "integration test": (1.00, 0.00),
    "integration test + interface coverage": (1.20, 0.05),
    "requirements-based test": (1.10, 0.02),
    "requirements-based test + fault injection": (1.30, 0.06),
    "requirements-based test + fault injection + back-to-back test": (1.45, 0.09),
}


def method_for(gate_id: str, asil: str) -> str:
    """Verification method prescribed for (gate, ASIL) by Tables III/IV."""
    return GATES[gate_id].methods.get(asil, "walk-through")


def method_rigor(method: str) -> tuple:
    """(effort multiplier, catch bonus) for a verification method."""
    return METHOD_RIGOR.get(method, (1.0, 0.0))


#: Invariant checks applicable *pre-promotion* at each gate. Downstream
#: completeness (I2b implementation, I5 verification, I8 component tests)
#: cannot hold until later gates have produced their artifacts, so those are
#: ledger-closure checks (H6), not promotion blockers at early gates.
#: I9/I10/I11 are result-level checks: a test is promoted only once its
#: result is recorded (I9), linked (I10) and passing (I11).
GATE_PRECHECKS = {
    "H1": ("I1", "I6"),  # SwReq: upward completeness + ASIL inheritance
    "H2": ("I1", "I3", "I6"),  # + allocation exists after the allocation step
    "H3": ("I4", "I6"),  # SwDesign/SwUnit: no orphans + ASIL inheritance
    "H4": ("I6", "I7", "I9", "I10", "I11"),  # UnitTest+Result: design link, result recorded/linked/passing
    "H5": ("I6", "I7", "I9", "I10", "I11"),  # CompTest/IntTest+Result
    "H6": ("I6", "I7", "I9", "I10", "I11"),  # QualTest+Result
}


# --------------------------------------------------------------------- #
# Promotion decision rule
# --------------------------------------------------------------------- #
@dataclass
class PromotionInput:
    envelope_key: str
    inv_ok: bool  # Inv(E): invariants hold on the envelope
    cov_ok: bool  # Cov(E,a): coverage targets met for the ASIL
    open_critic_findings: int  # undispositioned critic findings
    author: str
    approver: str
    attempts: int  # regeneration attempts so far
    retry_budget: int = RETRY_BUDGET_K


@dataclass
class PromotionDecision:
    promotable: bool
    escalate: bool
    reasons: List[str] = field(default_factory=list)


def evaluate_promotion(pi: PromotionInput) -> PromotionDecision:
    """Evaluate promote(E): Inv(E) and Cov(E,a) and findings-dispositioned
    and Approve(E,a).

    Approve(E,a) requires the approver to differ from the author/prompter.
    When the retry budget is exhausted the decision escalates to a human
    instead of promoting.
    """
    reasons: List[str] = []
    if not pi.inv_ok:
        reasons.append("invariant violations open on the envelope")
    if not pi.cov_ok:
        reasons.append("structural coverage target not met for the ASIL")
    if pi.open_critic_findings:
        reasons.append(f"{pi.open_critic_findings} undispositioned critic finding(s)")
    if pi.approver == pi.author:
        reasons.append("approver must differ from author/prompter (different-person rule)")
    escalate = pi.attempts > pi.retry_budget
    if escalate:
        reasons.append(
            f"retry budget k={pi.retry_budget} exhausted -> escalate to human"
        )
    return PromotionDecision(promotable=not reasons, escalate=escalate, reasons=reasons)
