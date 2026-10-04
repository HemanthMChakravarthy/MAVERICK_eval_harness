"""Defect seeding for RQ2: inject catalog faults, measure leakage to the next baselined stage."""
import copy, random
CATALOG = ["drop_parent_link", "wrong_asil", "drop_qual_test", "orphan_unit", "drop_allocation", "dangling_link"]

def seed(ledger, fault, rng):
    L = copy.deepcopy(ledger)
    req = [x for x in L.of("SwReq")]; units = L.of("SwUnit"); qt = L.of("QualTest")
    if fault == "drop_parent_link":
        r = rng.choice(req); r.links = [l for l in r.links if l[1] != "derives-from"]; return L, r.id
    if fault == "wrong_asil":
        r = rng.choice([x for x in req if x.asil != "QM"] or req); r.asil = "QM"; return L, r.id
    if fault == "drop_qual_test":
        t = rng.choice(qt); tgt = t.links[0][0]; del L.a[t.id]; return L, tgt
    if fault == "orphan_unit":
        u = rng.choice(units); u.links = [l for l in u.links if l[1] != "implements"]; return L, u.id
    if fault == "drop_allocation":
        r = rng.choice(req); r.links = [l for l in r.links if l[1] != "allocated-to"]; return L, r.id
    if fault == "dangling_link":
        r = rng.choice(req); r.links.append(("SYS-NONEXIST", "derives-from")); return L, r.id
    raise ValueError(fault)

def detected(L, target):
    return any(aid.split(":")[0].split("->")[0] == target for _, aid in L.violations())

def leakage(ledger, n_per_fault=20, seed_=0):
    """Leakage of the *deterministic layer only*. Semantic faults (e.g. inverted inequality,
    missing unit conversion) need execution of tests / human review and are measured in the study."""
    rng = random.Random(seed_); res = {}
    for f in CATALOG:
        miss = sum(not detected(*seed(ledger, f, rng)) for _ in range(n_per_fault))
        res[f] = miss / n_per_fault
    return res
