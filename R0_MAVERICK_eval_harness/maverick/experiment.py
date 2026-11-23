"""Experiment orchestration: run one (config, seed) simulation end to end.

A run walks gates H1..H6 in order. At each gate the role agent produces its
artifacts from the case-study templates via the configured backend
(``SimulatedLLM`` by default), seeded defects may be injected, and the
configuration's mechanisms engage:

1. deterministic checks (ledger invariants / supervisor policy) with bounded
   retry (k=3) then human escalation;
2. LLM critic review of semantic defects (findings are dispositioned);
3. human approval under the different-person rule (calibrated catch rates);
4. promotion via ``gates.evaluate_promotion``;
5. gate-level omission handling, structural coverage (H4/H5), a seeded
   requirement-change scenario with suspect propagation (H5), and ledger
   closure (H6).

Everything is driven by seeded ``random.Random`` streams, so a
(config, seed) pair is fully deterministic. No network calls are made.
"""
from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Set, Tuple

from . import faults
from .agents import (
    AGENT_ROLES,
    Agent,
    HumanReviewer,
    LLMCritic,
    ProductionRequest,
    SafetySupervisor,
    SimulatedLLM,
)
from .case_study import CaseStudy, build_case_study
from .configs import PipelineConfig, get_config
from .gates import (
    GATE_ORDER,
    GATE_PRECHECKS,
    GATES,
    PromotionInput,
    coverage_target,
    evaluate_promotion,
)
from .invariants import check_all, check_envelope, traceability_completeness
from .ledger import Envelope, Ledger, Link
from .metrics import (
    sample_authoring_minutes,
    sample_review_minutes,
    simulate_coverage,
    simulate_interface_coverage,
)

#: Verification rigor per configuration for the coverage stub (documented
#: assumption): how much verification the configuration actually generates
#: and passes. Drives the *explained* config-dependence of achieved coverage.
COVERAGE_RIGOR = {
    "B0": 0.90, "B1": 0.30, "B2": 0.20, "B3": 0.85, "B4": 0.70, "B5": 0.50,
    "M": 1.00, "M-noledger": 0.90, "M-nocritic": 0.95, "M-nopolicy": 1.00,
}

#: Artifact types that are test cases (I7/I9/I11 scope).
TEST_TYPES = ("UnitTest", "CompTest", "IntTest", "QualTest")


def _master_seed(config_id: str, fixture: str, seed: int) -> int:
    h = hashlib.sha256(f"maverick:v3:{config_id}:{fixture}:{seed}".encode()).hexdigest()
    return int(h[:16], 16)


def _sub_rng(master: int, salt: int) -> random.Random:
    return random.Random((master + salt * 0x9E3779B1) & 0xFFFFFFFFFFFFFFFF)


# --------------------------------------------------------------------- #
# result records
# --------------------------------------------------------------------- #
@dataclass
class InjectedRecord:
    defect_id: str
    kind: str  # structural | semantic | link-integrity
    target_gate: str
    artifact: str
    detected: bool = False
    detected_by: str = ""  # ledger | alm | policy | critic | human-review | human-escalation | coverage | test | audit
    detected_gate: str = ""
    leaked: bool = False


@dataclass
class GateRecord:
    gate_id: str
    produced: int = 0
    violations: Dict[str, int] = field(default_factory=dict)
    injected: int = 0
    detected: int = 0
    leaked: int = 0
    minutes: float = 0.0
    retries: int = 0
    escalations: int = 0
    advisory: int = 0  # B4: non-blocking post-check findings
    suspect_reverified: int = 0
    coverage_min_branch: Optional[float] = None
    closure: Dict[str, bool] = field(default_factory=dict)  # H6 confirmation measures


@dataclass
class RunResult:
    config_id: str
    seed: int
    fixture: str
    gates: List[GateRecord]
    final_tc: float
    first_pass_tc: float  # prescope invariants satisfied on first production
    residual_violations: Dict[str, int]
    total_minutes: float
    authoring_minutes: float
    review_minutes: float
    critic_precision: Optional[float]
    critic_recall: Optional[float]
    n_injected: int
    n_detected: int
    n_leaked: int
    n_leaked_structural: int
    n_leaked_semantic: int  # semantic + link-integrity
    n_leaked_link_integrity: int
    n_audit_found: int
    n_advisory: int
    n_escalations: int  # retry-budget exhaustions
    n_retries: int
    leakage_by_gate: Dict[str, float]
    coverage_min_branch: Optional[float]
    coverage_shortfalls_leaked: int
    self_approvals: int
    change_impacts_untracked: int
    chain_ok: bool
    injected: List[InjectedRecord] = field(default_factory=list)


