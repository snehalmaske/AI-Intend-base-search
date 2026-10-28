"""Reporting Agent - records each outcome (approved/denied/escalated + reason)."""
from __future__ import annotations

from .base import BaseAgent, StepResult


class ReportingAgent(BaseAgent):
    name = "reporting_agent"

    def record(self, case_id: int) -> StepResult:
        res = self.call("record_report_entry", case_id)
        summary = (f"recorded outcome '{res.data['outcome']}'" if res.ok
                   else f"not recorded: {res.verdict.reason}")
        return StepResult("report", self.name, res.ok, summary, [res])
