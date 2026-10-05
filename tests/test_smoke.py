"""Smoke tests for the MAVERICK evaluation harness v3.

Run with:  pytest tests/   (from the repository root)
"""
import random

import pytest

from maverick import faults
from maverick.agents import SimulatedLLM
from maverick.configs import FULL_ORDER, get_config
from maverick.experiment import run_experiment
from maverick.gates import PromotionInput, evaluate_promotion
from maverick.invariants import CHECK_ORDER, check_all, traceability_completeness
from maverick.ledger import Envelope, Ledger, Link
from maverick.stats import bootstrap_ci, cliffs_delta, holm, wilcoxon_signed_rank


def _mk_ledger_with_defects() -> Ledger:
    """Ledger containing one S1 (orphan unit), one S3 (missing parent) and
    one S4 (ASIL violation) defect, for invariant unit tests."""
    led = Ledger()
    sysr = Envelope(id="SYS-X", atype="SysReq", ver=1, asil="B",
                    payload={"text": "x", "safety": True}, links=[])
    led.append(sysr)
    led.promote_to_baselined(sysr.key, "process")
    req = Envelope(id="SWR-X", atype="SwReq", ver=1, asil="B",
                   payload={"text": "x"}, links=[],  # S3: no derives-from
                   prov={"author": "RA"})
    led.append(req)
    led.promote_to_baselined(req.key, "process")
    orphan = Envelope(id="UNIT-O", atype="SwUnit", ver=1, asil="B",
                      payload={"function": "f"}, links=[],  # S1: orphan
                      prov={"author": "DCA"})
    led.append(orphan)
    led.promote_to_baselined(orphan.key, "process")
    bad_asil = Envelope(id="UNIT-A", atype="SwUnit", ver=1, asil="A",  # S4
                        payload={"function": "g"},
                        links=[Link("implements", "SWR-X")],
                        prov={"author": "DCA"})
    led.append(bad_asil)
    led.promote_to_baselined(bad_asil.key, "process")
    return led


def test_hash_chain_intact():
    led = Ledger()
    for i in range(3):
        e = Envelope(id=f"A-{i}", atype="SwReq", ver=1, asil="B",
                     payload={"n": i}, links=[])
        led.append(e)
    assert led.verify_chain()
    assert led.head_hash == led.get("A-2#v1").h
    assert led.get("A-2#v1").h_prev == led.get("A-1#v1").h


def test_status_lifecycle_rejects_skip():
    led = Ledger()
    e = Envelope(id="A", atype="SwReq", ver=1, asil="B", payload={}, links=[])
    led.append(e)
    with pytest.raises(ValueError):
        led.transition(e.key, "baselined")  # must not skip steps
    led.transition(e.key, "machine-checked")
    led.transition(e.key, "human-approved")
    led.transition(e.key, "baselined")
    assert led.get(e.key).status == "baselined"


def test_suspect_propagation():
    led = Ledger()
    for lid, atype, links in [
        ("SYS-1", "SysReq", []),
        ("SWR-1", "SwReq", [Link("derives-from", "SYS-1")]),
        ("UNIT-1", "SwUnit", [Link("implements", "SWR-1")]),
        ("UT-1", "UnitTest", [Link("verifies", "UNIT-1")]),
    ]:
        e = Envelope(id=lid, atype=atype, ver=1, asil="B", payload={}, links=links)
        led.append(e)
        led.promote_to_baselined(e.key, "human")
    new = led.new_version("SWR-1", payload={"changed": True},
                          links=[Link("derives-from", "SYS-1")],
                          prov={}, change_note="CR-1")
    assert led.get("UNIT-1#v1").suspect
    assert led.get("UT-1#v1").suspect
    assert not led.get("SYS-1#v1").suspect  # upstream of the change: unaffected
    assert not new.suspect
    assert not led.consumable("UNIT-1")  # suspect artifacts are not consumable


def test_invariants_catch_structural_defects():
    led = _mk_ledger_with_defects()
    viols = check_all(led)
    assert any(v.artifact_id == "UNIT-O" for v in viols["I4"])  # S1 orphan
    assert any(v.artifact_id == "SWR-X" for v in viols["I1"])  # S3 missing parent
    assert any(v.artifact_id == "UNIT-A" for v in viols["I6"])  # S4 ASIL
    assert traceability_completeness(led) < 1.0


