"""Refunds Agent - submit/decide/process.

The LLM proposes approve/deny/escalate and cites policy chunks. The policy
engine (inside ``decide_refund`` / ``process_refund``) has the final word.
"""
from __future__ import annotations

from typing import Any

from .base import BaseAgent, StepResult


class RefundsAgent(BaseAgent):
    name = "refunds_agent"

    def decide(self, case_id: int, case: dict[str, Any], customer: dict[str, Any]) -> StepResult:
        query = f"refund request ${case['amount_requested']:.2f}: {case['description']}"
        policy = self.call("retrieve_policy", query=query, k=4)
        weekly = self.call("get_weekly_total", case_id)
        calls = [policy, weekly]
        chunks = policy.data if policy.ok else []
        total = weekly.data["weekly_total"] if weekly.ok else 0.0
        proposal = self.llm.propose_refund_decision(case, customer, chunks, total)
        retrieved = {c["id"] for c in chunks}
        # Only citations of chunks actually retrieved survive; the engine
        # re-verifies them against the policy store.
        refs = [r for r in proposal.get("policy_refs", []) if r in retrieved]
        decision = self.call("decide_refund", case_id, proposed_decision=proposal["decision"],
                             reason=proposal["reason"][:2000], policy_refs=refs)
        calls.append(decision)
        v = decision.verdict
        outcome = (decision.data or {}).get("outcome") if isinstance(decision.data, dict) else None
        if outcome:
            note = "" if v.allowed else f" - policy engine overrode proposal ({v.rule})"
            summary = f"model proposed '{proposal['decision']}', outcome '{outcome}'{note}"
        else:
            summary = f"decision refused: {v.reason}"
        return StepResult("decide", self.name, outcome is not None, summary, calls,
                          {"proposal": proposal, "outcome": outcome,
                           "retrieved_policy": [{"id": c["id"], "score": c.get("score")} for c in chunks]})

    def process(self, case_id: int) -> StepResult:
        res = self.call("process_refund", case_id)
        if res.ok:
            d = res.data
            summary = f"refund ${d['amount']:.2f} issued; balance ${d['balance_before']:.2f} -> ${d['balance_after']:.2f}"
        else:
            summary = f"refund not issued: {res.verdict.reason}"
        return StepResult("process", self.name, res.ok, summary, [res])
