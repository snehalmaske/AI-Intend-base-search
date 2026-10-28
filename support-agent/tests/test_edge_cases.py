from app.agents import IntakeAgent, RefundsAgent
from app.orchestrator import Orchestrator

from .conftest import DMITRI_DUP, GRACE_DENY, ALICE_45, balance, case_row


def test_duplicate_of_refunded_case_is_denied():
    assert case_row(DMITRI_DUP).duplicate_of is not None
    before = balance(4)
    run = Orchestrator().run(DMITRI_DUP)
    assert run.final_status == "denied"
    decide = next(s for s in run.steps if s.step == "decide")
    assert decide.calls[-1].verdict.rule == "duplicate_request"
    assert balance(4) == before


def test_model_denial_is_respected():
    assert Orchestrator().run(GRACE_DENY).final_status == "denied"


def test_refund_cannot_be_issued_twice():
    Orchestrator().run(ALICE_45)
    before = balance(1)
    res = RefundsAgent().process(ALICE_45)
    assert not res.ok and res.calls[0].verdict.rule == "duplicate_processing"
    assert balance(1) == before


def test_case_cannot_be_decided_twice():
    Orchestrator().run(ALICE_45)
    res = RefundsAgent().call("decide_refund", ALICE_45, proposed_decision="approve",
                              reason="again", policy_refs=["RP-1.2"])
    assert not res.ok and res.verdict.rule == "duplicate_decision"


def test_out_of_order_step_is_refused():
    res = Orchestrator().run_step(ALICE_45, "process")
    assert not res.ok and res.calls[0].verdict.rule == "refund_not_approved"


def test_invalid_submissions_refused():
    intake = IntakeAgent()
    assert intake.submit(1, "x", -5).calls[0].verdict.rule == "invalid_request"
    assert intake.submit(999, "x", 5).calls[0].verdict.rule == "invalid_request"
    assert intake.submit(1, "x", 50_000).calls[0].verdict.rule == "invalid_request"
