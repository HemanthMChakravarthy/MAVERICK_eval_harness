"""Agent roles and LLM backends for the MAVERICK evaluation harness.

Agent roles (paper Sec. III), each mapped to an ASPICE process and gate:

    RA    Requirements Agent            SWE.1  H1
    AA    Architecture Agent            SWE.2  H2
    DCA   Detailed design/Construction  SWE.3  H3
    CA    Coverage/Verification Agent   SWE.4  H4
    TSA-I Integration Test Agent        SWE.5  H5
    TSA-Q Qualification Test Agent      SWE.6  H6
    SS    Safety Supervisor (deterministic policy + LLM critic), all gates

Backends implement the ``Backend`` protocol. The backend is ``SimulatedLLM``:
a seeded RNG that starts from the case-study's correct payload template and
injects catalog defects with per-configuration probabilities. It performs
*no* network I/O and calls *no* real model -- the harness is a deterministic
simulation end to end. (A real-LLM backend can be plugged in later behind the
``Backend`` protocol; see README.md.)
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Set

from . import faults
from .ledger import Envelope, Ledger, Link

AGENT_ROLES = {
    "RA": ("Requirements Agent", "SWE.1", "H1"),
    "AA": ("Architecture Agent", "SWE.2", "H2"),
    "DCA": ("Detailed Design & Construction Agent", "SWE.3", "H3"),
    "CA": ("Coverage / Unit Verification Agent", "SWE.4", "H4"),
    "TSA-I": ("Integration Test Specification Agent", "SWE.5", "H5"),
    "TSA-Q": ("Qualification Test Specification Agent", "SWE.6", "H6"),
}


@dataclass
class ProductionRequest:
    """A request for one artifact version."""

    gate_id: str
    spec_kind: str  # "swreq" | "arch" | "unit" | "unittest" | "inttest" | "qualtest" | "result"
    spec_id: str
    template: dict  # correct payload to start from
    links: List[Link]
    asil: str
    candidates: List[str]  # defect ids that may be injected here
    excluded: Set[str] = field(default_factory=set)  # defects ruled out (e.g. after a finding)
    mutation_ctx: Dict = field(default_factory=dict)  # e.g. {"alt_targets": (...)} for W1


@dataclass
class ProductionResult:
    payload: dict
    links: List[Link]
    asil: str
    omitted: bool  # agent failed to produce the artifact at all
    injected: List[str]  # defect ids actually injected


class Backend(Protocol):
    def produce(self, req: ProductionRequest, rng: random.Random) -> ProductionResult:
        ...


class SimulatedLLM:
    """Seeded stand-in for an LLM agent.

    Starts from the correct template and injects each candidate catalog
    defect with probability ``inject_p`` (+ correlation / amplification
    bonuses, modelling B1's correlated cross-step failures and B2's
    hallucination propagation through the shared message pool).

    This is a *behavioral* simulation: it does not generate language, it
    generates artifact-level outcomes. All parameters are documented in
    configs.py as modelling assumptions, not measured LLM properties.
    """

    def __init__(
        self,
        inject_p: float,
        correlation_bonus: float = 0.0,
        amplification_bonus: float = 0.0,
    ) -> None:
        self.inject_p = inject_p
        self.correlation_bonus = correlation_bonus
        self.amplification_bonus = amplification_bonus
        self._prev_injected = False
        self._pressure = 0.0  # upstream defect pressure (B2 amplification)

    def set_upstream_pressure(self, n_active: int) -> None:
        """Defects currently active upstream amplify later injections (B2)."""
        self._pressure = self.amplification_bonus * min(3, max(0, n_active))

    def produce(self, req: ProductionRequest, rng: random.Random) -> ProductionResult:
        payload = copy.deepcopy(req.template)
        links = list(req.links)
        asil = req.asil
        p = self.inject_p
        if self._prev_injected:
            p += self.correlation_bonus  # B1: failures correlate across steps
        p += self._pressure  # B2: shared pool propagates hallucinations
        p = min(p, 0.95)

        injected: List[str] = []
        alt_targets = tuple(req.mutation_ctx.get("alt_targets", ()))
        for defect_id in req.candidates:
            if defect_id in req.excluded:
                continue
            if rng.random() >= p:
                continue
            if faults.is_omission(defect_id):
                self._prev_injected = True
                return ProductionResult(
                    payload={}, links=[], asil=req.asil,
                    omitted=True, injected=[defect_id],
                )
            new_asil = faults.apply_mutation(payload, links, defect_id,
                                             alt_targets=alt_targets)
            if new_asil:
                asil = new_asil
            injected.append(defect_id)
        self._prev_injected = bool(injected)
        return ProductionResult(
            payload=payload, links=links, asil=asil,
            omitted=False, injected=injected,
        )


@dataclass
class Agent:
    """A role agent (RA, AA, DCA, CA, TSA-I, TSA-Q) with a pluggable backend."""

    agent_id: str
    backend: Backend

    @property
    def role(self) -> str:
        return AGENT_ROLES[self.agent_id][0]

    @property
    def aspice(self) -> str:
        return AGENT_ROLES[self.agent_id][1]

    def produce(self, req: ProductionRequest, rng: random.Random) -> ProductionResult:
        return self.backend.produce(req, rng)


# --------------------------------------------------------------------- #
# Safety Supervisor: deterministic policy + LLM critic
# --------------------------------------------------------------------- #
@dataclass
class Finding:
    kind: str  # "policy" | "critic"
    detail: str
    defect_hint: Optional[str]  # catalog defect id if the finding maps to one


class SafetySupervisor:
    """Deterministic policy checks (cheap, static, no model calls).

    Catches a *subset* of defects deterministically: dangling link targets
    (S2) and ASIL attribute mismatches against the parent (M4). Full
    structural checking is the ledger's job (I1-I6); the policy models the
    supervisor's lightweight static layer. The supervisor also resolves the
    ASIL-indexed verification method for every gate (``supervise``) and runs
    the H6 ledger-closure confirmation measures (``ledger_closure``).
    """

    POLICY_CATCH = {"S2", "M4"}

    def policy_check(self, env: Envelope, ledger: Ledger) -> List[Finding]:
        findings: List[Finding] = []
        latest = ledger.latest_map()
        for link in env.links:
            if link.target_id not in latest:
                findings.append(
                    Finding("policy",
                            f"dangling link {link.link_type} -> {link.target_id!r}",
                            "S2")
                )
        for link in env.links:
            tgt = latest.get(link.target_id)
            if tgt is None:
                continue
            from .ledger import ASIL_RANK
            if ASIL_RANK[env.asil] < ASIL_RANK[tgt.asil] and not env.payload.get(
                "decomposition_approved"
            ):
                findings.append(
                    Finding("policy",
                            f"ASIL {env.asil} below parent {tgt.asil} without decomposition record",
                            "M4")
                )
        return findings

    def supervise(self, env: Envelope, gate_id: str) -> dict:
        """Apply the ASIL-indexed verification method table (paper Tables III/IV).

        Every gate H1-H6 prescribes a verification method per ASIL; the
        supervisor resolves the method for this artifact and returns its
        rigor calibration (review-effort multiplier, human catch bonus).
        The calibration lives in ``gates.METHOD_RIGOR`` and is a documented
        modelling assumption, not a measured quantity.
        """
        from .gates import method_for, method_rigor

        method = method_for(gate_id, env.asil)
        effort_mult, catch_bonus = method_rigor(method)
        return {"method": method,
                "effort_mult": effort_mult,
                "catch_bonus": catch_bonus}

    def ledger_closure(self, ledger: Ledger) -> Dict[str, bool]:
        """H6 confirmation measures: TC == 1, everything baselined, nothing
        suspect, hash chain intact."""
        from .invariants import traceability_completeness

        latest = ledger.latest_map()
        tc = traceability_completeness(ledger)
        return {
            "tc_equals_1": abs(tc - 1.0) < 1e-9,
            "all_baselined": all(e.status == "baselined" for e in latest.values()),
            "no_suspect": not any(e.suspect for e in latest.values()),
            "chain_intact": ledger.verify_chain(),
        }


class LLMCritic:
    """Behavioral model of the supervisor's LLM critic.

    For each *semantic or link-integrity* defect present in the artifact it
    raises a true finding with probability ``recall``; with probability
    ``corr_p`` it fails *in a correlated way* with the generator (blind to
    the defect regardless of recall -- modelling critic and generator
    sharing a failure mode). It additionally raises a false finding on a
    clean artifact with probability ``fp_rate``. The *assumed* operating
    characteristics are recall (0.70) and per-artifact fp_rate (0.10);
    precision is *emergent* (low defect prevalence -> modest precision, the
    base-rate effect) and is reported against the seeded ground truth so the
    assumption stays auditable. ``false_alarm_rate()`` (FP findings per
    review) feeds the alert-fatigue model in the experiment. All rates are
    documented modelling assumptions (see configs.py), not measured values.
    """

    def __init__(self, recall: float, fp_rate: float, enabled: bool,
                 corr_p: float = 0.0) -> None:
        self.recall = recall
        self.fp_rate = fp_rate
        self.enabled = enabled
        self.corr_p = corr_p
        self.tp = 0
        self.fp = 0
        self.fn = 0
        self.tn = 0
        self.reviews = 0
        self.correlated_misses = 0

    def review(
        self, semantic_present: List[str], rng: random.Random
    ) -> List[Finding]:
        """Review one artifact; ``semantic_present`` are injected semantic or
        link-integrity defect ids."""
        findings: List[Finding] = []
        if not self.enabled:
            return findings
        self.reviews += 1
        for defect_id in semantic_present:
            if self.corr_p > 0.0 and rng.random() < self.corr_p:
                # Correlated failure: critic shares the generator's blind
                # spot on this defect (misses regardless of recall).
                self.fn += 1
                self.correlated_misses += 1
                continue
            if rng.random() < self.recall:
                self.tp += 1
                findings.append(
                    Finding("critic", f"critic flagged {defect_id}", defect_id)
                )
            else:
                self.fn += 1
        if rng.random() < self.fp_rate:
            self.fp += 1
            findings.append(Finding("critic", "critic false alarm", None))
        else:
            self.tn += 1
        return findings

    def false_alarm_rate(self) -> float:
        """False-positive findings per review so far (feeds alert fatigue)."""
        return self.fp / self.reviews if self.reviews else 0.0

    def precision(self) -> Optional[float]:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else None

    def recall_achieved(self) -> Optional[float]:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else None


class HumanReviewer:
    """Models human verification with the different-person rule."""

    def __init__(self, approvers: tuple = ("human_1", "human_2", "human_3")) -> None:
        self.approvers = approvers

    def assign_approver(
        self, author: str, enforce_different_person: bool, rng: random.Random
    ) -> str:
        """Assign an approver and return their id (may equal ``author`` when the
        different-person rule is not enforced, modelling cursory self-review)."""
        if enforce_different_person:
            candidates = [a for a in self.approvers if a != author] or list(self.approvers)
            return rng.choice(candidates)
        # Cursory review: the author may approve their own work (B1).
        if rng.random() < 0.5:
            return author
        return rng.choice(self.approvers)
