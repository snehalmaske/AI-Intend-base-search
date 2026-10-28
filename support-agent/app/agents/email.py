"""Email Agent - draft, send (mock outbox) and receive (mock inbox)."""
from __future__ import annotations

from typing import Any

from .base import BaseAgent, StepResult


class EmailAgent(BaseAgent):
    name = "email_agent"

    def _send(self, step: str, case_id: int, case: dict[str, Any], kind: str,
              outcome: str | None = None, reason: str | None = None) -> StepResult:
        contact = self.call("get_customer_contact", case_id)
        calls = [contact]
        if not contact.ok:
            return StepResult(step, self.name, False, "no contact details", calls)
        msg = self.llm.draft_email(kind, case, contact.data, outcome, reason)
        draft = self.call("draft_email", case_id, subject=msg["subject"], body=msg["body"])
        calls.append(draft)
        params = {"subject": msg["subject"], "body": msg["body"]}
        if outcome:
            params["notify_status"] = outcome
        sent = self.call("send_email", case_id, **params)
        calls.append(sent)
        summary = (f"{kind} email sent to {contact.data['email']}" if sent.ok
                   else f"email refused: {sent.verdict.reason}")
        return StepResult(step, self.name, sent.ok, summary, calls, {"email": msg})

    def acknowledge(self, case_id: int, case: dict[str, Any]) -> StepResult:
        return self._send("acknowledge", case_id, case, "acknowledgement")

    def notify_decision(self, case_id: int, case: dict[str, Any]) -> StepResult:
        refund = case.get("refund") or {}
        return self._send("notify", case_id, case, "decision", case["status"], refund.get("reason"))

    def receive(self, case_id: int) -> StepResult:
        res = self.call("receive_emails", case_id)
        n = len(res.data) if res.ok else 0
        return StepResult("receive", self.name, res.ok, f"{n} inbound email(s)", [res],
                          {"emails": res.data if res.ok else []})