# --------------------------------------------------------------------- #
# experiment
# --------------------------------------------------------------------- #
class Experiment:
    def __init__(
        self,
        config_id: str,
        seed: int,
        fixture: str = "aeb",
        overrides: Optional[Dict] = None,
    ) -> None:
        self.cfg: PipelineConfig = get_config(config_id)
        if overrides:
            # Sensitivity sweeps: one-way parameter overrides (documented).
            self.cfg = replace(self.cfg, **overrides)
        self.seed = seed
        self.fixture = fixture
        master = _master_seed(config_id, fixture, seed)
        self.rng_inject = _sub_rng(master, 1)
        self.rng_review = _sub_rng(master, 2)
        self.rng_critic = _sub_rng(master, 3)
        self.rng_minutes = _sub_rng(master, 4)
        self.rng_cov = _sub_rng(master, 5)
        self.rng_misc = _sub_rng(master, 6)

        self.cs: CaseStudy = build_case_study(fixture)
        # The fixture's retry budget overrides the config default (ASIL-D: k=5).
        self.cfg = replace(self.cfg, retry_budget=self.cs.retry_budget)
        # ASIL-D fixture: mandatory independent human review at every gate.
        self.independent_review = (fixture == "asild")
        self.ledger = Ledger()
        self.backends = {
            aid: SimulatedLLM(
                self.cfg.inject_p,
                self.cfg.correlation_bonus,
                self.cfg.amplification_bonus,
            )
            for aid in AGENT_ROLES
        }
        self.agents = {aid: Agent(aid, be) for aid, be in self.backends.items()}
        self.supervisor = SafetySupervisor()
        self.critic = LLMCritic(
            self.cfg.critic_recall, self.cfg.critic_fp_rate,
            self.cfg.critic_enabled, self.cfg.corr_p,
        )
        self.reviewer = HumanReviewer()

        self.records: List[InjectedRecord] = []
        self._rec_by_defect: Dict[str, InjectedRecord] = {}
        self._injected_ever: Set[str] = set()
        self._correct: Dict[str, Tuple[dict, List[Link], str]] = {}
        self._applied: Dict[str, List[str]] = {}
        self._candidates: Dict[str, List[str]] = {}
        self._first_pass: Dict[str, bool] = {}
        self._advisory_findings = 0
        self._authoring_minutes = 0.0
        self._review_minutes = 0.0
        self._targets = self._assign_targets()

        self.self_approvals = 0
        self.change_impacts_untracked = 0
        self.coverage_shortfalls_leaked = 0
        self._branch_covs: List[float] = []

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _prov(self, agent_id: str) -> dict:
        author = "human_1" if self.cfg.config_id == "B0" else agent_id
        return {
            "author": author,
            "prompter": "prompter_1",
            "model": "simulated-llm",
            "config": self.cfg.config_id,
            "seed": self.seed,
        }

    def _assign_targets(self) -> Dict[str, Tuple[str, str]]:
        """Map each catalog defect to the (kind, spec id) it targets this run."""
        r = self.rng_misc
        sw = [s.rid for s in self.cs.sw_reqs]
        units = [u.uid for u in self.cs.units]
        if self.cs.fixture_id == "asild":
            return {
                "S3": ("swreq", r.choice(sw)),
                "M3": ("omit-swreq", "SWR-S104"),
                "M4": ("swreq", r.choice(sw)),
                "M5": ("swreq", "SWR-S101"),
                "M6": ("swreq", r.choice(sw)),
                "W2": ("swreq", r.choice(sw)),
                "R1": ("swreq", r.choice(sw)),
                "S1": ("unit", units[0]),
                "S2": ("unit", units[1]),
                "S4": ("unit", units[2]),
                "S5": ("omit-unit", units[3]),
                "M1": ("unit", units[0]),
                "M2": ("unit", units[1]),
                "S6": ("omit-qualtest", "SWR-S103"),
                "W1": ("unittest", f"UT-{units[0]}"),
            }
        return {
            "S3": ("swreq", r.choice(sw)),
            "M3": ("omit-swreq", "SWR-005"),
            "M4": ("swreq", r.choice(sw)),
            "M5": ("swreq", "SWR-003"),
            "M6": ("swreq", r.choice(sw)),
            "W2": ("swreq", r.choice(sw)),
            "R1": ("swreq", r.choice(sw)),
            "S1": ("unit", "UNIT-kalman-update"),
            "S2": ("unit", "UNIT-compute-ttc"),
            "S4": ("unit", "UNIT-radar-match"),
            "S5": ("omit-unit", "UNIT-plaus-score"),
            "M1": ("unit", "UNIT-brake-decision"),
            "M2": ("unit", "UNIT-kalman-update"),
            "S6": ("omit-qualtest", "SWR-005"),
            "W1": ("unittest", f"UT-{r.choice(units)}"),
        }

    def _candidates_for(self, gate_id: str, kind: str, sid: str) -> List[str]:
        out = []
        for d, (k, s) in self._targets.items():
            if k == kind and s == sid and faults.get(d).target_gate == gate_id:
                out.append(d)
        return out

    def _record_injection(self, defect_id: str, gate: str, artifact: str) -> None:
        spec = faults.get(defect_id)
        rec = InjectedRecord(defect_id, spec.kind, gate, artifact)
        self.records.append(rec)
        self._rec_by_defect[defect_id] = rec
        self._injected_ever.add(defect_id)

    def _mark_detected(self, defect_id: str, by: str, gate: str) -> None:
        rec = self._rec_by_defect[defect_id]
        rec.detected = True
        rec.detected_by = by
        rec.detected_gate = gate

    def _register(
        self,
        env: Envelope,
        injected: List[str],
        candidates: List[str],
        true_asil: str,
        correct_payload: Optional[dict] = None,
        correct_links: Optional[List[Link]] = None,
    ) -> None:
        """Snapshot the *correct* baseline for later rework.

        ``true_asil`` is the spec's intended ASIL (defects such as M4/S4 may
        have corrupted ``env.asil`` already); ``correct_payload`` /
        ``correct_links`` are the pristine pre-injection artifacts. When
        omitted they default to the envelope's current content, which is only
        valid for productions no defect targets.
        """
        self._correct[env.key] = (
            copy.deepcopy(correct_payload if correct_payload is not None else env.payload),
            list(correct_links if correct_links is not None else env.links),
            true_asil,
        )
        self._applied[env.key] = list(injected)
        self._candidates[env.key] = list(candidates)

    def _mutation_alt_targets(self, defect_id: str) -> tuple:
        """Candidate wrong-target ids for W1/W2 (fixture-aware)."""
        if defect_id == "W1":
            return tuple(f"DES-{a.aid}" for a in self.cs.arch
                         if a.kind == "component")
        if defect_id == "W2":
            return tuple(s.rid for s in self.cs.sys_reqs)
        return ()

    def _fix_defect(self, key: str, defect_id: str) -> None:
        """Rework an artifact: rebuild from the correct baseline minus the defect."""
        payload, links, asil = self._correct[key]
        new_payload = copy.deepcopy(payload)
        new_links = list(links)
        new_asil = asil
        remaining = [d for d in self._applied[key] if d != defect_id]
        for d in remaining:
            r = faults.apply_mutation(
                new_payload, new_links, d,
                alt_targets=self._mutation_alt_targets(d))
            if r:
                new_asil = r
        env = self.ledger.get(key)
        env.payload = new_payload
        env.links = new_links
        env.asil = new_asil
        self._applied[key] = remaining
        self.ledger.repair_hash(key)

    def _reroll(self, key: str, gate_id: str) -> List[str]:
        """Regeneration may introduce new defects (honest re-roll of candidates)."""
        new: List[str] = []
        env = self.ledger.get(key)
        for d in self._candidates.get(key, []):
            if d in self._injected_ever or faults.is_omission(d):
                continue
            if self.rng_inject.random() < min(self.cfg.inject_p, 0.95):
                r = faults.apply_mutation(
                    env.payload, env.links, d,
                    alt_targets=self._mutation_alt_targets(d))
                if r:
                    env.asil = r
                self._applied[key].append(d)
                self._record_injection(d, gate_id, key)
                new.append(d)
        if new:
            self.ledger.repair_hash(key)
        return new

    def _violation_counts(self) -> Dict[str, int]:
        return {k: len(v) for k, v in check_all(self.ledger).items()}

    # ------------------------------------------------------------------ #
    # test-result helpers (I9/I10/I11)
    # ------------------------------------------------------------------ #
    def _tested_key(self, test_key: str) -> Optional[str]:
        """Envelope key of the artifact a test verifies (via ``verifies``)."""
        env = self.ledger.get(test_key)
        for l in env.links:
            if l.link_type == "verifies":
                try:
                    return self.ledger.latest(l.target_id).key
                except KeyError:
                    return None
        return None

    def _test_verdict(self, test_key: str) -> str:
        """Seeded behavioral verdict: "fail" iff the tested artifact still has
        ≥1 injected defect applied (the test genuinely exercises a defective
        artifact); else "pass"."""
        tkey = self._tested_key(test_key)
        if tkey and self._applied.get(tkey):
            return "fail"
        return "pass"

    def _record_result(
        self,
        test_id: str,
        verdict: str,
        asil: str,
        prov: dict,
        extra: Optional[dict] = None,
    ) -> Envelope:
        """Create (or re-record as a new version) the Result for a test.

        Every result links back to its test specification via ``result-of``
        (I10); every test has a recorded result (I9); promotion requires the
        latest verdict to be "pass" (I11).
        """
        payload = {"verdict": verdict, "for": test_id}
        if extra:
            payload.update(extra)
        links = [Link("result-of", test_id)]
        rid = f"RES-{test_id}"
        if rid in self.ledger:
            env = self.ledger.new_version(
                rid, payload=payload, links=links, prov=prov, asil=asil,
                change_note=f"re-recorded verdict={verdict}",
            )
        else:
            env = Envelope(id=rid, atype="Result", ver=1, asil=asil,
                           payload=payload, links=links, prov=prov)
            self.ledger.append(env)
        self._register(env, [], [], asil)
        return env

    def _record_test_result(self, test_env, verdict: str, prov: dict,
                            extra: Optional[dict] = None):
        """Record a Result for a test, honoring T1/T4 defect flags.

        T1 (missing-result): skip recording entirely (I9 violation).
        T4 (dangling-result-link): record then mutate the link to dangle (I10).
        Returns the Result envelope, or None if T1 skipped.
        """
        if test_env.payload.get("_t1_skip_result"):
            return None
        res_env = self._record_result(
            test_env.id, verdict, test_env.asil, prov, extra=extra
        )
        if test_env.payload.get("_t4_dangle_result"):
            res_latest = self.ledger.latest(res_env.id)
            dangling_links = [Link("result-of", "GHOST-TEST-999")]
            new_res = self.ledger.new_version(
                res_env.id, payload=res_latest.payload,
                links=dangling_links, prov=prov,
                asil=res_latest.asil,
                change_note="T4: dangling result-of link",
            )
            self._register(new_res, [], [], res_latest.asil)
            return new_res
        return res_env

    # ------------------------------------------------------------------ #
    # pipeline stages
    # ------------------------------------------------------------------ #
    def _seed_sysreqs(self) -> None:
        for s in self.cs.sys_reqs:
            env = Envelope(
                id=s.rid, atype="SysReq", ver=1, asil=s.asil,
                payload={"text": s.text, "safety": s.safety},
                links=[], prov={"author": "process-input"},
            )
            self.ledger.append(env)
            self.ledger.promote_to_baselined(env.key, "process")

    def _process_artifact(
        self, key: str, gate_id: str, rec: GateRecord, cov_ok: bool = True
    ) -> None:
        """Run one artifact through check -> critic -> human -> promote."""
        cfg = self.cfg
        env = self.ledger.get(key)
        n_initial = len(self._applied.get(key, []))
        remaining = list(self._applied.get(key, []))
        attempts = 0

        # First-pass measurement (reported as first-pass TC): gate-prescope
        # invariants satisfied on first production, before any retry/rework.
        self._first_pass[key] = not check_envelope(
            self.ledger, key, only=GATE_PRECHECKS[gate_id]
        )

        # Authoring cost: human-rate for B0/B3, LLM-draft rate otherwise.
        authored = sample_authoring_minutes(
            self.rng_minutes, env.atype, env.asil, cfg.authoring_scale
        )
        rec.minutes += authored
        self._authoring_minutes += authored

        # Phase A: deterministic checks (ledger invariants / ALM link-existence
        # subset / supervisor policy) with bounded retry, then escalation.
        while True:
            hits: List[Tuple[str, str]] = []
            seen: Set[str] = set()
            if cfg.ledger_checks:
                for d in remaining:
                    if "ledger" in faults.get(d).detectable_by and d not in seen:
                        hits.append((d, "ledger"))
                        seen.add(d)
            if cfg.alm_checks:
                # B3: ALM-style link-existence checks catch missing
                # links/artifacts only -- never W1/W2/R1 or ASIL faults.
                for d in remaining:
                    if "alm" in faults.get(d).detectable_by and d not in seen:
                        hits.append((d, "alm"))
                        seen.add(d)
            if cfg.supervisor_policy:
                for d in remaining:
                    if "policy" in faults.get(d).detectable_by and d not in seen:
                        hits.append((d, "policy"))
                        seen.add(d)
            if not hits:
                break
            d, by = hits[0]
            attempts += 1
            self._fix_defect(key, d)
            remaining.remove(d)
            if attempts > cfg.retry_budget:
                # Retry budget exhausted -> human escalation.
                self._mark_detected(d, "human-escalation", gate_id)
                rec.minutes += 45.0
                rec.escalations += 1
            else:
                self._mark_detected(d, by, gate_id)
                rec.retries += 1
                for nd in self._reroll(key, gate_id):
                    remaining.append(nd)

        # Phase B: LLM critic on semantic and link-integrity defects; findings
        # are dispositioned.
        if cfg.critic_enabled:
            sem = [
                d for d in remaining
                if faults.get(d).kind in ("semantic", "link-integrity")
                and "critic" in faults.get(d).detectable_by
            ]
            for f in self.critic.review(sem, self.rng_critic):
                rec.minutes += 10.0  # disposition effort per finding
                if f.defect_hint and f.defect_hint in remaining:
                    self._fix_defect(key, f.defect_hint)
                    self._mark_detected(f.defect_hint, "critic", gate_id)
                    remaining.remove(f.defect_hint)

        # Phase C: human approval under the different-person rule, using the
        # ASIL-indexed verification method prescribed for this gate (paper
        # Tables III/IV, via the Safety Supervisor). Alert fatigue: the
        # critic's accumulated false-alarm rate degrades effective recall.
        sup = self.supervisor.supervise(env, gate_id)
        env.prov["verification_method"] = sup["method"]
        author = env.prov["author"]
        approver = self.reviewer.assign_approver(
            author, cfg.different_person_enforced, self.rng_review
        )
        if self.independent_review and approver == author:
            # ASIL-D fixture: mandatory independent review at every gate.
            approver = self.reviewer.assign_approver(author, True, self.rng_review)
        if approver == author:
            self.self_approvals += 1
        far = self.critic.false_alarm_rate()
        fatigue_mult = max(0.0, 1.0 - cfg.fatigue_factor * far)
        for d in list(remaining):
            base_p = (
                cfg.human_catch_struct
                if faults.get(d).kind == "structural"
                else cfg.human_catch_sem
            )
            p = min((base_p + sup["catch_bonus"]) * fatigue_mult, 0.99)
            if self.rng_review.random() < p:
                self._fix_defect(key, d)
                self._mark_detected(d, "human-review", gate_id)
                remaining.remove(d)
        reviewed = sup["effort_mult"] * sample_review_minutes(
            self.rng_minutes, env.atype, env.asil, n_initial, cfg.effort_scale
        )
        rec.minutes += reviewed
        self._review_minutes += reviewed

        # Result re-record for tests: the verdict follows the tested
        # artifact's current defect state (I11). T1/T4 flags honored.
        if env.atype in TEST_TYPES:
            self._record_test_result(
                env, self._test_verdict(key), self._prov("TSA-R")
            )

        # Phase D: promotion decision promote(E).
        # Pre-promotion invariant scope is gate-dependent: downstream
        # completeness (I2b/I5/I8) cannot hold until later gates produce their
        # artifacts, so only the gate's prescope checks block promotion.
        if cfg.ledger_checks:
            prescope = GATE_PRECHECKS[gate_id]
            inv_ok = not check_envelope(self.ledger, key, only=prescope)
            if inv_ok:  # only baselined artifacts are consumable downstream
                for link in self.ledger.get(key).links:
                    try:
                        if not self.ledger.consumable(link.target_id):
                            inv_ok = False
                            break
                    except KeyError:
                        inv_ok = False
                        break
        else:
            inv_ok = True  # this configuration does not check
        decision = evaluate_promotion(
            PromotionInput(
                envelope_key=key,
                inv_ok=inv_ok,
                cov_ok=cov_ok,
                open_critic_findings=0,  # all findings dispositioned in Phase B
                author=author,
                approver=approver,
                attempts=attempts,
                retry_budget=cfg.retry_budget,
            )
        )
        if not decision.promotable:
            # Escalation path: a human resolves whatever is left, then promote.
            for d in list(remaining):
                self._fix_defect(key, d)
                self._mark_detected(d, "human-escalation", gate_id)
                remaining.remove(d)
                rec.minutes += 45.0
                rec.escalations += 1
            if env.atype in TEST_TYPES and self._test_verdict(key) == "fail":
                # I11: the test failed -> root-cause the tested artifact.
                # The failing verification test *finds* the escaped defect.
                # The tested artifact is already baselined, so rework goes
                # through a new version, not in-place repair.
                tkey = self._tested_key(key)
                if tkey is not None:
                    tenv = self.ledger.get(tkey)
                    correct_payload, correct_links, true_asil = self._correct[tkey]
                    for d in list(self._applied.get(tkey, [])):
                        self._mark_detected(d, "test", gate_id)
                        rec.minutes += 30.0  # failure investigation + rework
                    new_tested = self.ledger.new_version(
                        tenv.id, payload=copy.deepcopy(correct_payload),
                        links=list(correct_links),
                        prov=self._prov("DCA"), asil=true_asil,
                        change_note=f"{gate_id} failing-test rework",
                    )
                    self._register(new_tested, [], [], true_asil,
                                   correct_payload=correct_payload,
                                   correct_links=correct_links)
                    home_gate = {"SwUnit": "H3", "SwReq": "H1"}.get(tenv.atype,
                                                                   gate_id)
                    self._process_artifact(new_tested.key, home_gate, rec)
                    rec.produced += 1
                    self._record_result(env.id, "pass", env.asil,
                                        self._prov("TSA-R"))
        self.ledger.promote_to_baselined(key, approver)

        # B4: advisory invariant post-check -- findings trigger rework (the
        # artifact is fixed) but do not block promotion. This models "we run
        # the checks and act on findings, but nothing blocks".
        if cfg.advisory_checks:
            findings = check_envelope(
                self.ledger, key, only=GATE_PRECHECKS[gate_id]
            )
            if findings:
                rec.advisory += len(findings)
                self._advisory_findings += len(findings)
                rec.minutes += 5.0 * len(findings)  # triage
                # Findings trigger rework: structural defects identified by
                # the checks are marked detected (not leaked).
                for d in list(remaining):
                    spec = faults.get(d)
                    if spec.kind == "structural":
                        self._rec_by_defect[d].detected = True
                        self._rec_by_defect[d].detected_by = "advisory"
                        self._rec_by_defect[d].detected_gate = gate_id
                        remaining.remove(d)
                        rec.minutes += 30.0  # rework per advisory-found defect
                        rec.retries += 1

        for d in remaining:  # never detected -> leaked downstream
            self._rec_by_defect[d].leaked = True

    def _handle_omissions(self, gate_id: str, rec: GateRecord) -> None:
        """Gate completeness review for omission defects (S5, S6, M3)."""
        pending = [
            r for r in self.records
            if r.target_gate == gate_id and not r.detected and not r.leaked
            and faults.is_omission(r.defect_id)
        ]
        for irec in pending:
            caught = False
            if self.cfg.ledger_checks:
                # Deterministic completeness review (H1 requirements review,
                # H3/H6 ledger closure checks): the missing artifact is authored.
                self._author_missing(irec, gate_id, rec, by="ledger")
                caught = True
            if not caught and self.rng_review.random() < self.cfg.human_catch_struct:
                self._author_missing(irec, gate_id, rec, by="human-review")
                caught = True
            if not caught:
                irec.leaked = True

    def _author_missing(
        self, irec: InjectedRecord, gate_id: str, rec: GateRecord, by: str
    ) -> None:
        """Human authors the omitted artifact correctly (30 min)."""
        spec = faults.get(irec.defect_id)
        _, kind, _ = spec.target.split(":")
        # The omitted artifact id is fixture-aware: resolve it from the
        # injection record, not from the catalog target template.
        if kind == "qualtest":
            sid = irec.artifact.removeprefix("QT-")
        else:
            sid = irec.artifact
        if kind == "swreq":
            s = self.cs.sw_req(sid)
            env = Envelope(
                id=sid, atype="SwReq", ver=1, asil=s.asil,
                payload={"text": s.text, "derived": s.derived, "safety": s.safety},
                links=[Link("derives-from", p) for p in s.derives_from],
                prov=self._prov("RA"),
            )
        elif kind == "unit":
            u = self.cs.unit(sid)
            env = Envelope(
                id=sid, atype="SwUnit", ver=1, asil=u.asil,
                payload=copy.deepcopy(u.template),
                links=[Link("implements", r) for r in u.implements]
                + [Link("realizes", f"DES-{u.arch}")]
                + [Link("allocated-to", u.arch)],
                prov=self._prov("DCA"),
            )
        elif kind == "qualtest":
            sw = self.cs.sw_req(sid)
            links = [Link("verifies", sid)]
            design_id = self._design_for_req(sid)
            if design_id is not None:
                links.append(Link("verifies-design", design_id))
            env = Envelope(
                id=f"QT-{sid}", atype="QualTest", ver=1, asil=sw.asil,
                payload={"text": f"Qualification test for {sid}",
                         "method": "requirements-based test"},
                links=links,
                prov=self._prov("TSA-Q"),
            )
        else:
            raise ValueError(f"cannot author missing artifact for {irec.defect_id}")
        self.ledger.append(env)
        self._register(env, [], [], env.asil)  # human-authored: as-produced == correct
        self._mark_detected(irec.defect_id, by, gate_id)
        res_key = None
        if env.atype in TEST_TYPES:
            # Re-authored tests get their result recorded before processing.
            res_env = self._record_result(
                env.id, self._test_verdict(env.key), env.asil,
                self._prov("TSA-R"))
            res_key = res_env.id
        rec.minutes += 30.0
        rec.produced += 1
        self._process_artifact(env.key, gate_id, rec)
        if res_key is not None:
            self._process_artifact(self.ledger.latest(res_key).key, gate_id, rec)
            rec.produced += 1

    # ------------------------------------------------------------------ #
    # gates
    # ------------------------------------------------------------------ #
    def _allocation_map(self) -> Dict[str, List[str]]:
        alloc: Dict[str, Set[str]] = {}
        for u in self.cs.units:
            for r in u.implements:
                alloc.setdefault(r, set()).add(u.arch)
        return {k: sorted(v) for k, v in alloc.items()}

    def _h1(self) -> GateRecord:
        rec = GateRecord("H1")
        for spec in self.cs.sw_reqs:
            cands = self._candidates_for("H1", "swreq", spec.rid)
            cands += self._candidates_for("H1", "omit-swreq", spec.rid)
            req = ProductionRequest(
                "H1", "swreq", spec.rid,
                template={"text": spec.text, "derived": spec.derived, "safety": spec.safety},
                links=[Link("derives-from", p) for p in spec.derives_from],
                asil=spec.asil, candidates=cands,
                mutation_ctx={"alt_targets": tuple(s.rid for s in self.cs.sys_reqs)},
            )
            res = self.agents["RA"].produce(req, self.rng_inject)
            if res.omitted:
                self._record_injection(res.injected[0], "H1", spec.rid)
                continue
            env = Envelope(id=spec.rid, atype="SwReq", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links, prov=self._prov("RA"))
            self.ledger.append(env)
            for d in res.injected:
                self._record_injection(d, "H1", env.key)
            # Pristine baseline: req.template / req.links are never mutated by
            # produce() (it deep-copies), so they are the correct references.
            self._register(env, res.injected, cands, spec.asil,
                           correct_payload=req.template, correct_links=req.links)
            self._process_artifact(env.key, "H1", rec)
            rec.produced += 1
        self._handle_omissions("H1", rec)
        return rec

    def _h2(self) -> GateRecord:
        rec = GateRecord("H2")
        for spec in self.cs.arch:
            req = ProductionRequest(
                "H2", "arch", spec.aid,
                template={"text": spec.text, "kind": spec.kind},
                links=[], asil=spec.asil, candidates=[],
            )
            res = self.agents["AA"].produce(req, self.rng_inject)
            env = Envelope(id=spec.aid, atype="SwArch", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links, prov=self._prov("AA"))
            self.ledger.append(env)
            self._register(env, res.injected, [], spec.asil)
            self._process_artifact(env.key, "H2", rec)
            rec.produced += 1
        # Allocation: SwReq --allocated-to--> SwArch, as new versions.
        alloc = self._allocation_map()
        for spec in self.cs.sw_reqs:
            if spec.rid not in self.ledger:
                continue  # omitted and leaked (no-ledger configurations)
            old = self.ledger.latest(spec.rid)
            correct_payload, correct_links, _ = self._correct[old.key]
            base_links = list(correct_links) + [
                Link("allocated-to", aid) for aid in alloc.get(spec.rid, ())
            ]
            base_payload = copy.deepcopy(correct_payload)
            new_links = list(base_links)
            new_payload = copy.deepcopy(base_payload)
            new_asil = old.asil
            applied = list(self._applied.get(old.key, []))
            for d in applied:  # re-apply defects still present on the old version
                r = faults.apply_mutation(
                    new_payload, new_links, d,
                    alt_targets=self._mutation_alt_targets(d))
                if r:
                    new_asil = r
            new = self.ledger.new_version(
                spec.rid, payload=new_payload, links=new_links,
                prov=self._prov("AA"), asil=new_asil,
                change_note="allocation of SwReq to SwArch elements",
            )
            self._register(new, applied, [], spec.asil,
                           correct_payload=base_payload, correct_links=base_links)
            self._process_artifact(new.key, "H2", rec)
            rec.produced += 1
        self._handle_omissions("H2", rec)
        return rec

    def _design_id(self, arch_id: str) -> str:
        return f"DES-{arch_id}"

    def _h3(self) -> GateRecord:
        rec = GateRecord("H3")
        # Detailed design (SWE.3): one SwDesign per software component,
        # refining its SwArch element. Units realize their design (I4).
        for spec in self.cs.arch:
            if spec.kind != "component":
                continue
            did = self._design_id(spec.aid)
            req = ProductionRequest(
                "H3", "design", did,
                template={"text": f"Detailed design of {spec.aid}",
                          "decomposition": f"{spec.aid} behavior, interfaces, data"},
                links=[Link("refines", spec.aid)],
                asil=spec.asil, candidates=[],
            )
            res = self.agents["DCA"].produce(req, self.rng_inject)
            env = Envelope(id=did, atype="SwDesign", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links,
                           prov=self._prov("DCA"))
            self.ledger.append(env)
            self._register(env, res.injected, [], spec.asil)
            self._process_artifact(env.key, "H3", rec)
            rec.produced += 1
        # Units (SWE.3): implement SwReqs and realize the detailed design.
        for spec in self.cs.units:
            cands = self._candidates_for("H3", "unit", spec.uid)
            cands += self._candidates_for("H3", "omit-unit", spec.uid)
            req = ProductionRequest(
                "H3", "unit", spec.uid,
                template=copy.deepcopy(spec.template),
                links=[Link("implements", r) for r in spec.implements]
                + [Link("realizes", self._design_id(spec.arch))]
                + [Link("allocated-to", spec.arch)],
                asil=spec.asil, candidates=cands,
            )
            res = self.agents["DCA"].produce(req, self.rng_inject)
            if res.omitted:
                self._record_injection(res.injected[0], "H3", spec.uid)
                continue
            env = Envelope(id=spec.uid, atype="SwUnit", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links, prov=self._prov("DCA"))
            self.ledger.append(env)
            for d in res.injected:
                self._record_injection(d, "H3", env.key)
            self._register(env, res.injected, cands, spec.asil,
                           correct_payload=req.template, correct_links=req.links)
            self._process_artifact(env.key, "H3", rec)
            rec.produced += 1
        self._handle_omissions("H3", rec)
        return rec

    def _h4(self) -> GateRecord:
        rec = GateRecord("H4")
        rigor = COVERAGE_RIGOR[self.cfg.config_id]
        for spec in self.cs.units:
            if spec.uid not in self.ledger:
                continue  # omitted and leaked
            unit_env = self.ledger.latest(spec.uid)
            test_id = f"UT-{spec.uid}"

            # Structural coverage (deterministic tool stub) BEFORE the test is
            # produced: Cov(E, a) is part of promote(E), and a shortfall
            # rooted in the unit (seeded defect) triggers unit rework as a new
            # version. Achieved coverage depends on the configuration's
            # verification rigor (documented assumption, metrics.py).
            has_defect = bool(self._applied.get(unit_env.key, []))
            cov = simulate_coverage(self.seed, spec.uid, has_defect,
                                    self.rng_cov, rigor=rigor)
            short = [
                m for m in ("statement", "branch", "mcdc")
                if cov[m] < coverage_target("H4", m, unit_env.asil)
            ]
            if short and self.cfg.coverage_enforced:
                if has_defect:
                    # Coverage investigation finds the root cause in the unit:
                    # rework as a new baselined version (paper Sec. III). All
                    # defects still applied to the unit are suspect and fixed.
                    # (The unit is already baselined, so rework goes through
                    # a new version built from the correct baseline.)
                    old_key = unit_env.key
                    correct_payload, correct_links, true_asil = self._correct[old_key]
                    for d in list(self._applied.get(old_key, [])):
                        self._mark_detected(d, "coverage", "H4")
                    new_unit = self.ledger.new_version(
                        spec.uid, payload=copy.deepcopy(correct_payload),
                        links=list(correct_links),
                        prov=self._prov("DCA"), asil=true_asil,
                        change_note="H4 coverage investigation: rework defective unit",
                    )
                    self._register(new_unit, [], [], true_asil,
                                   correct_payload=correct_payload,
                                   correct_links=correct_links)
                    rec.minutes += 30.0
                    self._process_artifact(new_unit.key, "H3", rec)  # unit rework
                    rec.produced += 1
                    unit_env = new_unit
                    cov = simulate_coverage(self.seed, spec.uid, False,
                                            self.rng_cov, rigor=rigor)
                else:
                    rec.retries += 1  # regenerate tests; flaky gap usually clears
                    cov = simulate_coverage(self.seed, spec.uid, False,
                                            self.rng_cov, rigor=rigor)
                short = [
                    m for m in ("statement", "branch", "mcdc")
                    if cov[m] < coverage_target("H4", m, unit_env.asil)
                ]
            if short and not self.cfg.coverage_enforced:
                self.coverage_shortfalls_leaked += 1
            self._branch_covs.append(cov["branch"])
            cov_ok = not short or not self.cfg.coverage_enforced

            cands = self._candidates_for("H4", "unittest", test_id)
            design_id = self._design_id(spec.arch)
            req = ProductionRequest(
                "H4", "unittest", test_id,
                template={"text": f"Unit test for {spec.uid}",
                          "method": "requirements-based + boundary value"},
                links=[Link("verifies", spec.uid),
                       Link("verifies-design", design_id)],
                asil=unit_env.asil, candidates=cands,
                mutation_ctx={"alt_targets": self._mutation_alt_targets("W1")},
            )
            res = self.agents["CA"].produce(req, self.rng_inject)
            env = Envelope(id=test_id, atype="UnitTest", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links, prov=self._prov("CA"))
            self.ledger.append(env)
            for d in res.injected:
                self._record_injection(d, "H4", env.key)
            self._register(env, res.injected, cands, self._correct[unit_env.key][2],
                           correct_payload=req.template, correct_links=req.links)
            # Record the result BEFORE the test is processed: I9 (recorded),
            # I10 (result-of link) and I11 (verdict "pass") are pre-promotion
            # checks. The verdict follows the tested unit's defect state.
            # T1/T4 flags honored via _record_test_result.
            res_env = self._record_test_result(
                env, self._test_verdict(env.key), self._prov("CA"),
                extra={"coverage": cov, "shortfalls": short},
            )
            self._process_artifact(env.key, "H4", rec, cov_ok=cov_ok)
            rec.produced += 1
            if res_env is not None:
                self._process_artifact(self.ledger.latest(res_env.id).key, "H4", rec)
                rec.produced += 1
        self._handle_omissions("H4", rec)
        if self._branch_covs:
            rec.coverage_min_branch = min(self._branch_covs)
        return rec

    def _h5(self) -> GateRecord:
        rec = GateRecord("H5")
        rigor = COVERAGE_RIGOR[self.cfg.config_id]
        # Component verification (SWE.5), distinct from integration testing:
        # one CompTest per architectural component (I8 quantifies over
        # SwArch kind="component", not SwUnit).
        for arch_spec in [a for a in self.cs.arch if a.kind == "component"]:
            if arch_spec.aid not in self.ledger:
                continue  # omitted and leaked
            arch_env = self.ledger.latest(arch_spec.aid)
            test_id = f"CT-{arch_spec.aid}"
            req = ProductionRequest(
                "H5", "comptest", test_id,
                template={"text": f"Component test for {arch_spec.aid}",
                          "method": "component requirements-based test"},
                links=[Link("verifies", arch_spec.aid),
                       Link("verifies-design", self._design_id(arch_spec.aid))],
                asil=arch_env.asil, candidates=[],
            )
            res = self.agents["TSA-I"].produce(req, self.rng_inject)
            # T2 defect: omit the CompTest for the targeted component.
            if res.omitted:
                for d in res.injected:
                    self._record_injection(d, "H5", test_id)
                continue
            env = Envelope(id=test_id, atype="CompTest", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links,
                           prov=self._prov("TSA-I"))
            self.ledger.append(env)
            self._register(env, res.injected, [],
                           self._correct[arch_env.key][2] if arch_env.key in self._correct else (None, None, None))
            res_env = self._record_test_result(
                env, self._test_verdict(env.key), self._prov("TSA-I")
            )
            self._process_artifact(env.key, "H5", rec)
            rec.produced += 1
            if res_env is not None:
                self._process_artifact(self.ledger.latest(res_env.id).key, "H5", rec)
                rec.produced += 1
        # Integration tests, one per interface. The verifies-design link
        # points at the detailed design of the first component (fixture
        # convention): the integration test exercises that design's
        # interface behavior.
        components = sorted(a.aid for a in self.cs.arch if a.kind == "component")
        if_design = self._design_id(components[0]) if components else None
        for spec in [a for a in self.cs.arch if a.kind == "interface"]:
            test_id = f"IT-{spec.aid}"
            links = [Link("verifies", spec.aid)]
            if if_design is not None:
                links.append(Link("verifies-design", if_design))
            req = ProductionRequest(
                "H5", "inttest", test_id,
                template={"text": f"Integration test for interface {spec.aid}",
                          "method": "interface call-sequence test"},
                links=links,
                asil=spec.asil, candidates=[],
            )
            res = self.agents["TSA-I"].produce(req, self.rng_inject)
            env = Envelope(id=test_id, atype="IntTest", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links, prov=self._prov("TSA-I"))
            self.ledger.append(env)
            self._register(env, res.injected, [], spec.asil)

            cov = simulate_interface_coverage(self.seed, spec.aid, self.rng_cov,
                                              rigor=rigor)
            short = [
                m for m in ("function", "call")
                if cov[m] < coverage_target("H5", m, spec.asil)
            ]
            if short and self.cfg.coverage_enforced:
                rec.retries += 1
                cov = simulate_interface_coverage(self.seed, spec.aid,
                                                  self.rng_cov, rigor=rigor)
                short = [
                    m for m in ("function", "call")
                    if cov[m] < coverage_target("H5", m, spec.asil)
                ]
            if short and not self.cfg.coverage_enforced:
                self.coverage_shortfalls_leaked += 1
            cov_ok = not short or not self.cfg.coverage_enforced

            res_env = self._record_result(
                test_id, self._test_verdict(env.key), spec.asil,
                self._prov("TSA-I"),
                extra={"coverage": cov, "shortfalls": short})
            self._process_artifact(env.key, "H5", rec, cov_ok=cov_ok)
            rec.produced += 1
            self._process_artifact(self.ledger.latest(res_env.id).key, "H5", rec)
            rec.produced += 1
        self._change_scenario(rec)
        self._handle_omissions("H5", rec)
        return rec

    def _change_scenario(self, rec: GateRecord) -> None:
        """Seeded requirement change (CR-014): new SwReq version, suspect propagation."""
        present = [s.rid for s in self.cs.sw_reqs if s.rid in self.ledger]
        target = self.rng_misc.choice(present)
        old = self.ledger.latest(target)
        old_correct_payload, old_correct_links, old_true_asil = self._correct[old.key]
        # Pristine base for the new version: the old *correct* baseline plus
        # the CR-014 change (never the defected working copy).
        correct_payload = copy.deepcopy(old_correct_payload)
        correct_payload["ttc_threshold_s"] = 3.0
        correct_payload["change"] = "CR-014: TTC threshold 2.5 s -> 3.0 s"
        correct_links = list(old_correct_links)
        new = self.ledger.new_version(
            target, payload=copy.deepcopy(correct_payload),
            links=list(correct_links), prov=self._prov("RA"),
            asil=old_true_asil, change_note="CR-014",
        )
        self._register(new, [], [], old_true_asil,
                       correct_payload=correct_payload, correct_links=correct_links)
        for d in self._applied.get(old.key, []):
            r = faults.apply_mutation(
                new.payload, new.links, d,
                alt_targets=self._mutation_alt_targets(d))
            if r:
                new.asil = r
            self._applied[new.key].append(d)
        self.ledger.repair_hash(new.key)
        self._candidates[new.key] = []
        # Full re-review of the changed requirement itself.
        self._process_artifact(new.key, "H5", rec)
        rec.produced += 1

        impacted = self.ledger.descendants(target)
        if self.cfg.ledger_checks:
            for key in sorted(impacted):
                env = self.ledger.get(key)
                check_envelope(self.ledger, key)  # re-run invariant queries
                env.suspect = False
                rec.minutes += 0.5 * sample_review_minutes(
                    self.rng_minutes, env.atype, env.asil, 0, self.cfg.effort_scale
                )
                rec.suspect_reverified += 1
        else:
            # No suspect protocol: change impact is untracked.
            self.change_impacts_untracked = len(impacted)
            for key in impacted:
                self.ledger.get(key).suspect = False

    def _design_for_req(self, rid: str) -> Optional[str]:
        """Detailed-design id covering a requirement (via its first unit)."""
        impls = sorted((u.uid for u in self.cs.units if rid in u.implements))
        if not impls:
            return None
        return self._design_id(self.cs.unit(impls[0]).arch)

    def _h6(self) -> GateRecord:
        rec = GateRecord("H6")
        for spec in self.cs.sw_reqs:
            if spec.rid not in self.ledger:
                continue  # omitted and leaked (M3 in no-ledger configurations)
            sw = self.ledger.latest(spec.rid)
            test_id = f"QT-{spec.rid}"
            cands = self._candidates_for("H6", "omit-qualtest", spec.rid)
            links = [Link("verifies", spec.rid)]
            design_id = self._design_for_req(spec.rid)
            if design_id is not None:
                links.append(Link("verifies-design", design_id))
            req = ProductionRequest(
                "H6", "qualtest", test_id,
                template={"text": f"Qualification test for {spec.rid}",
                          "method": "requirements-based test"},
                links=links,
                asil=sw.asil, candidates=cands,
            )
            res = self.agents["TSA-Q"].produce(req, self.rng_inject)
            if res.omitted:
                self._record_injection(res.injected[0], "H6", test_id)
                continue
            env = Envelope(id=test_id, atype="QualTest", ver=1, asil=res.asil,
                           payload=res.payload, links=res.links,
                           prov=self._prov("TSA-Q"))
            self.ledger.append(env)
            for d in res.injected:
                self._record_injection(d, "H6", env.key)
            self._register(env, res.injected, cands, self._correct[sw.key][2])
            res_env = self._record_result(
                test_id, self._test_verdict(env.key), sw.asil,
                self._prov("TSA-Q"))
            self._process_artifact(env.key, "H6", rec)
            rec.produced += 1
            self._process_artifact(self.ledger.latest(res_env.id).key, "H6", rec)
            rec.produced += 1
        self._handle_omissions("H6", rec)
        # SS ledger closure: H6 confirmation measures (TC == 1, all baselined,
        # no suspect artifacts, chain intact).
        rec.closure = self.supervisor.ledger_closure(self.ledger)
        return rec

    def _finalize_gate(self, rec: GateRecord) -> None:
        gid = rec.gate_id
        rec.injected = sum(1 for r in self.records if r.target_gate == gid)
        rec.detected = sum(1 for r in self.records if r.detected_gate == gid)
        rec.leaked = sum(1 for r in self.records if r.target_gate == gid and r.leaked)
        rec.violations = self._violation_counts()
        rec.minutes = round(rec.minutes, 2)

    def _audit_pass(self, gate_records: List[GateRecord]) -> int:
        """B5 post-hoc audit (Sameh & Elbanna style).

        After the release-equivalent (H6), a manual audit pass reviews every
        artifact (``audit_minutes_per_artifact`` each) and finds each escaped
        defect with probability ``audit_recall``; every found issue costs
        ``audit_rework_minutes`` of rework. The audit cannot block the
        release: found defects were still gate-pipeline escapes, so
        ``leaked`` stays True. Correlated failure (``corr_p``) applies: with
        probability corr_p the auditor shares the generator's blind spot and
        misses the defect. Returns the number of audit-found defects.
        """
        rec = gate_records[-1]  # audit effort charged to H6
        n_artifacts = len(self.ledger.latest_map())
        rec.minutes += self.cfg.audit_minutes_per_artifact * n_artifacts
        found = 0
        for irec in self.records:
            if irec.leaked and not irec.detected:
                # Correlated failure: auditor shares generator's blind spot.
                if self.rng_review.random() < self.cfg.corr_p:
                    continue
                if self.rng_review.random() < self.cfg.audit_recall:
                    irec.detected = True
                    irec.detected_by = "audit"
                    irec.detected_gate = "H6"
                    rec.minutes += self.cfg.audit_rework_minutes
                    found += 1
        return found

    def run(self) -> RunResult:
        self._seed_sysreqs()
        gate_records: List[GateRecord] = []
        for gi, gate_id in enumerate(GATE_ORDER):
            # B2 amplification: active upstream defects pressurise this gate.
            if gi > 0:
                prev = GATE_ORDER[gi - 1]
                active = sum(
                    1 for r in self.records
                    if r.target_gate == prev and not r.detected
                )
                for be in self.backends.values():
                    be.set_upstream_pressure(active)
            rec = getattr(self, f"_{gate_id.lower()}")()
            self._finalize_gate(rec)
            gate_records.append(rec)

        n_audit_found = self._audit_pass(gate_records) if self.cfg.audit_pass else 0

        order_index = {g: i for i, g in enumerate(GATE_ORDER)}
        leakage_by_gate: Dict[str, float] = {}
        for g in GATE_ORDER:
            gi = order_index[g]
            denom = [r for r in self.records if order_index[r.target_gate] <= gi]
            if not denom:
                leakage_by_gate[g] = 0.0
                continue
            leaked = [
                r for r in denom
                if r.leaked
                or (r.detected and order_index[r.detected_gate] > gi)
            ]
            leakage_by_gate[g] = len(leaked) / len(denom)

        n_injected = len(self.records)
        n_detected = sum(1 for r in self.records if r.detected)
        leaked = [r for r in self.records if r.leaked]
        n_leaked = len(leaked)
        n_leaked_structural = sum(1 for r in leaked if r.kind == "structural")
        n_leaked_link = sum(1 for r in leaked if r.kind == "link-integrity")
        n_leaked_semantic = sum(1 for r in leaked if r.kind != "structural")

        first_pass_tc = (
            sum(1 for v in self._first_pass.values() if v)
            / len(self._first_pass) if self._first_pass else 1.0
        )

        return RunResult(
            config_id=self.cfg.config_id,
            seed=self.seed,
            fixture=self.fixture,
            gates=gate_records,
            final_tc=traceability_completeness(self.ledger),
            first_pass_tc=first_pass_tc,
            residual_violations=self._violation_counts(),
            total_minutes=round(sum(r.minutes for r in gate_records), 2),
            authoring_minutes=round(self._authoring_minutes, 2),
            review_minutes=round(self._review_minutes, 2),
            critic_precision=self.critic.precision(),
            critic_recall=self.critic.recall_achieved(),
            n_injected=n_injected,
            n_detected=n_detected,
            n_leaked=n_leaked,
            n_leaked_structural=n_leaked_structural,
            n_leaked_semantic=n_leaked_semantic,
            n_leaked_link_integrity=n_leaked_link,
            n_audit_found=n_audit_found,
            n_advisory=self._advisory_findings,
            n_escalations=sum(r.escalations for r in gate_records),
            n_retries=sum(r.retries for r in gate_records),
            leakage_by_gate=leakage_by_gate,
            coverage_min_branch=min(self._branch_covs) if self._branch_covs else None,
            coverage_shortfalls_leaked=self.coverage_shortfalls_leaked,
            self_approvals=self.self_approvals,
            change_impacts_untracked=self.change_impacts_untracked,
            chain_ok=self.ledger.verify_chain(),
            injected=self.records,
        )


def run_experiment(
    config_id: str,
    seed: int,
    fixture: str = "aeb",
    overrides: Optional[Dict] = None,
) -> RunResult:
    """Run one (config, seed) simulation. Deterministic; no network calls.

    ``fixture`` selects the worked-example fixture ("aeb" | "asild");
    ``overrides`` are one-way PipelineConfig overrides for sensitivity sweeps.
    """
    return Experiment(config_id, seed, fixture=fixture, overrides=overrides).run()
