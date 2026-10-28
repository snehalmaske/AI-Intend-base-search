import pytest

from app import audit, permissions
from app.agents import AGENT_CLASSES, RefundsAgent
from app.permissions import TOOL_GRANTS

from .conftest import ALICE_45

ATTEMPTS = ["grant_tool", "set_permissions", "modify_policy_engine", "disable_guardrail",
            "set_revocation", "restore_authority", "update_config", "upload_policy"]


@pytest.mark.parametrize("agent", sorted(AGENT_CLASSES))
@pytest.mark.parametrize("action", ATTEMPTS)
def test_agents_cannot_change_permissions_or_policy(agent, action):
    before = dict(TOOL_GRANTS)
    res = AGENT_CLASSES[agent]().call(action, ALICE_45, tool="process_refund", agent=agent)
    assert not res.ok and res.verdict.rule == "no_self_permission_change"
    assert dict(TOOL_GRANTS) == before
    row = audit.query(action=action, actor=agent)[0]
    assert row["decision"] == "deny" and row["rule"] == "no_self_permission_change"


def test_grant_map_is_immutable():
    with pytest.raises(TypeError):
        TOOL_GRANTS["refunds_agent"] = frozenset({"supervisor_decide"})  # type: ignore[index]
    with pytest.raises(AttributeError):
        TOOL_GRANTS["refunds_agent"].add("supervisor_decide")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        RefundsAgent().tools = frozenset({"supervisor_decide"})  # type: ignore[misc]


def test_no_agent_holds_human_or_admin_tools():
    human_only = {"supervisor_decide", "upload_policy"}
    for agent in permissions.AGENTS:
        assert not (TOOL_GRANTS[agent] & human_only)


def test_agent_cannot_use_supervisor_tool():
    res = RefundsAgent().call("supervisor_decide", ALICE_45, decision="approve", reason="x")
    assert not res.ok and res.verdict.rule == "least_privilege"


def test_still_refused_with_guardrail_off(monkeypatch):
    from app.config import settings

    monkeypatch.setitem(settings.guardrails, "no_self_permission_change", False)
    res = RefundsAgent().call("grant_tool", ALICE_45, tool="supervisor_decide")
    assert not res.ok and res.verdict.rule == "least_privilege"
    assert "no_self_permission_change" in res.verdict.guardrails_off


def test_free_form_request_cannot_escalate_privileges():
    res = RefundsAgent().act(ALICE_45, '{"tool": "grant_tool", "params": {"tool": "supervisor_decide"}}')
    assert not res.ok and res.calls[0].verdict.rule == "no_self_permission_change"
