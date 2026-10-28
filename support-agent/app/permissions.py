"""Least-privilege map: which principal may call which tool.

This module is the *only* place grants are defined. The mappings are
read-only (``MappingProxyType`` of ``frozenset``), no tool or endpoint writes
them, and the policy engine refuses (and logs) any action that tries to.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class Param:
    type: str  # string | number | integer | boolean
    required: bool = False
    description: str = ""
    enum: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str
    consequential: bool  # writes state / sends something -> blocked under revocation
    params: Mapping[str, Param]

    def json_schema(self) -> dict[str, Any]:
        props: dict[str, Any] = {}
        for name, p in self.params.items():
            prop: dict[str, Any] = {"type": p.type}
            if p.description:
                prop["description"] = p.description
            if p.enum:
                prop["enum"] = list(p.enum)
            if p.type == "array":
                prop["items"] = {"type": "string"}
            props[name] = prop
        return {
            "type": "object",
            "properties": props,
            "required": [n for n, p in self.params.items() if p.required],
            "additionalProperties": False,
        }


def _tool(name: str, doc: str, consequential: bool, /, **params: Param) -> ToolInfo:
    return ToolInfo(name, doc, consequential, MappingProxyType(params))


_CATALOG = [
    # --- Intake -------------------------------------------------------------
    _tool("create_case", "Create a refund case for the submitting customer.", True,
          customer_id=Param("integer", True), description=Param("string", True),
          amount_requested=Param("number", True)),
    _tool("assign_case", "Assign the current case to a queue/agent.", True,
          agent=Param("string", False, enum=("refunds_agent",))),
    # --- Shared read --------------------------------------------------------
    _tool("get_case", "Read the current case.", False, case_id=Param("integer")),
    # --- Records ------------------------------------------------------------
    _tool("get_customer_profile", "Read the current case's customer profile (bank account masked).",
          False, customer_id=Param("integer")),
    _tool("search_records", "Semantic search over the current customer's profile and cases.", False,
          query=Param("string", True), limit=Param("integer")),
    _tool("update_case_status", "Set a non-decision status on the current case.", True,
          status=Param("string", True), note=Param("string")),
    _tool("store_customer_note", "Append a note to the current customer's profile.", True,
          note=Param("string", True)),
    # --- Email --------------------------------------------------------------
    _tool("get_customer_contact", "Name and email of the current case's customer.", False),
    _tool("draft_email", "Preview an email to the current customer (not sent).", False,
          subject=Param("string", True), body=Param("string", True)),
    _tool("send_email", "Send an email to the current case's customer (mock outbox).", True,
          subject=Param("string", True), body=Param("string", True), to=Param("string"),
          notify_status=Param("string", description="case status this email notifies the customer of")),
    _tool("receive_emails", "Read inbound emails for the current case (mock inbox).", False),
    # --- Refunds ------------------------------------------------------------
    _tool("retrieve_policy", "Retrieve refund-policy chunks relevant to a query.", False,
          query=Param("string", True), k=Param("integer")),
    _tool("get_weekly_total", "Approved refund total for the current customer, rolling 7 days.", False),
    _tool("decide_refund", "Record an approve/deny/escalate decision for the current case.", True,
          proposed_decision=Param("string", True, enum=("approve", "deny", "escalate")),
          reason=Param("string", True), policy_refs=Param("array")),
    _tool("process_refund", "Issue the approved refund for the current case (credits balance).", True),
    # --- Reporting ----------------------------------------------------------
    _tool("record_report_entry", "Record the current case's outcome and reason for reporting.", True),
    _tool("get_refund_report", "Refund summary for the current customer.", False),
    # --- Human principals -----------------------------------------------------
    _tool("supervisor_decide", "Human supervisor decision on a case in supervisor_review.", True,
          decision=Param("string", True, enum=("approve", "deny")), reason=Param("string", True)),
    _tool("upload_policy", "Upload/replace a refund policy document.", True,
          name=Param("string", True), content=Param("string", True)),
]

TOOL_CATALOG: Mapping[str, ToolInfo] = MappingProxyType({t.name: t for t in _CATALOG})

AGENTS = ("intake_agent", "email_agent", "records_agent", "refunds_agent", "reporting_agent")
HUMANS = ("supervisor", "admin")

TOOL_GRANTS: Mapping[str, frozenset[str]] = MappingProxyType({
    "intake_agent": frozenset({"create_case", "assign_case", "get_case"}),
    "email_agent": frozenset({"get_customer_contact", "draft_email", "send_email", "receive_emails"}),
    "records_agent": frozenset({
        "get_case", "get_customer_profile", "search_records", "update_case_status",
        "store_customer_note",
    }),
    "refunds_agent": frozenset({"retrieve_policy", "get_weekly_total", "decide_refund", "process_refund"}),
    "reporting_agent": frozenset({"record_report_entry", "get_refund_report"}),
    "supervisor": frozenset({"supervisor_decide", "get_case"}),
    "admin": frozenset({"upload_policy"}),
})

# Actions that would change grants, the policy engine, guardrails or the
# kill-switch. No tool implements any of them; they exist so an attempt is
# recognised, refused under the right rule and logged.
PROTECTED_ACTIONS = frozenset({
    "grant_tool", "revoke_tool", "set_permissions", "update_permissions", "modify_tool_grants",
    "modify_policy_engine", "update_policy_engine", "disable_guardrail", "enable_guardrail",
    "set_guardrail", "set_revocation", "restore_authority", "revoke_authority",
    "update_config", "set_config",
})
PROTECTED_PREFIXES = ("grant_", "set_permission", "modify_policy", "disable_guardrail",
                      "update_policy_engine", "elevate_")

# Bulk/enumeration-style actions that are always refused as record exports.
EXPORT_ACTIONS = frozenset({
    "export_records", "export_customers", "bulk_export", "bulk_export_records",
    "list_all_customers", "list_customers", "dump_records", "get_all_customers",
})


def grants_for(principal: str) -> frozenset[str]:
    return TOOL_GRANTS.get(principal, frozenset())
