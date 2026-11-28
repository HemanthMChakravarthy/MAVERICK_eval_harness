"""Mechanism-verification suite (Type-A evidence): checks that the mechanisms
operate as designed, independently of any behavioural parameter."""
import itertools, random, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from maverick_r1.ledger import aeb_fixture, steer_fixture
from maverick_r1.faults import NAMES, CAT, targets, profile, mutate
from maverick_r1.sim import run_one

def test_clean_fixtures_are_compliant():
    for fx in (aeb_fixture, steer_fixture):
        assert fx().tc() == 1.0

def test_every_structural_fault_fires_an_invariant():
    for fx in (aeb_fixture, steer_fixture):
        L = fx()
        for n in NAMES:
            if CAT[n] != "St": continue
            for t in targets(L, n):
                assert profile(L, n, t)["inv"], (fx.__name__, n, t)

def test_semantic_faults_are_invisible_to_invariants():
    L = aeb_fixture()
    for n in NAMES:
        if CAT[n] == "Sm":
            assert not any(profile(L, n, t)["inv"] for t in targets(L, n))

def test_alm_existence_checks_miss_asil_misclassification():
    L = aeb_fixture()
    assert not any(profile(L, "wrong_asil_attr", t)["alm"] for t in targets(L, "wrong_asil_attr"))

def test_hash_chain_detects_tampering():
    L = aeb_fixture(); a = L.a["R3"]; a.payload = dict(a.payload, text="tampered")
    assert not L.chain_ok(a)

def test_revision_marks_downstream_suspect():
    L = aeb_fixture(); L.revise("R3", payload={"text": "TTC < 2.0 s"})
    sus = {k for k, v in L.a.items() if v.status == "suspect"}
    assert {"C3", "DD3", "U3", "QT3", "UT3"} <= sus

def test_union_of_single_fault_profiles_matches_graph():
    rnd = random.Random(0); L0 = aeb_fixture()
    st = [n for n in NAMES if CAT[n] != "Sm"]
    for _ in range(300):
        picks = rnd.sample(st, rnd.randint(1, 5)); L = L0.copy(); aff = set(); seen = set()
        for n in picks:
            ts = [t for t in targets(L0, n) if t not in seen]
            if not ts: continue
            t = rnd.choice(ts); seen.add(t); aff |= profile(L0, n, t)["affected"]; mutate(L, n, t)
        actual = (1 - L.tc()) * len(L0.a)
        assert abs(actual - len(aff)) <= 2

def test_paired_seeds_are_deterministic():
    assert run_one("M", 11) == run_one("M", 11)

def test_full_maverick_enforces_tc_and_zero_structural_escapes():
    for s in range(300):
        r = run_one("M", s)
        assert r["tc_final"] == 1.0 and r["st"] == 0 and r["residual"] == 0

def test_advisory_invariants_never_trigger_rework():
    for s in range(300):
        assert run_one("B4", s)["r_invariant"] == 0


def test_hash_covers_identity_metadata_and_history():
    L = aeb_fixture(); a = L.a["R3"]
    assert L.chain_ok(a)
    a.type = "SysReq"
    assert not L.chain_ok(a)
    L = aeb_fixture(); L.revise("R3", payload={"text": "changed"})
    assert L.chain_ok(L.a["R3"])
    L.history["R3"][0].payload["tampered"] = True
    assert not L.chain_ok(L.a["R3"])

def test_missing_test_verdict_fails_closed():
    L = aeb_fixture(); L.a["RES-UT1"].payload = {}
    assert "RES-UT1" in L.violations()["I11"]

def test_failed_repair_and_failed_escalation_remain_escapes():
    # Disable all probabilistic semantic controls and both repair paths.
    P = dict(p_llm=0.75, p_fix_llm=0.0, p_fix_escalation=0.0,
             critic_recall=0.0, test_scale=0.0, h_st=0.0, h_sm=0.0, h_li=0.0,
             release_st=0.0, release_sm=0.0, release_li=0.0)
    r = run_one("M", 23, P=P)
    assert r["unresolved_detected"] > 0
    assert r["escapes"] > 0

def test_repair_probability_does_not_change_injection_count():
    a = run_one("M", 101, P={"p_fix_llm": 0.0, "p_fix_escalation": 0.0})
    b = run_one("M", 101, P={"p_fix_llm": 1.0, "p_fix_escalation": 1.0})
    assert a["injected"] == b["injected"]

def test_repair_probability_does_not_shift_detection_draws():
    # With escalation always succeeding, every detected defect is resolved, so
    # escapes depend only on detection draws. They must not change with the
    # per-attempt repair probability (no random-stream coupling).
    for cfg in ("M", "B3", "B6"):
        for s in range(100):
            a = run_one(cfg, s, P={"p_fix_llm": 0.60, "p_fix_human": 0.60, "p_fix_escalation": 1.0})
            b = run_one(cfg, s, P={"p_fix_llm": 0.95, "p_fix_human": 0.95, "p_fix_escalation": 1.0})
            assert a["escapes"] == b["escapes"] and a["injected"] == b["injected"]

def test_unresolved_invariant_violation_holds_release_not_escape():
    # If neither rework nor escalation resolves a structural defect that a
    # blocking invariant detects, the release gate re-evaluates the invariant and
    # withholds the release: the defect is neither contained nor released.
    P = dict(p_fix_llm=0.0, p_fix_escalation=0.0, critic_recall=0.0, test_scale=0.0,
             h_st=0.0, h_sm=0.0, h_li=0.0)
    held = 0
    for s in range(50):
        r = run_one("M", s, P=P)
        assert r["st"] == 0 and r["tc_final"] == 1.0
        held += r["held"]
    assert held > 0
    # Without blocking invariants the same defects are released.
    assert sum(run_one("B4", s, P=P)["st"] for s in range(50)) > 0
