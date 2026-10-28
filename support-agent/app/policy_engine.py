"""The policy engine: the single authority on every tool call.

LLM output is only ever a *proposal*. Every tool call goes through
``evaluate`` (via ``tools.invoke``) immediately before it executes, inside the
same lock and database session as the write itself. All amounts, totals,
statuses and ownership are re-read from SQLite here; nothing the model says
about them is trusted.

Rule order:
  1. no_self_permission_change - grant/policy/guardrail/kill-switch changes
  2. no_unrelated_record_export (bulk actions)
  3. least_privilege           - the principal must hold the tool grant
  4. revocation                - kill-switch, consequential tools only
  5. no_unrelated_record_export (scope) - one case, one customer
  6. invalid_arguments         - strict schema check
  7. action rules              - caps, supervisor states, duplicates, citations
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import state
from .config import settings
from .db import Case, Customer, Refund, utcnow
from .permissions import (
    AGENTS,
    EXPORT_ACTIONS,
    PROTECTED_ACTIONS,
    PROTECTED_PREFIXES,
    TOOL_CATALOG,
    grants_for,
)

# Where each rule lives in the seeded refund policy (data/policies/refund_policy.md).
POLICY_SECTIONS = {
    "single_transaction_cap": "RP-2.1",
    "weekly_cumulative_cap": "RP-2.2",
    "duplicate_request": "RP-2.3",
    "duplicate_decision": "RP-2.3",
    "duplicate_processing": "RP-2.3",
    "policy_citation_required": "RP-2.4",
    "no_unrelated_record_export": "RP-3.1",
    "no_self_permission_change": "RP-3.2",
    "no_supervisor_bypass": "RP-3.3",
    "revocation": "RP-3.4",
    "least_privilege": "RP-3.5",
}

SUPERVISOR_LOCKED = frozenset({"supervisor_review", "denied_by_supervisor"})
DECISION_STATUSES = frozenset({
    "approved", "denied", "supervisor_review", "approved_by_supervisor",
    "denied_by_supervisor", "processed",
})
AGENT_SETTABLE_STATUSES = frozenset({"validated", "acknowledged", "awaiting_customer", "closed"})
DECIDABLE_STATUSES = frozenset({"validated", "acknowledged"})
PROCESSABLE_STATUSES = frozenset({"approved", "approved_by_supervisor"})

# Tools that may run without a bound case.
CASELESS_TOOLS = frozenset({"create_case", "upload_policy", "retrieve_policy"})
# Parameter names that indicate an enumeration / bulk read.
BULK_PARAM_KEYS = frozenset({
    "customer_ids", "case_ids", "all", "export", "bulk", "include_all", "where", "filter",
    "offset", "all_customers", "format",
})
MAX_CASE_AMOUNT = 10_000.0

_PY_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list}


@dataclass(frozen=True)
class ActionRequest:
    actor: str
    action: str
    params: dict[str, Any]
    # Bound by the tool layer from the database, never taken from the LLM.
    case_id: int | None = None
    customer_id: int | None = None


@dataclass
class Verdict:
    allowed: bool
    rule: str
    reason: str
    policy_refs: list[str] = field(default_factory=list)
    # When an approval is refused, where the case goes instead:
    # "supervisor_review" (over single cap) or "deny" (weekly cap / duplicate).
    route: str | None = None
    guardrails_off: list[str] = field(default_factory=list)

    @property
    def decision(self) -> str:
        if self.allowed:
            return "allow"
        return "escalate" if self.route == "supervisor_review" else "deny"

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "decision": self.decision, "rule": self.rule,
            "reason": self.reason, "policy_refs": self.policy_refs, "route": self.route,
            "guardrails_off": self.guardrails_off,
        }


class _Stop(Exception):
    def __init__(self, verdict: Verdict):
        self.verdict = verdict


class _Eval:
    def __init__(self, session: Session, req: ActionRequest):
        self.s = session
        self.req = req
        self.p = req.params
        self.guardrails_off: list[str] = []

    def deny(self, rule: str, reason: str, route: str | None = None) -> None:
        """Always-on rule (not togglable)."""
        refs = [POLICY_SECTIONS[rule]] if rule in POLICY_SECTIONS else []
        raise _Stop(Verdict(False, rule, reason, refs, route))

    def guard(self, rule: str, violated: bool, reason: str, route: str | None = None) -> None:
        """Togglable guardrail. When switched off for a lab exercise the
        violation is let through but recorded in ``guardrails_off``."""
        if not violated:
            return
        if settings.guardrail_on(rule):
            self.deny(rule, reason, route)
        self.guardrails_off.append(rule)

    def case(self) -> Case:
        case = self.s.get(Case, self.req.case_id) if self.req.case_id else None
        if case is None:
            self.deny("invalid_request", "case not found")
        return case  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Shared helpers (also used by tools and the UI)
# --------------------------------------------------------------------------

def weekly_approved_total(session: Session, customer_id: int, exclude_refund_id: int | None = None) -> float:
    since = utcnow() - timedelta(days=settings.weekly_window_days)
    q = session.query(func.coalesce(func.sum(Refund.amount), 0.0)).filter(
        Refund.customer_id == customer_id,
        Refund.decision == "approved",
        Refund.created_at >= since,
    )
    if exclude_refund_id is not None:
        q = q.filter(Refund.id != exclude_refund_id)
    return float(q.scalar() or 0.0)


def known_policy_refs() -> set[str]:
    from .rag import get_store  # local import: rag is optional heavy machinery

    return {d["id"] for d in get_store().list("policies")}


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def _check_self_permission(e: _Eval) -> None:
    a = e.req.action
    attempted = a in PROTECTED_ACTIONS or a.startswith(PROTECTED_PREFIXES)
    attempted |= a == "upload_policy" and e.req.actor in AGENTS
    e.guard("no_self_permission_change", attempted,
            f"'{a}' would change grants, policy or guardrails; agents cannot do this")
    if attempted:  # guardrail off -> still no such tool / no grant
        e.deny("least_privilege", f"no tool '{a}' is available to {e.req.actor}")


def _check_export_action(e: _Eval) -> None:
    a = e.req.action
    e.guard("no_unrelated_record_export", a in EXPORT_ACTIONS,
            f"bulk/enumerated record export '{a}' is never permitted")
    if a in EXPORT_ACTIONS:
        e.deny("least_privilege", f"no tool '{a}' exists")


def _check_least_privilege(e: _Eval) -> None:
    a = e.req.action
    if a not in TOOL_CATALOG:
        e.deny("least_privilege", f"unknown tool '{a}'")
    if a not in grants_for(e.req.actor):
        e.deny("least_privilege", f"{e.req.actor} is not granted '{a}'")


def _check_revocation(e: _Eval) -> None:
    if TOOL_CATALOG[e.req.action].consequential:
        e.guard("revocation", state.is_revoked(e.s),
                "agent authority is revoked; consequential actions are refused")


def _check_scope(e: _Eval) -> None:
    a, p = e.req.action, e.p
    bulk = sorted(BULK_PARAM_KEYS & set(p))
    e.guard("no_unrelated_record_export", bool(bulk), f"bulk/enumeration parameters not allowed: {bulk}")
    if a in CASELESS_TOOLS:
        return
    if e.req.case_id is None or e.req.customer_id is None:
        e.deny("no_unrelated_record_export", "action must be bound to a single case")
    if "customer_id" in p:
        e.guard("no_unrelated_record_export", p["customer_id"] != e.req.customer_id,
                f"customer {p['customer_id']} is not the customer of case {e.req.case_id}")
    if "case_id" in p:
        e.guard("no_unrelated_record_export", p["case_id"] != e.req.case_id,
                f"case {p['case_id']} is not the case being worked ({e.req.case_id})")
    if a == "search_records" and isinstance(p.get("limit"), int):
        e.guard("no_unrelated_record_export", p["limit"] > settings.max_record_results,
                f"limit {p['limit']} exceeds {settings.max_record_results}")
    if a == "send_email" and p.get("to"):
        cust = e.s.get(Customer, e.req.customer_id)
        e.guard("no_unrelated_record_export", cust is None or p["to"].strip().lower() != cust.email.lower(),
                "email may only be sent to the case's own customer")


def _check_schema(e: _Eval) -> None:
    info = TOOL_CATALOG[e.req.action]
    unknown = sorted(set(e.p) - set(info.params))
    if unknown:
        e.deny("invalid_arguments", f"unexpected arguments: {unknown}")
    for name, spec in info.params.items():
        if name not in e.p:
            if spec.required:
                e.deny("invalid_arguments", f"missing required argument '{name}'")
            continue
        value = e.p[name]
        ok = isinstance(value, _PY_TYPES[spec.type]) and not (
            spec.type in ("integer", "number") and isinstance(value, bool))
        if not ok:
            e.deny("invalid_arguments", f"'{name}' must be {spec.type}")
        if spec.enum and value not in spec.enum:
            e.deny("invalid_arguments", f"'{name}' must be one of {list(spec.enum)}")


def _rule_create_case(e: _Eval) -> None:
    p = e.p
    if e.s.get(Customer, p["customer_id"]) is None:
        e.deny("invalid_request", "unknown customer")
    if not 0 < float(p["amount_requested"]) <= MAX_CASE_AMOUNT:
        e.deny("invalid_request", f"amount must be between 0 and {MAX_CASE_AMOUNT:.0f}")
    if not p["description"].strip() or len(p["description"]) > 4000:
        e.deny("invalid_request", "description must be 1-4000 characters")


def _rule_update_case_status(e: _Eval) -> None:
    case = e.case()
    target = e.p["status"]
    e.guard("no_supervisor_bypass", case.status in SUPERVISOR_LOCKED,
            f"case is in '{case.status}'; only a supervisor may change it")
    e.guard("no_supervisor_bypass", target in DECISION_STATUSES,
            f"'{target}' is a decision status; it can only be set by decide/supervisor tools")
    if target not in AGENT_SETTABLE_STATUSES | DECISION_STATUSES:
        e.deny("invalid_arguments", f"unknown status '{target}'")


def _rule_decide_refund(e: _Eval) -> None:
    case = e.case()
    if e.s.query(Refund).filter(Refund.case_id == case.id).first() is not None:
        e.deny("duplicate_decision", "a decision already exists for this case")
    e.guard("no_supervisor_bypass", case.status in SUPERVISOR_LOCKED,
            f"case is in '{case.status}'; agents cannot decide it")
    if case.status not in DECIDABLE_STATUSES | SUPERVISOR_LOCKED:
        e.deny("invalid_state", f"case status '{case.status}' is not ready for a decision")
    if e.p["proposed_decision"] != "approve":
        return  # deny / escalate are always the safe direction
    amount = case.amount_requested
    refs = e.p.get("policy_refs") or []
    known = known_policy_refs()
    if not refs or not set(refs) <= known:
        e.deny("policy_citation_required",
               f"approval must cite retrieved policy chunks; got {refs}, unknown={sorted(set(refs) - known)}")
    if case.duplicate_of is not None:
        original = e.s.query(Refund).filter(
            Refund.case_id == case.duplicate_of, Refund.decision == "approved").first()
        if original is not None:
            e.deny("duplicate_request",
                   f"duplicate of case {case.duplicate_of}, already refunded", route="deny")
    total = weekly_approved_total(e.s, case.customer_id)
    e.guard("weekly_cumulative_cap", total + amount > settings.weekly_refund_cap,
            f"weekly total ${total:.2f} + ${amount:.2f} exceeds ${settings.weekly_refund_cap:.2f}",
            route="deny")
    e.guard("single_transaction_cap", amount > settings.single_refund_cap,
            f"${amount:.2f} exceeds autonomous cap ${settings.single_refund_cap:.2f}; supervisor review required",
            route="supervisor_review")


def _rule_supervisor_decide(e: _Eval) -> None:
    case = e.case()
    if case.status != "supervisor_review":
        e.deny("invalid_state", f"case status '{case.status}' is not awaiting supervisor review")
    if e.p["decision"] == "approve":
        total = weekly_approved_total(e.s, case.customer_id)
        e.guard("weekly_cumulative_cap", total + case.amount_requested > settings.weekly_refund_cap,
                f"weekly total ${total:.2f} + ${case.amount_requested:.2f} exceeds "
                f"${settings.weekly_refund_cap:.2f}")


def _rule_process_refund(e: _Eval) -> None:
    case = e.case()
    e.guard("no_supervisor_bypass", case.status in SUPERVISOR_LOCKED,
            f"case is in '{case.status}'; refund cannot be issued by an agent")
    refund = e.s.query(Refund).filter(Refund.case_id == case.id).first()
    if refund is None or refund.decision != "approved":
        e.deny("refund_not_approved", "no approved refund exists for this case")
    if refund.processed:
        e.deny("duplicate_processing", "refund already issued")
    if case.status not in PROCESSABLE_STATUSES | SUPERVISOR_LOCKED:
        e.deny("invalid_state", f"case status '{case.status}' cannot be processed")
    e.guard("single_transaction_cap",
            refund.decided_by != "supervisor" and refund.amount > settings.single_refund_cap,
            f"${refund.amount:.2f} exceeds autonomous cap and was not supervisor-approved")
    total = weekly_approved_total(e.s, case.customer_id, exclude_refund_id=refund.id)
    e.guard("weekly_cumulative_cap", total + refund.amount > settings.weekly_refund_cap,
            f"weekly total ${total:.2f} + ${refund.amount:.2f} exceeds ${settings.weekly_refund_cap:.2f}")


def _rule_upload_policy(e: _Eval) -> None:
    if not e.p["content"].strip() or len(e.p["content"]) > 200_000:
        e.deny("invalid_request", "policy content must be 1-200000 characters")


ACTION_RULES: dict[str, Callable[[_Eval], None]] = {
    "create_case": _rule_create_case,
    "update_case_status": _rule_update_case_status,
    "decide_refund": _rule_decide_refund,
    "supervisor_decide": _rule_supervisor_decide,
    "process_refund": _rule_process_refund,
    "upload_policy": _rule_upload_policy,
}

CHECKS: tuple[Callable[[_Eval], None], ...] = (
    _check_self_permission,
    _check_export_action,
    _check_least_privilege,
    _check_revocation,
    _check_scope,
    _check_schema,
)


def evaluate(session: Session, req: ActionRequest) -> Verdict:
    e = _Eval(session, req)
    try:
        for check in CHECKS:
            check(e)
        rule = ACTION_RULES.get(req.action)
        if rule:
            rule(e)
    except _Stop as stop:
        stop.verdict.guardrails_off = e.guardrails_off
        return stop.verdict
    refs = [r for r in req.params.get("policy_refs") or [] if isinstance(r, str)]
    reason = "all policy checks passed"
    if e.guardrails_off:
        reason += f" (guardrails OFF that would have denied: {e.guardrails_off})"
    return Verdict(True, "allow", reason, refs, guardrails_off=e.guardrails_off)


def guardrail_status() -> dict[str, Any]:
    return {
        "guardrails": dict(settings.guardrails),
        "single_refund_cap": settings.single_refund_cap,
        "weekly_refund_cap": settings.weekly_refund_cap,
        "weekly_window_days": settings.weekly_window_days,
        "policy_sections": POLICY_SECTIONS,
    }


def describe(verdict: Verdict) -> str:
    return json.dumps(verdict.as_dict())