def test_tc_clean_ledger_is_one():
    led = Ledger()
    sysr = Envelope(id="SYS-X", atype="SysReq", ver=1, asil="B",
                    payload={"text": "x", "safety": True}, links=[])
    led.append(sysr)
    led.promote_to_baselined(sysr.key, "process")
    req = Envelope(id="SWR-X", atype="SwReq", ver=1, asil="B", payload={"text": "x"},
                   links=[Link("derives-from", "SYS-X"), Link("allocated-to", "COMP-X")])
    led.append(req)
    led.promote_to_baselined(req.key, "process")
    comp = Envelope(id="COMP-X", atype="SwArch", ver=1, asil="B",
                    payload={"kind": "component"}, links=[])
    led.append(comp)
    led.promote_to_baselined(comp.key, "process")
    des = Envelope(id="DES-COMP-X", atype="SwDesign", ver=1, asil="B",
                   payload={"text": "d"},
                   links=[Link("refines", "COMP-X")])
    led.append(des)
    led.promote_to_baselined(des.key, "process")
    unit = Envelope(id="UNIT-X", atype="SwUnit", ver=1, asil="B", payload={},
                    links=[Link("implements", "SWR-X"),
                           Link("realizes", "DES-COMP-X")])
    led.append(unit)
    led.promote_to_baselined(unit.key, "process")
    for tid, ttype, tgt in [("UT-X", "UnitTest", "UNIT-X"),
                            ("CT-X", "CompTest", "UNIT-X"),
                            ("QT-X", "QualTest", "SWR-X")]:
        t = Envelope(id=tid, atype=ttype, ver=1, asil="B", payload={},
                     links=[Link("verifies", tgt),
                            Link("verifies-design", "DES-COMP-X")])
        led.append(t)
        led.promote_to_baselined(t.key, "process")
        r = Envelope(id=f"RES-{tid}", atype="Result", ver=1, asil="B",
                     payload={"verdict": "pass", "for": tid},
                     links=[Link("result-of", tid)])
        led.append(r)
        led.promote_to_baselined(r.key, "process")
    assert check_all(led) == {k: [] for k in CHECK_ORDER}
    assert traceability_completeness(led) == 1.0


def test_promotion_rules():
    base = dict(envelope_key="E#v1", inv_ok=True, cov_ok=True,
                open_critic_findings=0, author="RA", approver="human_1",
                attempts=0)
    assert evaluate_promotion(PromotionInput(**base)).promotable
    # different-person rule
    d = evaluate_promotion(PromotionInput(**{**base, "approver": "RA"}))
    assert not d.promotable and any("differ from author" in r for r in d.reasons)
    # invariant failure blocks
    d = evaluate_promotion(PromotionInput(**{**base, "inv_ok": False}))
    assert not d.promotable
    # undispositioned critic findings block
    d = evaluate_promotion(PromotionInput(**{**base, "open_critic_findings": 2}))
    assert not d.promotable
    # retry budget exhaustion escalates
    d = evaluate_promotion(PromotionInput(**{**base, "attempts": 4, "retry_budget": 3}))
    assert d.escalate and not d.promotable


def test_experiment_deterministic():
    r1 = run_experiment("M", 0)
    r2 = run_experiment("M", 0)
    assert r1.final_tc == r2.final_tc
    assert r1.total_minutes == r2.total_minutes
    assert r1.n_leaked == r2.n_leaked
    assert [g.leaked for g in r1.gates] == [g.leaked for g in r2.gates]
    assert r1.chain_ok and r2.chain_ok


def test_config_contrast_m_beats_b2():
    # On fixed seeds, the full pipeline should dominate the unsupervised baseline.
    for seed in (0, 1, 2):
        m = run_experiment("M", seed)
        b2 = run_experiment("B2", seed)
        assert m.final_tc >= b2.final_tc
        assert (m.n_leaked / max(m.n_injected, 1)) <= (
            b2.n_leaked / max(b2.n_injected, 1))
    assert {c for c in FULL_ORDER} == {"B0", "B1", "B2", "B3", "B4", "B5",
                                       "M", "M-noledger", "M-nocritic",
                                       "M-nopolicy"}


