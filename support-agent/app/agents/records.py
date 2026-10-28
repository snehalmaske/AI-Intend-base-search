"""Records Agent - customer records access, storage and retrieval.

Scoped to the current case's customer by the tool layer: it cannot name
another customer, enumerate customers or export records in bulk.
"""
from __future__ import annotations

from typing import Any

from .base import BaseAgent, StepResult


class RecordsAgent(BaseAgent):
    name = "records_agent"

    def load(self, case_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list]:
        case = self.call("get_case", case_id)
        profile = self.call("get_customer_profile", case_id)
        return (case.data if case.ok else None, profile.data if profile.ok else None, [case, profile])

    def validate(self, case_id: int) -> StepResult:
        case, profile, calls = self.load(case_id)
        if case is None or profile is None:
            return StepResult("validate", self.name, False, "could not load case/profile", calls)
        related = self.call("search_records", case_id, query=case["description"], limit=3)
        calls.append(related)
        problems = []
        if case["customer_id"] != profile["id"]:
            problems.append("case/customer mismatch")
        if case["amount_requested"] <= 0:
            problems.append("non-positive amount")
        if problems:
            return StepResult("validate", self.name, False, "; ".join(problems), calls)
        upd = self.call("update_case_status", case_id, status="validated",
                        note="profile and case retrieved and consistent")
        calls.append(upd)
        dup = f"; flagged duplicate of #{case['duplicate_of']}" if case["duplicate_of"] else ""
        return StepResult("validate", self.name, upd.ok,
                          (f"validated against profile of {profile['name']} "
                           f"(balance ${profile['balance']:.2f}){dup}") if upd.ok else f"refused: {upd.verdict.reason}",
                          calls, {"case": case, "customer": profile,
                                  "related_records": related.data if related.ok else []})

    def mark(self, case_id: int, status: str, note: str = "") -> StepResult:
        res = self.call("update_case_status", case_id, status=status, note=note)
        return StepResult("update_status", self.name, res.ok, f"status -> {status}" if res.ok else
                          f"refused: {res.verdict.reason}", [res])
