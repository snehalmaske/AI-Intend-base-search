"""FastAPI app: REST API + static single-page UI.

Human-operator endpoints (admin/supervisor/controls) are separate from the
agents' tool layer. Agents never call these endpoints and have no tools that
reach them.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func

from . import audit, policy_engine, rag, state
from .agents import AGENT_CLASSES, IntakeAgent
from .config import BASE_DIR, settings
from .db import (
    AuditLog,
    Case,
    Customer,
    Email,
    PolicyDocument,
    Refund,
    ReportEntry,
    init_db,
    mask_account,
    session_scope,
    utcnow,
)
from .llm import get_llm
from .orchestrator import STEP_AGENT, STEPS, Orchestrator, next_step_for
from .permissions import TOOL_CATALOG, TOOL_GRANTS
from .tools import ToolContext, case_dict, invoke

STATIC_DIR = BASE_DIR / "static"

@asynccontextmanager
async def _lifespan(_: FastAPI):
    init_db()
    rag.reindex_all()  # SQLite is the source of truth; rebuild the index from it
    yield


app = FastAPI(title="Enterprise Customer Support Agent (synthetic)", version="1.0", lifespan=_lifespan)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class PolicyUpload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class NewCase(BaseModel):
    customer_id: int
    description: str = Field(min_length=1, max_length=4000)
    amount_requested: float = Field(gt=0)


class SupervisorDecision(BaseModel):
    decision: Literal["approve", "deny"]
    reason: str = Field(min_length=1, max_length=2000)


class InboundEmail(BaseModel):
    case_id: int
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=10000)


class AgentAct(BaseModel):
    case_id: int | None = None
    instruction: str = ""
    tool: str | None = None
    params: dict[str, Any] | None = None


class RevocationToggle(BaseModel):
    revoked: bool
    reason: str = ""


# --------------------------------------------------------------------------
# System
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "llm": get_llm().name,
        "model": settings.claude_model if not settings.mock_llm else None,
        "rag_backend": rag.get_store().backend,
        "revocation": state.revocation_state(),
        **policy_engine.guardrail_status(),
        "agents": {a: sorted(t) for a, t in TOOL_GRANTS.items()},
        "tools": {n: {"description": t.description, "consequential": t.consequential,
                      "params": t.json_schema()} for n, t in TOOL_CATALOG.items()},
        "steps": [{"step": s, "agent": STEP_AGENT[s]} for s in STEPS],
    }


@app.get("/api/controls/revocation")
def get_revocation() -> dict[str, Any]:
    return {"revocation": state.revocation_state()}


@app.post("/api/controls/revocation")
def toggle_revocation(body: RevocationToggle) -> dict[str, Any]:
    return {"revocation": state.set_revocation(body.revoked, actor="operator", reason=body.reason)}


# --------------------------------------------------------------------------
# Policies (admin)
# --------------------------------------------------------------------------

@app.post("/api/policies")
def upload_policy(body: PolicyUpload) -> dict[str, Any]:
    res = invoke("admin", "upload_policy", params=body.model_dump())
    if not res.ok:
        raise HTTPException(403, res.as_dict())
    return res.as_dict()


@app.get("/api/policies")
def list_policies() -> list[dict[str, Any]]:
    with session_scope() as s:
        return [{"id": d.id, "name": d.name, "uploaded_by": d.uploaded_by,
                 "uploaded_at": d.uploaded_at.isoformat(), "content": d.content}
                for d in s.query(PolicyDocument).order_by(PolicyDocument.id)]


@app.get("/api/policies/chunks")
def policy_chunks() -> list[dict[str, Any]]:
    return sorted(rag.get_store().list("policies"), key=lambda d: d["id"])


@app.get("/api/policies/search")
def policy_search(q: str, k: int = Query(4, ge=1, le=10)) -> list[dict[str, Any]]:
    return rag.get_store().query("policies", q, k=k)


# --------------------------------------------------------------------------
# Customers (operator view; bank accounts always masked)
# --------------------------------------------------------------------------

def _customer_view(s, c: Customer) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "email": c.email, "bank_account": mask_account(c.bank_account),
            "balance": round(c.balance, 2), "notes": c.notes,
            "weekly_approved_total": round(policy_engine.weekly_approved_total(s, c.id), 2)}


@app.get("/api/customers")
def customers() -> list[dict[str, Any]]:
    with session_scope() as s:
        return [_customer_view(s, c) for c in s.query(Customer).order_by(Customer.id)]


@app.get("/api/customers/{customer_id}")
def customer(customer_id: int) -> dict[str, Any]:
    with session_scope() as s:
        c = s.get(Customer, customer_id)
        if c is None:
            raise HTTPException(404, "customer not found")
        out = _customer_view(s, c)
        out["cases"] = [case_dict(k) for k in s.query(Case).filter(Case.customer_id == c.id)]
        return out


# --------------------------------------------------------------------------
# Cases + workflow
# --------------------------------------------------------------------------

def _case_detail(s, case: Case) -> dict[str, Any]:
    out = case_dict(case)
    cust = s.get(Customer, case.customer_id)
    out["customer_name"] = cust.name if cust else None
    out["next_step"] = next_step_for(case)
    refund = s.query(Refund).filter(Refund.case_id == case.id).first()
    out["refund"] = None if refund is None else {
        "id": refund.id, "amount": refund.amount, "decision": refund.decision, "reason": refund.reason,
        "policy_refs": refund.policy_ref_list, "decided_by": refund.decided_by,
        "processed": refund.processed,
    }
    return out


@app.post("/api/cases")
def create_case(body: NewCase) -> dict[str, Any]:
    res = IntakeAgent().submit(body.customer_id, body.description, body.amount_requested)
    if not res.ok:
        raise HTTPException(403 if res.halted else 400, res.as_dict())
    return res.as_dict()


@app.get("/api/cases")
def list_cases(status: str | None = None) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = s.query(Case)
        if status:
            q = q.filter(Case.status == status)
        return [_case_detail(s, c) for c in q.order_by(Case.id.desc())]


@app.get("/api/cases/{case_id}")
def get_case(case_id: int) -> dict[str, Any]:
    with session_scope() as s:
        case = s.get(Case, case_id)
        if case is None:
            raise HTTPException(404, "case not found")
        out = _case_detail(s, case)
        out["emails"] = [{"id": e.id, "direction": e.direction, "address": e.address, "subject": e.subject,
                          "body": e.body, "created_at": e.created_at.isoformat()}
                         for e in s.query(Email).filter(Email.case_id == case_id).order_by(Email.id)]
    out["audit"] = audit.query(target=f"case:{case_id}", limit=500)[::-1]
    return out


@app.post("/api/cases/{case_id}/steps/{step}")
def run_step(case_id: int, step: str) -> dict[str, Any]:
    if step not in STEPS:
        raise HTTPException(400, f"unknown step; one of {list(STEPS)}")
    _require_case(case_id)
    return Orchestrator().run_step(case_id, step).as_dict()


@app.post("/api/cases/{case_id}/run")
def run_workflow(case_id: int) -> dict[str, Any]:
    _require_case(case_id)
    return Orchestrator().run(case_id).as_dict()


@app.post("/api/cases/{case_id}/supervisor")
def supervisor_decision(case_id: int, body: SupervisorDecision) -> dict[str, Any]:
    _require_case(case_id)
    res = invoke("supervisor", "supervisor_decide", ToolContext(case_id=case_id), body.model_dump())
    if not res.ok:
        raise HTTPException(403, res.as_dict())
    return res.as_dict()


@app.post("/api/agents/{agent}/act")
def agent_act(agent: str, body: AgentAct) -> dict[str, Any]:
    """Free-form request to one agent. The model (or the caller, via ``tool``)
    proposes a single tool call; the policy engine decides."""
    cls = AGENT_CLASSES.get(agent)
    if cls is None:
        raise HTTPException(404, f"unknown agent; one of {sorted(AGENT_CLASSES)}")
    return cls().act(body.case_id, body.instruction, body.tool, body.params).as_dict()


def _require_case(case_id: int) -> None:
    with session_scope() as s:
        if s.get(Case, case_id) is None:
            raise HTTPException(404, "case not found")


# --------------------------------------------------------------------------
# Email (mock inbox / outbox)
# --------------------------------------------------------------------------

@app.post("/api/emails/inbound")
def inbound_email(body: InboundEmail) -> dict[str, Any]:
    """Simulates a customer reply arriving in the mock inbox."""
    with session_scope() as s:
        case = s.get(Case, body.case_id)
        if case is None:
            raise HTTPException(404, "case not found")
        cust = s.get(Customer, case.customer_id)
        email = Email(case_id=case.id, direction="in", address=cust.email, subject=body.subject, body=body.body)
        s.add(email)
        s.flush()
        return {"id": email.id}


@app.get("/api/emails")
def list_emails(direction: Literal["in", "out"] | None = None) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = s.query(Email)
        if direction:
            q = q.filter(Email.direction == direction)
        return [{"id": e.id, "case_id": e.case_id, "direction": e.direction, "address": e.address,
                 "subject": e.subject, "body": e.body, "created_at": e.created_at.isoformat()}
                for e in q.order_by(Email.id.desc())]


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

@app.get("/api/reports/summary")
def report_summary() -> dict[str, Any]:
    with session_scope() as s:
        by_decision = dict(s.query(Refund.decision, func.count()).group_by(Refund.decision).all())
        approved_amount = s.query(func.coalesce(func.sum(Refund.amount), 0.0)) \
            .filter(Refund.decision == "approved").scalar()
        issued_amount = s.query(func.coalesce(func.sum(Refund.amount), 0.0)) \
            .filter(Refund.processed.is_(True)).scalar()
        by_status = dict(s.query(Case.status, func.count()).group_by(Case.status).all())
        entries = [{"id": r.id, "case_id": r.case_id, "customer_id": r.customer_id, "outcome": r.outcome,
                    "amount": r.amount, "reason": r.reason, "created_at": r.created_at.isoformat()}
                   for r in s.query(ReportEntry).order_by(ReportEntry.id.desc())]
        reasons: dict[str, int] = {}
        for r in s.query(Refund).filter(Refund.decision == "denied"):
            if r.reason.startswith("Policy engine"):
                key = "policy engine override"
            else:
                key = "supervisor denial" if r.decided_by == "supervisor" else "agent denial (policy grounds)"
            reasons[key] = reasons.get(key, 0) + 1
        return {"refunds_by_decision": by_decision, "approved_amount": round(approved_amount, 2),
                "issued_amount": round(issued_amount, 2), "cases_by_status": by_status,
                "denial_reasons": reasons, "entries": entries}


@app.get("/api/reports/weekly")
def report_weekly(weeks: int = Query(4, ge=1, le=52)) -> dict[str, Any]:
    """Per customer: rolling 7-day approved total + approved totals per ISO week."""
    since = utcnow() - timedelta(weeks=weeks)
    with session_scope() as s:
        rows = []
        for c in s.query(Customer).order_by(Customer.id):
            per_week: dict[str, float] = {}
            for r in s.query(Refund).filter(Refund.customer_id == c.id, Refund.decision == "approved",
                                            Refund.created_at >= since):
                y, w, _ = r.created_at.isocalendar()
                key = f"{y}-W{w:02d}"
                per_week[key] = round(per_week.get(key, 0.0) + r.amount, 2)
            rolling = policy_engine.weekly_approved_total(s, c.id)
            rows.append({"customer_id": c.id, "name": c.name, "rolling_7d_total": round(rolling, 2),
                         "cap": settings.weekly_refund_cap,
                         "headroom": round(max(0.0, settings.weekly_refund_cap - rolling), 2),
                         "by_iso_week": per_week})
        return {"weeks": weeks, "customers": rows}


# --------------------------------------------------------------------------
# Audit / evidence
# --------------------------------------------------------------------------

def _audit_query(actor, action, decision, rule, target, q, limit):
    return audit.query(actor=actor, action=action, decision=decision, rule=rule, target=target, q=q,
                       limit=limit)


@app.get("/api/audit")
@app.get("/audit", include_in_schema=False)
def get_audit(actor: str | None = None, action: str | None = None, decision: str | None = None,
              rule: str | None = None, target: str | None = None, q: str | None = None,
              limit: int = Query(500, ge=1, le=10000)) -> list[dict[str, Any]]:
    return _audit_query(actor, action, decision, rule, target, q, limit)


@app.get("/api/audit/export")
def export_audit(format: Literal["csv", "json"] = "csv", actor: str | None = None,
                 action: str | None = None, decision: str | None = None, rule: str | None = None,
                 target: str | None = None, q: str | None = None) -> Response:
    rows = _audit_query(actor, action, decision, rule, target, q, 10000)[::-1]
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    if format == "json":
        payload = {"exported_at": stamp, "chain": audit.verify_chain(), "rows": rows}
        return Response(json.dumps(payload, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename=audit_{stamp}.json"})
    return PlainTextResponse(audit.export_csv(rows), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=audit_{stamp}.csv"})


@app.get("/api/audit/verify")
def verify_audit() -> dict[str, Any]:
    return audit.verify_chain()


@app.get("/api/audit/stats")
def audit_stats() -> dict[str, Any]:
    with session_scope() as s:
        by_rule = dict(s.query(AuditLog.rule, func.count()).filter(AuditLog.decision != "allow")
                       .group_by(AuditLog.rule).all())
        by_decision = dict(s.query(AuditLog.decision, func.count()).group_by(AuditLog.decision).all())
    return {"by_decision": by_decision, "refusals_by_rule": by_rule}


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