def test_no_network_in_default_mode():
    # The experiment path uses only the SimulatedLLM backend: no sockets,
    # no API clients, no subprocesses anywhere in the default run.
    import socket
    import maverick.agents as agents_mod
    import maverick.experiment as exp_mod
    assert not hasattr(agents_mod, "RealLLMAdapter")
    for mod in (agents_mod, exp_mod):
        src = open(mod.__file__).read()
        assert "import socket" not in src
        assert "urllib" not in src and "requests" not in src
        assert "ANTHROPIC" not in src and "OPENAI" not in src
    be = SimulatedLLM(0.75)
    assert isinstance(be, SimulatedLLM)
    socket.setdefaulttimeout(0.001)  # would break any real network attempt fast
    r = run_experiment("M", 0)
    assert r.chain_ok
    socket.setdefaulttimeout(None)


def test_gate_prescope_blocks_early_temporal_violations():
    """Pre-promotion checks must not fail on downstream work that does not
    exist yet (I2b/I5 at H1); they must still catch the gate's own defects."""
    from maverick.gates import GATE_PRECHECKS
    from maverick.invariants import check_envelope
    led = Ledger()
    sysr = Envelope(id="SYS-X", atype="SysReq", ver=1, asil="B",
                    payload={"text": "x", "safety": True}, links=[])
    led.append(sysr)
    led.promote_to_baselined(sysr.key, "process")
    # SwReq at H1: no units/tests exist yet -> full check_all would flag
    # I2/I3/I5, but the H1 prescope (I1, I6) must be clean.
    req = Envelope(id="SWR-X", atype="SwReq", ver=1, asil="B", payload={"text": "x"},
                   links=[Link("derives-from", "SYS-X")])
    led.append(req)
    assert check_envelope(led, req.key, only=GATE_PRECHECKS["H1"]) == []
    assert len(check_envelope(led, req.key)) > 0  # unscoped: temporal violations
    # ...while a genuine H1 defect (S3: missing parent link) is caught.
    bad = Envelope(id="SWR-Y", atype="SwReq", ver=1, asil="B", payload={}, links=[])
    led.append(bad)
    assert any(v.check == "I1" for v in
               check_envelope(led, bad.key, only=GATE_PRECHECKS["H1"]))


