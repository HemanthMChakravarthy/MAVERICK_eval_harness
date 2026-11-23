"""Seeded behavioural simulation over the executable ledger."""
from __future__ import annotations
import numpy as np
from .ledger import aeb_fixture, steer_fixture
from .faults import CATALOG, NAMES, CAT, STAGE, TEST_P, targets, profile
from .params import BASE, AUTHOR_MIN, REVIEW_MIN, EFFORT
from .configs import C

_FIX = {}
def fixture(name):
    """Build fixture and pre-compute deterministic detection profiles of every (fault, target)."""
    if name not in _FIX:
        L = aeb_fixture() if name == "aeb" else steer_fixture()
        prof = {}
        for n in NAMES:
            prof[n] = [(t, pk, profile(L, n, t, pk)) for t in targets(L, n) for pk in (0, 1)]
        asil = "D" if name == "steer" else "B"
        author = sum(AUTHOR_MIN[a.type] for a in L.a.values())
        review = sum(REVIEW_MIN[a.type] for a in L.a.values())
        _FIX[name] = dict(L=L, prof=prof, n=len(L.a), asil=asil, author=author, review=review)
    return _FIX[name]


def run_one(cfg_name, seed, fx="aeb", P=None, return_detail=False):
    P = dict(BASE, **(P or {}))
    c = C[cfg_name]; F = fixture(fx)
    rng = np.random.default_rng(seed)          # paired: same seed -> same RNG stream for every config
    asil_d = F["asil"] == "D"
    k_retry = P["k_retry_asil_d"] if asil_d else P["k_retry"]

    # ---------------- injection ----------------
    if c["inject"] == "manual":
        p = P["p_manual"]
    elif c["inject"] == "human":
        p = P["p_human"]
    else:
        p = P["p_llm"]
        if c["dehallucination"]:
            p *= (1 - P["b7_dehallucination"])
    if c["correlated"]:
        share, pd = P["b1_degraded_share"], P["b1_p_degraded"]
        p_lo = max(0.0, (p - share * pd) / (1 - share))
        p = pd if rng.random() < share else p_lo
    order = sorted(range(len(NAMES)), key=lambda i: STAGE[NAMES[i]])
    u_inj = rng.random(len(NAMES)); u_tgt = rng.random(len(NAMES))
    injected = []
    n_up = 0
    for i in order:
        n = NAMES[i]
        pe = min(0.98, p + (P["b2_amplification"] * n_up if c["amplification"] else 0.0))
        if u_inj[i] < pe:
            choices = F["prof"][n]
            t, pk, pr = choices[int(u_tgt[i] * len(choices))]
            injected.append((n, t, pr))
            n_up += 1

    # first-pass TC (measured by the evaluator's ledger on every configuration)
    aff = set()
    for n, t, pr in injected:
        aff |= pr["affected"]
    tc_first = 1 - len(aff) / F["n"]

    # ---------------- detection / rework ----------------
    far = P["critic_far"] if c["critic"] else 0.0
    fatigue = 1 - P["fatigue_slope"] * far
    def hrec(cat, kind):
        if kind == "b0":
            return {"St": P["h0_st"], "Sm": P["h0_sm"], "LI": P["h0_li"]}[cat]
        base = {"St": P["h_st"], "Sm": P["h_sm"], "LI": P["h_li"]}[cat] * fatigue
        if kind == "self":
            return base * P["self_review_factor"]
        return base
    retries = {"invariant": 0, "critic": 0, "test": 0, "human": 0, "llm_review": 0, "release": 0, "self": 0}
    escal = 0; advisories = 0; crit_tp = 0
    escapes = []; caught_by = {}
    fix_p = P["p_fix_human"] if c["author"] == "human" else P["p_fix_llm"]

    for n, t, pr in injected:
        cat = CAT[n]
        layers = []   # (name, detect_prob, blocking)
        if c["self_review"]:
            layers.append(("self", P["b1_self_review"], True))
        if c["ledger"] == "blocking":
            layers.append(("invariant", 1.0 if pr["inv"] else 0.0, True))
        elif c["ledger"] == "alm":
            layers.append(("invariant", 1.0 if pr["alm"] else 0.0, True))
        elif c["ledger"] == "advisory":
            layers.append(("advisory", 1.0 if pr["inv"] else 0.0, False))
        if c["critic"]:
            layers.append(("critic", P["critic_recall"], True))
        if c["llm_reviewer"] and STAGE[n] >= 3:
            layers.append(("llm_review", P["llm_reviewer_recall"] * (1 - P["llm_reviewer_corr"] * 0.5), True))
        tp = TEST_P[n] * P["test_scale"]
        if c["tests"] == "exec_feedback":
            tp *= P["exec_feedback_factor"]
        elif c["tests"] == "same_agent":
            tp *= P["same_agent_test_factor"]
        if tp > 0:
            layers.append(("test", min(1.0, tp), True))
        if c["human"] in ("dp", "b0", "self"):
            kind = c["human"]
            if kind == "dp" and not c["policy"] and rng.random() < P["p_self_approval"]:
                kind = "self"
            layers.append(("human", hrec(cat, kind), True))
            if asil_d and c["policy"] and c["human"] == "dp":
                layers.append(("human2", P["asil_d_second_review"], True))
        if c["release_review"]:
            layers.append(("release", {"St": P["release_st"], "Sm": P["release_sm"], "LI": P["release_li"]}[cat], True))

        escaped = True
        crit_miss_corr = c["critic"] and rng.random() < P["corr"]   # shared blind spot with generator
        for name, dp, blocking in layers:
            if name == "critic" and crit_miss_corr:
                continue
            if rng.random() < dp:
                if not blocking:
                    advisories += 1
                    continue
                # rework loop: bounded retry budget then escalation to a human author
                key = "human" if name == "human2" else name
                if name == "critic":
                    crit_tp += 1
                fixed = False
                for _ in range(k_retry):
                    retries[key] += 1
                    if rng.random() < fix_p:
                        fixed = True; break
                if not fixed:
                    escal += 1
                escaped = False
                caught_by[name] = caught_by.get(name, 0) + 1
                break
        if escaped:
            escapes.append((n, t, pr))

    # ---------------- release state ----------------
    aff_final = set()
    for n, t, pr in escapes:
        aff_final |= pr["affected"]
    tc_final = 1 - len(aff_final) / F["n"]
    esc_cat = {"St": 0, "Sm": 0, "LI": 0}
    for n, t, pr in escapes:
        esc_cat[CAT[n]] += 1
    audit_found = 0
    if c["audit"]:
        audit_found = int(sum(rng.random() < P["audit_recall"] for _ in escapes))

    # ---------------- effort ----------------
    E = EFFORT
    review = F["review"] * (E["asil_d_review_factor"] if asil_d else 1.0)
    author = F["author"] if c["author"] == "human" else F["author"] * E["llm_draft_factor"]
    if c["human"] == "b0":
        rev = review * E["b0_review_factor"]
    elif c["human"] == "dp":
        rev = review * (2.0 if (asil_d and c["policy"]) else 1.0)
    elif c["human"] == "self":
        rev = review * E["self_review_share"]
    else:
        rev = 0.0
    if c["release_review"]:
        rev += review * E["release_review_share"]
    n_retry = sum(retries.values())
    rework = n_retry * (review / F["n"]) * E["rework_review_share"] * 2 \
        + (n_retry * (F["author"] / F["n"]) * (1.0 if c["author"] == "human" else E["llm_draft_factor"]))
    disp = 0.0
    if c["critic"]:
        disp = (crit_tp + far * F["n"]) * E["disposition_min"]
    adv = advisories * E["advisory_triage_min"] if c["ledger"] == "advisory" else 0.0
    aud = review * E["audit_share"] if c["audit"] else 0.0
    minutes = author + rev + rework + disp + adv + aud + escal * E["escalation_min"]

    # coverage stub (assumption-determined; see ASSUMPTIONS_R1.md)
    target = 1.0 if asil_d else 0.80
    if c["coverage_loop"]:
        cov = min(1.0, target + (0.0 if asil_d else rng.uniform(0.10, 0.16)))
    else:
        cov = rng.uniform(0.70, 0.80) if c["tests"] == "same_agent" else rng.uniform(0.74, 0.86)

    out = dict(cfg=cfg_name, seed=seed, fx=fx, injected=len(injected), escapes=len(escapes),
               st=esc_cat["St"], sm=esc_cat["Sm"], li=esc_cat["LI"], tc_first=tc_first,
               tc_final=tc_final, residual=len(aff_final), minutes=minutes, retries=n_retry,
               escalations=escal, advisories=advisories, audit_found=audit_found,
               field_escapes=len(escapes) - audit_found, coverage=cov,
               **{f"r_{k}": v for k, v in retries.items()},
               **{f"c_{k}": v for k, v in caught_by.items()})
    return out
