from app import audit
from app.agents import RefundsAgent
from app.db import Refund, session_scope
from app.orchestrator import Orchestrator

from .conftest import ALICE_45, BRUNO_250, ESTHER_100, FARID_10001, balance, case_row


def test_under_cap_is_auto_approved_and_issued():
    before = balance(1)
    run = Orchestrator().run(ALICE_45)
    assert run.final_status == "processed"
    assert balance(1) == before + 45.00


def test_over_cap_routes_to_supervisor_never_auto_approved():
    before = balance(2)
    run = Orchestrator().run(BRUNO_250)
    assert run.final_status == "supervisor_review"
    decide = next(s for s in run.steps if s.step == "decide")
    assert decide.data["proposal"]["decision"] == "approve"  # the model wanted to approve
    with session_scope() as s:
        assert s.query(Refund).filter(Refund.case_id == BRUNO_250).count() == 0
    assert balance(2) == before
    rows = audit.query(action="decide_refund", target=f"case:{BRUNO_250}")
    assert rows[0]["decision"] == "escalate" and rows[0]["rule"] == "single_transaction_cap"
    assert "RP-2.1" in rows[0]["policy_refs"]


def test_boundary_exactly_cap_allowed_one_cent_over_escalates():
    assert Orchestrator().run(ESTHER_100).final_status == "processed"
    assert Orchestrator().run(FARID_10001).final_status == "supervisor_review"


def test_process_rechecks_cap_even_if_ledger_was_tampered():
    """Defence in depth: an agent-approved refund > cap (e.g. inserted by a
    compromised component) is still not issued."""
    from .conftest import advance_to

    advance_to(BRUNO_250, "acknowledged")
    with session_scope() as s:
        case = s.get(type(case_row(BRUNO_250)), BRUNO_250)
        case.status = "approved"
        s.add(Refund(case_id=BRUNO_250, customer_id=2, amount=250.0, decision="approved",
                     reason="tampered", policy_refs="[]", decided_by="refunds_agent"))
    before = balance(2)
    res = RefundsAgent().process(BRUNO_250)
    assert not res.ok
    assert res.calls[0].verdict.rule == "single_transaction_cap"
    assert balance(2) == before