def test_stats_helpers():
    mean, lo, hi = bootstrap_ci([1.0, 2.0, 3.0, 4.0])
    assert lo <= mean <= hi
    _, p = wilcoxon_signed_rank([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert p == 1.0
    _, p2 = wilcoxon_signed_rank([5, 6, 7, 8, 9, 10], [1, 1, 1, 1, 1, 1])
    assert 0.0 < p2 < 0.05
    adj = holm([0.01, 0.04, 0.5])
    assert adj[0] <= adj[1] <= adj[2]
    assert all(0.0 <= a <= 1.0 for a in adj)


def test_fault_catalog_complete():
    ids = {d.defect_id for d in faults.CATALOG}
    assert ids == ({f"S{i}" for i in range(1, 7)} | {f"M{i}" for i in range(1, 7)}
                   | {"W1", "W2", "R1"})
    assert all(d.kind in ("structural", "semantic", "link-integrity")
               for d in faults.CATALOG)
    # W1/W2/R1 are invisible to the ledger/ALM link-existence mechanisms.
    for did in ("W1", "W2", "R1"):
        db = faults.get(did).detectable_by
        assert "ledger" not in db and "alm" not in db
        assert "critic" in db and "human" in db


def _clean_ledger_i7() -> Ledger:
    """Minimal ledger with a design-linked test + passing result."""
    led = Ledger()
    for lid, atype, links in [
        ("SYS-X", "SysReq", []),
        ("SWR-X", "SwReq", [Link("derives-from", "SYS-X")]),
        ("DES-X", "SwDesign", []),
        ("UNIT-X", "SwUnit", [Link("implements", "SWR-X"),
                              Link("realizes", "DES-X")]),
        ("UT-X", "UnitTest", [Link("verifies", "UNIT-X"),
                              Link("verifies-design", "DES-X")]),
    ]:
        e = Envelope(id=lid, atype=atype, ver=1, asil="B", payload={}, links=links)
        led.append(e)
        led.promote_to_baselined(e.key, "human")
    return led


def test_i7_i8_catch_missing_design_links():
    from maverick.invariants import CHECKS
    led = _clean_ledger_i7()
    assert CHECKS["I7"](led) == []
    # Drop the verifies-design link -> I7 fires.
    t = led.get("UT-X#v1")
    t.links = [l for l in t.links if l.link_type != "verifies-design"]
    assert any(v.check == "I7" for v in CHECKS["I7"](led))
    # A unit without a CompTest -> I8 fires.
    assert any(v.check == "I8" for v in CHECKS["I8"](led))


def test_i9_i10_i11_result_invariants():
    from maverick.invariants import CHECKS
    led = _clean_ledger_i7()
    # No result recorded -> I9 fires.
    assert any(v.check == "I9" for v in CHECKS["I9"](led))
    r = Envelope(id="RES-UT-X", atype="Result", ver=1, asil="B",
                 payload={"verdict": "fail", "for": "UT-X"},
                 links=[Link("result-of", "UT-X")])
    led.append(r)
    led.promote_to_baselined(r.key, "human")
    assert CHECKS["I9"](led) == []
    assert CHECKS["I10"](led) == []
    # Verdict "fail" -> I11 fires; "pass" clears it.
    assert any(v.check == "I11" for v in CHECKS["I11"](led))
    r.payload["verdict"] = "pass"
    assert CHECKS["I11"](led) == []


def test_w1_w2_invisible_to_existence_checks():
    """Wrong-target (W1) and spurious (W2) links must not trip I1/I4/I7."""
    from maverick.invariants import CHECKS
    led = _clean_ledger_i7()
    other = Envelope(id="DES-Y", atype="SwDesign", ver=1, asil="B",
                     payload={}, links=[])
    led.append(other)
    led.promote_to_baselined(other.key, "human")
    payload, links = {"text": "x"}, [Link("verifies-design", "DES-X")]
    faults.apply_mutation(payload, links, "W1", alt_targets=("DES-X", "DES-Y"))
    t = led.get("UT-X#v1")
    t.links = [Link("verifies", "UNIT-X")] + links  # wrong design target
    assert CHECKS["I7"](led) == []  # existence still satisfied
    payload2, links2 = {"text": "y"}, [Link("derives-from", "SYS-X")]
    faults.apply_mutation(payload2, links2, "W2", alt_targets=("SYS-X",))
    # W2 appends a spurious derives-from to a real SysReq: I1 still clean.
    s = led.get("SWR-X#v1")
    s.links = links2
    assert CHECKS["I1"](led) == []


def test_new_baselines_configured():
    for cid, flag in [("B3", "alm_checks"), ("B4", "advisory_checks"),
                      ("B5", "audit_pass")]:
        cfg = get_config(cid)
        assert getattr(cfg, flag) is True
        assert cfg.ledger_checks is False
    assert get_config("B3").authoring_scale == 1.0  # human-authored
    assert get_config("B4").authoring_scale == 0.05  # LLM-drafted


def test_cliffs_delta_sanity():
    d, mag = cliffs_delta([5, 6, 7, 8], [1, 1, 1, 1])
    assert d == 1.0 and mag == "large"
    d2, mag2 = cliffs_delta([1, 2, 3], [1, 2, 3])
    assert d2 == 0.0 and mag2 == "negligible"


def test_asild_fixture_builds_and_runs():
    from maverick.case_study import build_case_study
    cs = build_case_study("asild")
    assert cs.fixture_id == "asild"
    assert cs.retry_budget == 5
    assert any(u.uid == "UNIT-log-torque" for u in cs.units)
    r = run_experiment("M", 0, fixture="asild")
    assert r.chain_ok
    assert r.fixture == "asild"


def test_sweep_overrides_deterministic():
    r1 = run_experiment("M", 3, overrides={"critic_recall": 0.5})
    r2 = run_experiment("M", 3, overrides={"critic_recall": 0.5})
    assert r1.total_minutes == r2.total_minutes
    assert r1.n_leaked == r2.n_leaked
