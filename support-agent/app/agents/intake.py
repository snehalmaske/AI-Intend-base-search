"""Intake Agent - case submission and assignment."""
from __future__ import annotations

from ..tools import ToolContext, invoke
from .base import BaseAgent, StepResult


class IntakeAgent(BaseAgent):
    name = "intake_agent"

    def submit(self, customer_id: int, description: str, amount_requested: float) -> StepResult:
        res = invoke(self.name, "create_case", ToolContext(customer_id=customer_id),
                     {"customer_id": customer_id, "description": description,
                      "amount_requested": amount_requested})
        if not res.ok:
            return StepResult("submit", self.name, False, f"case not created: {res.verdict.reason}", [res])
        data = res.data
        note = f" (possible duplicate of case #{data['duplicate_of']})" if data["duplicate_of"] else ""
        return StepResult("submit", self.name, True, f"case #{data['case_id']} created{note}", [res], data)

    def assign(self, case_id: int) -> StepResult:
        res = self.call("assign_case", case_id, agent="refunds_agent")
        summary = "assigned to refunds_agent" if res.ok else f"not assigned: {res.verdict.reason}"
        return StepResult("intake", self.name, res.ok, summary, [res])
