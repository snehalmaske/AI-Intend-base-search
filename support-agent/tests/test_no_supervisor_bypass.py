import pytest

from app.agents import RecordsAgent, RefundsAgent
from app.orchestrator import Orchestrator
from app.tools import ToolContext, invoke

from .conftest import ALICE_45, BRUNO_250, balance, case_row


@pytest.fixture
def in_review():
    assert Orchestrator().run(BRUNO_250).final_status == "supervisor_review"
    return BRUNO_250


def test_refunds_agent_cannot_decide_case_in_review(in_review):
    res = RefundsAgent().call("decide_refund", in_review, proposed_decision="approve",
                              reason="customer insists", policy_refs=["RP-1.2"])
    assert not res.ok and res.verdict.rule == "no_supervisor_bypass"
    assert case_row(in_review).status == "supervisor_review"


@pytest.mark.parametrize("status", ["approved", "approved_by_supervisor", "processed", "closed"])
def test_records_agent_cannot_flip_status(in_review, status):
    res = RecordsAgent().call("update_case_status", in_review, status=status)
    assert not res.ok and res.verdict.rule == "no_supervisor_bypass"
    assert case_row(in_review).status == "supervisor_review"


def test_cannot_process_case_in_review(in_review):
    before = balance(2)
    res = RefundsAgent().process(in_review)
    assert not res.ok and res.calls[0].verdict.rule == "no_supervisor_bypass"
    assert balance(2) == before


def test_denied_by_supervisor_is_final(in_review):
    assert invoke("supervisor", "supervisor_decide", ToolContext(case_id=in_review),
                  {"decision": "deny", "reason": "no evidence"}).ok
    assert RefundsAgent().process(in_review).calls[0].verdict.rule == "no_supervisor_bypass"
    res = RecordsAgent().call("update_case_status", in_review, status="approved")
    assert not res.ok and res.verdict.rule == "no_supervisor_bypass"
    assert case_row(in_review).status == "denied_by_supervisor"


def test_agent_cannot_set_decision_status_on_normal_case():
    res = RecordsAgent().call("update_case_status", ALICE_45, status="approved")
    assert not res.ok and res.verdict.rule == "no_supervisor_bypass"


def test_supervisor_approval_is_the_legitimate_path(in_review):
    before = balance(2)
    assert invoke("supervisor", "supervisor_decide", ToolContext(case_id=in_review),
                  {"decision": "approve", "reason": "carrier confirmed loss"}).ok
    run = Orchestrator().run(in_review)
    assert run.final_status == "processed"
    assert balance(2) == before + 250.0
