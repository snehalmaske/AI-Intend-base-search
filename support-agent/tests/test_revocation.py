import pytest

from app import audit, state
from app.agents import EmailAgent, IntakeAgent, RecordsAgent, RefundsAgent, ReportingAgent
from app.db import Refund, session_scope
from app.orchestrator import Orchestrator
from app.tools import invoke

from .conftest import ALICE_45, advance_to, balance, case_row


@pytest.fixture
def revoked():
    state.set_revocation(True, actor="operator", reason="test")
    yield
    state.set_revocation(False, actor="operator", reason="test done")


def test_consequential_actions_refused(revoked):
    calls = [
        EmailAgent().call("send_email", ALICE_45, subject="s", body="b"),
        RecordsAgent().call("update_case_status", ALICE_45, status="validated"),
        RecordsAgent().call("store_customer_note", ALICE_45, note="n"),
        RefundsAgent().call("decide_refund", ALICE_45, proposed_decision="deny", reason="r"),
        RefundsAgent().call("process_refund", ALICE_45),
        ReportingAgent().call("record_report_entry", ALICE_45),
        IntakeAgent().submit(1, "new request", 10.0).calls[0],
        invoke("admin", "upload_policy", params={"name": "x", "content": "y"}),
    ]
    for res in calls:
        assert not res.ok and res.verdict.rule == "revocation", res.tool
    assert case_row(ALICE_45).status == "new"


def test_read_only_actions_continue(revoked):
    assert RecordsAgent().call("get_case", ALICE_45).ok
    assert RecordsAgent().call("get_customer_profile", ALICE_45).ok
    assert RefundsAgent().call("retrieve_policy", query="refund cap").ok
    assert EmailAgent().call("receive_emails", ALICE_45).ok


def test_in_flight_workflow_halts_at_moment_of_action(env):
    """Revocation flipped while the model is deliberating: the decision that
    follows is refused even though the workflow started while authorised."""
    def flip(method):
        if method == "propose_refund_decision":
            state.set_revocation(True, actor="operator", reason="mid-flight")

    env.hooks.append(flip)
    run = Orchestrator().run(ALICE_45)
    assert run.halted
    assert [s.step for s in run.steps] == ["intake", "validate", "acknowledge", "decide"]
    assert run.steps[-1].calls[-1].verdict.rule == "revocation"
    assert case_row(ALICE_45).status == "acknowledged"
    with session_scope() as s:
        assert s.query(Refund).filter(Refund.case_id == ALICE_45).count() == 0
    row = audit.query(action="decide_refund", target=f"case:{ALICE_45}")[0]
    assert row["revocation_state"] == "revoked" and row["decision"] == "deny"

    env.hooks.clear()
    state.set_revocation(False, actor="operator", reason="restore")
    assert Orchestrator().run(ALICE_45).final_status == "processed"


def test_balance_update_refused_after_approval(env):
    advance_to(ALICE_45, "approved")
    before = balance(1)
    state.set_revocation(True, actor="operator")
    res = RefundsAgent().process(ALICE_45)
    assert not res.ok and res.halted
    assert balance(1) == before
    state.set_revocation(False, actor="operator")


def test_toggle_is_audited():
    state.set_revocation(True, actor="operator", reason="drill")
    state.set_revocation(False, actor="operator", reason="drill over")
    actions = [r["action"] for r in audit.query(target="system:revocation")]
    assert actions[:2] == ["restore_authority", "revoke_authority"]
