"""MAVERICK gate configuration v3 (drop-in replacement for the policy tables in supervisor.py).
Conservative default informed by ISO 26262:2018; selects every highly recommended (++) method per ASIL.
Method tables cited are *alternative entries* (ISO 26262-2/-6/-8, 4.3): project may substitute via safety plan + rationale."""

# H1-H5: verification gates. Independence I0-I3 does NOT apply; approver != author/prompter is mandatory
# (ISO 26262-8 9.4.3.2 / 9.4.2.4 "should" -> MAVERICK "shall").
VERIFICATION = {
  "H1": {"A": ["walkthrough"], "B": ["inspection"], "C": ["inspection", "semiformal_verif"],
         "D": ["inspection", "semiformal_verif"]},                                   # Part 8 Table 2
  "H2": {"A": ["walkthrough"], "B": ["inspection"],
         "C": ["inspection", "control_flow", "data_flow", "scheduling"],
         "D": ["inspection", "control_flow", "data_flow", "scheduling", "simulation", "prototype"]},  # Part 6 Table 4
  "H3": {"A": ["walkthrough", "static_code"], "B": ["inspection", "static_code"],
         "C": ["inspection", "semiformal_verif", "control_flow", "data_flow", "static_code"],
         "D": ["inspection", "semiformal_verif", "control_flow", "data_flow", "static_code"]},       # Part 6 Table 7
  "H4": {"A": ["req_test", "interface_test"], "B": ["req_test", "interface_test"],
         "C": ["req_test", "interface_test", "back_to_back_if_mbd"],
         "D": ["req_test", "interface_test", "back_to_back_if_mbd", "fault_injection", "resource_usage"]},
  "H5": {"A": [], "B": [], "C": [], "D": []},
}
COVERAGE = {  # target 100 %; shortfall needs extra tests or recorded rationale (Part 6 9.4.4)
  "H4": {"QM": [], "A": ["statement"], "B": ["statement", "branch"], "C": ["branch"], "D": ["branch", "mcdc"]},  # Table 9 ++
  "H5": {"QM": [], "A": ["function", "call"], "B": ["function", "call"], "C": ["function", "call"], "D": ["function", "call"]},  # Table 12; A/B recommendation (10.4.5)
}
H5_COVERAGE_MANDATORY = {"QM": False, "A": False, "B": False, "C": True, "D": True}  # "(A), (B)" in 10.4.5

# H6: confirmation measures, ISO 26262-2 Table 1. None = no requirement; ("I0","rec") = recommended.
CONFIRMATION = {
  "review_safety_analyses": {"QM": None, "A": "I1", "B": "I1", "C": "I2", "D": "I3"},
  "review_safety_case":     {"QM": None, "A": "I1", "B": "I1", "C": "I2", "D": "I3"},
  "fs_audit":               {"QM": None, "A": None, "B": ("I0", "rec"), "C": "I2", "D": "I3"},
  "fs_assessment":          {"QM": None, "A": None, "B": ("I0", "rec"), "C": "I2", "D": "I3"},
}
LEVEL = {"I0": 0, "I1": 1, "I2": 2, "I3": 3}

def h6_check(asil, approvals, authors):
    """approvals: {measure: (person, independence_level_str)}; returns list of blocking reasons."""
    reasons = []
    for m, req in CONFIRMATION.items():
        r = req[asil]
        if r is None: continue
        lvl, recommended = (r if isinstance(r, tuple) else (r, None))
        got = approvals.get(m)
        if got is None:
            if recommended != "rec": reasons.append(f"{m}: missing (required {lvl})")
            continue
        person, ind = got
        if person in authors: reasons.append(f"{m}: performed by author")
        if LEVEL[ind] < LEVEL[lvl]: reasons.append(f"{m}: independence {ind} < {lvl}")
    return reasons

if __name__ == "__main__":
    au = {"alice"}
    assert h6_check("A", {}, au) == ["review_safety_analyses: missing (required I1)", "review_safety_case: missing (required I1)"]
    assert h6_check("B", {"review_safety_analyses": ("bob", "I1"), "review_safety_case": ("bob", "I1")}, au) == []  # audit/assessment recommended only
    r = h6_check("D", {m: ("carol", "I2") for m in CONFIRMATION}, au); assert len(r) == 4 and all("I2 < I3" in x for x in r)
    assert h6_check("C", {m: ("alice", "I2") for m in CONFIRMATION}, au) == [f"{m}: performed by author" for m in CONFIRMATION]
    assert COVERAGE["H4"]["D"] == ["branch", "mcdc"] and not H5_COVERAGE_MANDATORY["B"]
    print("gate_policy v3 self-test: 5/5 OK")
