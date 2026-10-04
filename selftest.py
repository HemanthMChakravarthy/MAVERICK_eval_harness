"""SELF-TEST ON A SYNTHETIC TOY GRAPH. Verifies harness correctness only. NOT experimental results."""
import random
from maverick.ledger import Ledger, Envelope
from maverick.supervisor import SafetySupervisor, Approval
from maverick.seeding import leakage
from maverick.stats import median_ci, holm

L = Ledger()
for i in range(3): L.put(Envelope(f"SYS-{i}", "SysReq", 1, "B", {"t": f"sys {i}"}))
for i in range(3):
    L.put(Envelope(f"SWR-{i}", "SwReq", 1, "B", {"t": f"swr {i}"}, links=[(f"SYS-{i}", "derives-from"), ("ARC-0", "allocated-to")]))
L.put(Envelope("ARC-0", "SwArch", 1, "B", {}, interfaces=["ObjList", "TTC"]))
L.put(Envelope("U-0", "SwUnit", 1, "B", {}, links=[("ARC-0", "implements")]))
L.put(Envelope("UT-0", "UnitTest", 1, "B", {}, links=[("U-0", "verifies")]))
L.put(Envelope("IT-0", "IntTest", 1, "B", {"interfaces": ["ObjList", "TTC"]}, links=[("ARC-0", "verifies")]))
for i in range(3): L.put(Envelope(f"QT-{i}", "QualTest", 1, "B", {}, links=[(f"SWR-{i}", "verifies")]))

assert L.violations() == [], L.violations(); assert L.tc() == 1.0
print("clean graph: violations=0, TC=1.0  OK")

L.put(Envelope("SYS-0", "SysReq", 1, "B", {"t": "changed"}))
assert "SWR-0" in L.suspect and "QT-0" in L.suspect; print("change -> suspect:", sorted(L.suspect), " OK")

S = SafetySupervisor(L, critic=lambda e: ["unverifiable wording"] if e.id == "SWR-1" else [])
assert S.promote(L.a["SWR-0"], "H1")[0] is False                                    # no approval
assert S.promote(L.a["SWR-0"], "H1", approval=Approval("rev", 0, {"SWR-0"}))[0] is False  # author = reviewer
assert S.promote(L.a["SWR-0"], "H1", approval=Approval("rev", 0))[0] is True
assert S.promote(L.a["SWR-1"], "H1", approval=Approval("rev", 0))[0] is False        # critic finding open
assert S.promote(L.a["SWR-1"], "H1", approval=Approval("rev", 0), dispositions=["unverifiable wording"])[0]
assert S.promote(L.a["U-0"], "H4", coverage={"statement": 1.0, "branch": 0.9}, approval=Approval("r", 0))[0] is False
print("supervisor decision rule (Eq. 3): all 6 checks OK")

print("deterministic-layer leakage on toy graph:", leakage(L, 10))
r = random.Random(1); print("stats smoke:", median_ci([r.random() for _ in range(10)]), holm({"a": .01, "b": .04, "c": .03}))
