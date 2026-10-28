"""Common agent plumbing: every tool call goes through ``tools.invoke``."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..llm import LLM, get_llm
from ..permissions import TOOL_CATALOG, grants_for
from ..tools import ToolContext, ToolResult, invoke


@dataclass
class StepResult:
    step: str
    agent: str
    ok: bool
    summary: str
    calls: list[ToolResult] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def halted(self) -> bool:
        return any(c.halted for c in self.calls)

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "agent": self.agent, "ok": self.ok, "halted": self.halted,
                "summary": self.summary, "data": self.data,
                "calls": [c.as_dict() for c in self.calls]}


class BaseAgent:
    name: ClassVar[str]

    def __init__(self, llm: LLM | None = None):
        self._llm = llm

    @property
    def llm(self) -> LLM:
        return self._llm or get_llm()

    @property
    def tools(self) -> frozenset[str]:
        """Read-only view of this agent's grants (see permissions.py)."""
        return grants_for(self.name)

    def call(self, tool: str, case_id: int | None = None, /, **params: Any) -> ToolResult:
        return invoke(self.name, tool, ToolContext(case_id=case_id), params)

    def act(self, case_id: int | None, instruction: str = "", tool: str | None = None,
            params: dict[str, Any] | None = None) -> StepResult:
        """Free-form operation: the LLM picks one tool from this agent's grant
        (or the caller names one directly). Either way the call is just a
        proposal that goes through the policy engine like any other."""
        if tool is None:
            infos = [TOOL_CATALOG[t] for t in sorted(self.tools)]
            plan = self.llm.plan_tool_call(self.name, infos, instruction, {"case_id": case_id})
            if plan is None:
                return StepResult("act", self.name, False, "model proposed no tool call")
            tool, params = plan["tool"], plan.get("params") or {}
        result = self.call(tool, case_id, **(params or {}))
        verb = "allowed" if result.ok else f"refused ({result.verdict.rule})"
        return StepResult("act", self.name, result.ok, f"{tool}: {verb}", [result],
                          {"proposed": {"tool": tool, "params": params or {}}})
