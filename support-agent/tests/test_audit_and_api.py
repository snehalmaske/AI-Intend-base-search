import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import audit
from app.api import app
from app.config import settings
from app.db import get_engine
from app.orchestrator import Orchestrator

from .conftest import ALICE_45, BRUNO_250, case_row


def test_audit_log_is_append_only():
    Orchestrator().run(ALICE_45)
    with get_engine().begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(text("UPDATE audit_log SET decision='allow' WHERE id=1"))
    with get_engine().begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(text("DELETE FROM audit_log"))
    assert audit.verify_chain()["ok"]


def test_hash_chain_detects_tampering():
    Orchestrator().run(ALICE_45)
    path = settings.database_url.replace("sqlite:///", "", 1)
    conn = sqlite3.connect(path)
    conn.execute("DROP TRIGGER audit_log_no_update")
    conn.execute("UPDATE audit_log SET reason='nothing to see here' WHERE id=5")
    conn.commit()
    conn.close()
    result = audit.verify_chain()
    assert not result["ok"] and result["first_bad_id"] == 5


def test_every_step_is_logged_with_required_fields():
    Orchestrator().run(ALICE_45)
    rows = audit.query(target=f"case:{ALICE_45}")
    actions = {r["action"] for r in rows}
    assert {"assign_case", "update_case_status", "send_email", "decide_refund", "process_refund",
            "record_report_entry"} <= actions
    for r in rows:
        assert r["actor_agent"] and r["inputs_hash"] and r["rule"] and r["revocation_state"]
    decide = next(r for r in rows if r["action"] == "decide_refund")
    assert decide["policy_refs"], "decision must cite policy chunks"


def test_approval_without_policy_citation_refused():
    from app.agents import RefundsAgent
    from .conftest import advance_to

    advance_to(ALICE_45, "acknowledged")
    for refs in ([], ["RP-9.9-made-up"]):
        res = RefundsAgent().call("decide_refund", ALICE_45, proposed_decision="approve",
                                  reason="ok", policy_refs=refs)
        assert not res.ok and res.verdict.rule == "policy_citation_required"


def test_guardrail_off_is_visible_in_audit(monkeypatch):
    monkeypatch.setitem(settings.guardrails, "single_transaction_cap", False)
    assert Orchestrator().run(BRUNO_250).final_status == "processed"
    row = audit.query(action="decide_refund", target=f"case:{BRUNO_250}")[0]
    assert row["decision"] == "allow" and "single_transaction_cap" in row["guardrails_off"]


def test_api_end_to_end():
    with TestClient(app) as client:
        cfg = client.get("/api/config").json()
        assert cfg["llm"] == "mock" and all(cfg["guardrails"].values())
        created = client.post("/api/cases", json={"customer_id": 7, "description": "Kettle leaks", "amount_requested": 20})
        cid = created.json()["data"]["case_id"]
        run = client.post(f"/api/cases/{cid}/run").json()
        assert run["final_status"] == "processed"
        detail = client.get(f"/api/cases/{cid}").json()
        assert detail["refund"]["processed"] and len(detail["emails"]) == 2
        assert client.get("/audit", params={"target": f"case:{cid}"}).json()
        csv = client.get("/api/audit/export", params={"format": "csv"})
        assert csv.status_code == 200 and csv.text.startswith("id,ts,actor_agent")
        assert client.get("/api/audit/export", params={"format": "json"}).json()["chain"]["ok"]
        assert client.get("/api/reports/summary").json()["refunds_by_decision"]["approved"] >= 1
        assert client.get("/api/reports/weekly").json()["customers"]
        assert client.post("/api/controls/revocation", json={"revoked": True}).json()["revocation"] == "revoked"
        refused = client.post("/api/cases", json={"customer_id": 7, "description": "x", "amount_requested": 5})
        assert refused.status_code == 403
        client.post("/api/controls/revocation", json={"revoked": False})
        act = client.post("/api/agents/records_agent/act",
                          json={"case_id": cid, "tool": "get_customer_profile", "params": {"customer_id": 1}}).json()
        assert not act["ok"] and act["calls"][0]["verdict"]["rule"] == "no_unrelated_record_export"
        assert client.get("/").status_code == 200
