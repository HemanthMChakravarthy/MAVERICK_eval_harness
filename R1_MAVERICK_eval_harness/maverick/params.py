"""Behavioural parameters (assumption register, machine-readable).

Every number here is a MODELLING ASSUMPTION, not a measurement.  See
ASSUMPTIONS_R1.md for rationale and the ranges used in the global
uncertainty analysis (GUA).
"""
BASE = dict(
    # defect injection (per fault class, per run)
    p_llm=0.75, p_human=0.15, p_manual=0.05,
    b1_degraded_share=0.30, b1_p_degraded=0.95,          # B1 run-level correlation
    b2_amplification=0.15,                               # B2 +p per active upstream defect
    b7_dehallucination=0.20,                             # B7 relative reduction of injection p
    # LLM critic
    critic_recall=0.70, critic_far=0.10, corr=0.0,
    # human review (different person), by category
    h_st=0.90, h_sm=0.85, h_li=0.80,
    h0_st=0.97, h0_sm=0.95, h0_li=0.93,                  # B0 near-perfect review
    fatigue_slope=0.30,
    self_review_factor=0.60,                             # recall multiplier when approver == author/prompter
    p_self_approval=0.20,                                # share of self-approvals when independence is not enforced (M-policy)
    release_st=0.45, release_sm=0.40, release_li=0.30,   # single end-of-pipeline human release review
    # LLM self-review / LLM reviewer roles
    b1_self_review=0.25,
    llm_reviewer_recall=0.40, llm_reviewer_corr=0.50,    # B6/B7 same-family reviewer agent
    # executed tests
    test_scale=1.0,                                      # multiplies catalog test_detect (independent tests)
    exec_feedback_factor=0.8,                            # B6-B8 tests derived in the same context
    same_agent_test_factor=0.3,                          # B1/B2 tests from the producing agent
    # rework
    p_fix_llm=0.85, p_fix_human=0.95, p_fix_escalation=0.95, k_retry=3, k_retry_asil_d=5,
    # ASIL-D policy rigor: second independent inspection layer
    asil_d_second_review=0.50,
    # post-hoc audit (B5)
    audit_recall=0.85,
)

# effort model (minutes); authoring base per artifact type, review per artifact type
AUTHOR_MIN = dict(SysReq=0, SwReq=90, SwArch=240, SwDesign=180, SwUnit=360, UnitTest=90,
                  CompTest=90, IntTest=90, QualTest=90, Result=15)
REVIEW_MIN = dict(SysReq=0, SwReq=20, SwArch=45, SwDesign=30, SwUnit=60, UnitTest=15,
                  CompTest=15, IntTest=15, QualTest=15, Result=5)
EFFORT = dict(llm_draft_factor=0.05, b0_review_factor=2.5, asil_d_review_factor=1.5,
              rework_review_share=0.5, escalation_min=240, disposition_min=10,
              advisory_triage_min=5, audit_share=0.30, release_review_share=0.35,
              self_review_share=0.5)
