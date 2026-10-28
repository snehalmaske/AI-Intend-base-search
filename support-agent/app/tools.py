"""The tool layer: the one choke point every agent action goes through.

``invoke(actor, tool, ctx, params)``:
  1. binds the case/customer from the database (never from the caller/LLM),
  2. asks the policy engine for a verdict *at the moment of action*, holding
     a process-wide lock and the same DB session the write will use (so the
     revocation flag and weekly totals cannot change between check and write),
  3. executes the implementation only if allowed (or runs the engine's
     safe fallback route, e.g. "send to supervisor review"),
  4. commits, then appends one audit row.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from . import audit, rag, state
from .config import settings
from .db import (
    Case,
    Customer,
    Email,
    PolicyDocument,
    Refund,
    ReportEntry,
    mask_account,
    session_scope,
    utcnow,
)
from .policy_engine import ActionRequest, Verdict, evaluate, weekly_approved_total

_action_lock = threading.RLock()


@dataclass
class ToolContext:
    case_id: int | None = None
    customer_id: int | None = None  # only used for create_case; otherwise derived from the case


@dataclass
class ToolResult:
    actor: str
    tool: str
    ok: bool
    data: Any
    verdict: Verdict
    audit_id: int

    @property
    def halted(self) -> bool:
        return self.verdict.rule == "revocation"

    def as_dict(self) -> dict[str, Any]:
        return {"actor": self.actor, "tool": self.tool, "ok": self.ok, "data": self.data,
                "verdict": self.verdict.as_dict(), "audit_id": self.audit_id}


class ToolError(Exception):
    pass


After = list[Callable[[], None]]
Impl = Callable[[Session, ActionRequest, Verdict, After], Any]


def _case(s: Session, req: ActionRequest) -> Case:
    case = s.get(Case, req.case_id)
    if case is None:
        raise ToolError("case not found")
    return case


def _customer(s: Session, req: ActionRequest) -> Customer:
    cust = s.get(Customer, req.customer_id)
    if cust is None:
        raise ToolError("customer not found")
    return cust


def _reindex_case(case_id: int) -> Callable[[], None]:
    def run() -> None:
        with session_scope() as s:
            case = s.get(Case, case_id)
            if case:
                rag.index_case(case)
    return run


def _reindex_customer(customer_id: int) -> Callable[[], None]:
    def run() -> None:
        with session_scope() as s:
            cust = s.get(Customer, customer_id)
            if cust:
                rag.index_customer(cust)
    return run


def case_dict(case: Case) -> dict[str, Any]:
    return {
        "id": case.id, "customer_id": case.customer_id, "type": case.type,
        "description": case.description, "amount_requested": case.amount_requested,
        "status": case.status, "assigned_agent": case.assigned_agent,
        "duplicate_of": case.duplicate_of, "notified_status": case.notified_status,
        "reported_status": case.reported_status, "created_at": case.created_at.isoformat(),
    }


def profile_dict(c: Customer) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "email": c.email,
            "bank_account": mask_account(c.bank_account), "balance": round(c.balance, 2),
            "notes": c.notes}


# --------------------------------------------------------------------------
# Implementations
# --------------------------------------------------------------------------

_STOPWORDS = frozenset("a an and are for i in is it my of on the this to was with".split())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - _STOPWORDS


def _create_case(s, req, v, after):
    p = req.params
    amount = round(float(p["amount_requested"]), 2)
    duplicate_of = None
    since = utcnow() - timedelta(days=30)
    words = _tokens(p["description"])
    for other in s.query(Case).filter(Case.customer_id == p["customer_id"], Case.created_at >= since):
        other_words = _tokens(other.description)
        overlap = len(words & other_words) / max(1, len(words | other_words))
        if abs(other.amount_requested - amount) < 0.01 and overlap >= 0.75:
            duplicate_of = other.id
            break
    case = Case(customer_id=p["customer_id"], description=p["description"].strip(),
                amount_requested=amount, status="new", duplicate_of=duplicate_of)
    s.add(case)
    s.flush()
    after.append(_reindex_case(case.id))
    return {"case_id": case.id, "status": case.status, "duplicate_of": duplicate_of}


def _assign_case(s, req, v, after):
    case = _case(s, req)
    if case.status != "new":
        raise ToolError(f"case already {case.status}")
    case.assigned_agent = req.params.get("agent", "refunds_agent")
    case.status = "assigned"
    after.append(_reindex_case(case.id))
    return {"case_id": case.id, "status": case.status, "assigned_agent": case.assigned_agent}


def _get_case(s, req, v, after):
    case = _case(s, req)
    out = case_dict(case)
    refund = s.query(Refund).filter(Refund.case_id == case.id).first()
    out["refund"] = None if refund is None else {
        "decision": refund.decision, "reason": refund.reason, "amount": refund.amount,
        "decided_by": refund.decided_by, "processed": refund.processed,
        "policy_refs": refund.policy_ref_list,
    }
    return out


def _get_customer_profile(s, req, v, after):
    return profile_dict(_customer(s, req))


def _search_records(s, req, v, after):
    k = min(int(req.params.get("limit") or 3), settings.max_record_results)
    # The customer filter is applied by the tool, not chosen by the caller.
    hits = rag.get_store().query("records", req.params["query"], k=k,
                                 where={"customer_id": req.customer_id})
    return [h for h in hits if h["metadata"].get("customer_id") == req.customer_id]


def _update_case_status(s, req, v, after):
    case = _case(s, req)
    case.status = req.params["status"]
    after.append(_reindex_case(case.id))
    return {"case_id": case.id, "status": case.status, "note": req.params.get("note", "")}


def _store_customer_note(s, req, v, after):
    cust = _customer(s, req)
    stamp = utcnow().strftime("%Y-%m-%d")
    cust.notes = (cust.notes + "\n" if cust.notes else "") + f"[{stamp} case {req.case_id}] {req.params['note']}"
    after.append(_reindex_customer(cust.id))
    return {"customer_id": cust.id, "notes": cust.notes}


def _get_customer_contact(s, req, v, after):
    c = _customer(s, req)
    return {"name": c.name, "email": c.email}


def _draft_email(s, req, v, after):
    c = _customer(s, req)
    return {"to": c.email, "subject": req.params["subject"], "body": req.params["body"]}


def _send_email(s, req, v, after):
    c = _customer(s, req)
    case = _case(s, req)
    email = Email(case_id=case.id, direction="out", address=c.email,
                  subject=req.params["subject"][:300], body=req.params["body"])
    s.add(email)
    if req.params.get("notify_status") == case.status:
        case.notified_status = case.status
    s.flush()
    return {"email_id": email.id, "to": c.email}


def _receive_emails(s, req, v, after):
    rows = s.query(Email).filter(Email.case_id == req.case_id, Email.direction == "in") \
        .order_by(Email.id).all()
    return [{"id": e.id, "from": e.address, "subject": e.subject, "body": e.body,
             "created_at": e.created_at.isoformat()} for e in rows]


def _retrieve_policy(s, req, v, after):
    k = min(int(req.params.get("k") or 4), 8)
    return rag.get_store().query("policies", req.params["query"], k=k)


def _get_weekly_total(s, req, v, after):
    total = weekly_approved_total(s, req.customer_id)
    return {"customer_id": req.customer_id, "weekly_total": round(total, 2),
            "weekly_cap": settings.weekly_refund_cap}


def _decide_refund(s, req, v, after):
    case = _case(s, req)
    p = req.params
    after.append(_reindex_case(case.id))
    if v.allowed and p["proposed_decision"] == "escalate":
        case.status = "supervisor_review"
        return {"outcome": "supervisor_review", "reason": p["reason"]}
    if not v.allowed and v.route == "supervisor_review":
        case.status = "supervisor_review"
        return {"outcome": "supervisor_review", "reason": v.reason}
    if v.allowed:
        decision = "approved" if p["proposed_decision"] == "approve" else "denied"
        reason, refs = p["reason"], list(p.get("policy_refs") or [])
    elif v.route == "deny":
        decision = "denied"
        reason, refs = f"Policy engine: {v.reason}", v.policy_refs + list(p.get("policy_refs") or [])
    else:  # pragma: no cover - only routed verdicts reach here
        raise ToolError("not allowed")
    refund = Refund(case_id=case.id, customer_id=case.customer_id, amount=case.amount_requested,
                    decision=decision, reason=reason, policy_refs=json.dumps(sorted(set(refs))),
                    decided_by=req.actor)
    s.add(refund)
    case.status = decision
    s.flush()
    return {"outcome": decision, "refund_id": refund.id, "reason": reason, "policy_refs": sorted(set(refs))}


def _process_refund(s, req, v, after):
    case = _case(s, req)
    cust = _customer(s, req)
    refund = s.query(Refund).filter(Refund.case_id == case.id).one()
    refund.processed = True
    refund.processed_at = utcnow()
    before = cust.balance
    cust.balance = round(cust.balance + refund.amount, 2)
    case.status = "processed"
    state.set_weekly_counter(s, cust.id, weekly_approved_total(s, cust.id))
    after.extend([_reindex_case(case.id), _reindex_customer(cust.id)])
    return {"refund_id": refund.id, "amount": refund.amount,
            "balance_before": before, "balance_after": cust.balance}


def _record_report_entry(s, req, v, after):
    case = _case(s, req)
    if case.reported_status == case.status:
        return {"case_id": case.id, "outcome": case.status, "note": "already recorded"}
    refund = s.query(Refund).filter(Refund.case_id == case.id).first()
    outcome = case.status if case.status != "processed" else "approved"
    reason = refund.reason if refund else "Awaiting human supervisor review"
    entry = ReportEntry(case_id=case.id, customer_id=case.customer_id,
                        refund_id=refund.id if refund else None, outcome=outcome,
                        amount=case.amount_requested, reason=reason)
    s.add(entry)
    case.reported_status = case.status
    s.flush()
    return {"report_entry_id": entry.id, "case_id": case.id, "outcome": outcome, "reason": reason}


def _get_refund_report(s, req, v, after):
    rows = s.query(ReportEntry).filter(ReportEntry.customer_id == req.customer_id).all()
    return {"customer_id": req.customer_id,
            "weekly_total": round(weekly_approved_total(s, req.customer_id), 2),
            "entries": [{"case_id": r.case_id, "outcome": r.outcome, "amount": r.amount,
                         "reason": r.reason} for r in rows]}


def _supervisor_decide(s, req, v, after):
    case = _case(s, req)
    approve = req.params["decision"] == "approve"
    refund = Refund(case_id=case.id, customer_id=case.customer_id, amount=case.amount_requested,
                    decision="approved" if approve else "denied",
                    reason=f"Supervisor: {req.params['reason']}",
                    policy_refs=json.dumps(["RP-2.1", "RP-3.3"]), decided_by="supervisor")
    s.add(refund)
    case.status = "approved_by_supervisor" if approve else "denied_by_supervisor"
    s.flush()
    after.append(_reindex_case(case.id))
    return {"outcome": case.status, "refund_id": refund.id}


def _upload_policy(s, req, v, after):
    name, content = req.params["name"].strip(), req.params["content"]
    doc = s.query(PolicyDocument).filter(PolicyDocument.name == name).first()
    if doc is None:
        s.add(PolicyDocument(name=name, content=content, uploaded_by=req.actor))
    else:
        doc.content, doc.uploaded_by, doc.uploaded_at = content, req.actor, utcnow()

    def reindex() -> None:
        with session_scope() as s2:
            rag.index_policy(s2.query(PolicyDocument).filter(PolicyDocument.name == name).one())

    after.append(reindex)
    return {"name": name, "chunks": [cid for cid, _ in rag.chunk_policy(name, content)]}


IMPLEMENTATIONS: dict[str, Impl] = {
    "create_case": _create_case,
    "assign_case": _assign_case,
    "get_case": _get_case,
    "get_customer_profile": _get_customer_profile,
    "search_records": _search_records,
    "update_case_status": _update_case_status,
    "store_customer_note": _store_customer_note,
    "get_customer_contact": _get_customer_contact,
    "draft_email": _draft_email,
    "send_email": _send_email,
    "receive_emails": _receive_emails,
    "retrieve_policy": _retrieve_policy,
    "get_weekly_total": _get_weekly_total,
    "decide_refund": _decide_refund,
    "process_refund": _process_refund,
    "record_report_entry": _record_report_entry,
    "get_refund_report": _get_refund_report,
    "supervisor_decide": _supervisor_decide,
    "upload_policy": _upload_policy,
}


# --------------------------------------------------------------------------
# The choke point
# --------------------------------------------------------------------------

def _bind(s: Session, ctx: ToolContext, tool: str, params: dict[str, Any]) -> tuple[int | None, int | None]:
    """Resolve case and customer from the database. A caller-supplied
    customer_id is only honoured for create_case (the submitting customer)."""
    if tool == "create_case":
        cid = params.get("customer_id")
        return None, cid if isinstance(cid, int) else None
    if ctx.case_id is None:
        return None, None
    case = s.get(Case, ctx.case_id)
    if case is None:
        return None, None
    return case.id, case.customer_id


def _target(tool: str, case_id: int | None, customer_id: int | None, data: Any) -> str:
    if tool == "create_case" and isinstance(data, dict) and "case_id" in data:
        return f"case:{data['case_id']}"
    if tool == "upload_policy":
        return "policy_store"
    if case_id is not None:
        return f"case:{case_id}"
    if customer_id is not None:
        return f"customer:{customer_id}"
    return "-"


def invoke(actor: str, tool: str, ctx: ToolContext | None = None,
           params: dict[str, Any] | None = None) -> ToolResult:
    ctx = ctx or ToolContext()
    params = dict(params or {})
    after: After = []
    with _action_lock:
        error = None
        try:
            with session_scope() as s:
                case_id, customer_id = _bind(s, ctx, tool, params)
                req = ActionRequest(actor, tool, params, case_id, customer_id)
                verdict = evaluate(s, req)
                revocation = state.revocation_state(s)
                impl = IMPLEMENTATIONS.get(tool)
                if impl is not None and (verdict.allowed or verdict.route):
                    data = impl(s, req, verdict, after)
                else:
                    data = {"refused": verdict.reason}
        except ToolError as exc:  # rolled back by session_scope
            error = str(exc)
            data, after = {"error": error}, []
        for callback in after:
            callback()
        ok = verdict.allowed and error is None
        audit_id = audit.record(
            actor=actor,
            action=tool,
            target=_target(tool, case_id, customer_id, data),
            inputs={"params": params, "case_id": case_id, "customer_id": customer_id},
            decision=verdict.decision if error is None else "error",
            rule=verdict.rule,
            reason=verdict.reason if error is None else f"{verdict.reason}; execution error: {error}",
            policy_refs=verdict.policy_refs,
            result=data,
            revocation_state=revocation,
            guardrails_off=verdict.guardrails_off,
        )
    return ToolResult(actor, tool, ok, data, verdict, audit_id)
