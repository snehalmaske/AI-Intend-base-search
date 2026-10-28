"""Workflow orchestration.

Each step is a plain function that hands the case to exactly one agent.
The *next* step is always derived from the case row in SQLite, so a run can
stop (supervisor review, kill-switch) and resume later from the UI.

    intake -> validate -> acknowledge -> decide -> notify -> [process] -> report
                                                   ^ supervisor decision re-enters here

The full run is a LangGraph ``StateGraph`` (router node + one node per step,
explicit conditional edges). If LangGraph is not installed, an equivalent
loop over the same functions is used.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, TypedDict

from .agents import EmailAgent, IntakeAgent, RecordsAgent, RefundsAgent, ReportingAgent, StepResult
from .db import Case, session_scope
from .llm import LLM

STEPS = ("intake", "validate", "acknowledge", "decide", "notify", "process", "report")
NOTIFIABLE = {"approved", "denied", "supervisor_review", "approved_by_supervisor", "denied_by_supervisor"}
REPORTABLE = {"processed", "denied", "denied_by_supervisor", "supervisor_review"}
STEP_AGENT = {"intake": "intake_agent", "validate": "records_agent", "acknowledge": "email_agent",
              "decide": "refunds_agent", "notify": "email_agent", "process": "refunds_agent",
              "report": "reporting_agent"}


def next_step_for(case: Case) -> str | None:
    s = case.status
    if s == "new":
        return "intake"
    if s == "assigned":
        return "validate"
    if s == "validated":
        return "acknowledge"
    if s == "acknowledged":
        return "decide"
    if s in NOTIFIABLE and case.notified_status != s:
        return "notify"
    if s in ("approved", "approved_by_supervisor"):
        return "process"
    if s in REPORTABLE and case.reported_status != s:
        return "report"
    return None


def next_step(case_id: int) -> str | None:
    with session_scope() as s:
        case = s.get(Case, case_id)
        return next_step_for(case) if case else None


class Orchestrator:
    def __init__(self, llm: LLM | None = None):
        self.intake = IntakeAgent(llm)
        self.records = RecordsAgent(llm)
        self.email = EmailAgent(llm)
        self.refunds = RefundsAgent(llm)
        self.reporting = ReportingAgent(llm)
        self._steps: dict[str, Callable[[int], StepResult]] = {
            "intake": self.intake.assign,
            "validate": self.records.validate,
            "acknowledge": self._acknowledge,
            "decide": self._decide,
            "notify": self._notify,
            "process": self.refunds.process,
            "report": self.reporting.record,
        }

    # -- steps that hand context from Records to another agent ---------------
    def _acknowledge(self, case_id: int) -> StepResult:
        case, _, calls = self.records.load(case_id)
        if case is None:
            return StepResult("acknowledge", "email_agent", False, "case unavailable", calls)
        res = self.email.acknowledge(case_id, case)
        res.calls = calls + res.calls
        if res.ok:
            mark = self.records.mark(case_id, "acknowledged", "acknowledgement sent")
            res.calls += mark.calls
            res.ok = mark.ok
        return res

    def _decide(self, case_id: int) -> StepResult:
        case, customer, calls = self.records.load(case_id)
        if case is None or customer is None:
            return StepResult("decide", "refunds_agent", False, "case unavailable", calls)
        res = self.refunds.decide(case_id, case, customer)
        res.calls = calls + res.calls
        return res

    def _notify(self, case_id: int) -> StepResult:
        case, _, calls = self.records.load(case_id)
        if case is None:
            return StepResult("notify", "email_agent", False, "case unavailable", calls)
        res = self.email.notify_decision(case_id, case)
        res.calls = calls + res.calls
        return res

    # -- public API ------------------------------------------------------------
    def run_step(self, case_id: int, step: str) -> StepResult:
        if step not in self._steps:
            raise ValueError(f"unknown step '{step}'")
        return self._steps[step](case_id)

    def run(self, case_id: int, max_steps: int = 12) -> "WorkflowRun":
        if _HAS_LANGGRAPH:
            return self._run_langgraph(case_id, max_steps)
        return self._run_loop(case_id, max_steps)

    def _run_loop(self, case_id: int, max_steps: int) -> "WorkflowRun":
        results: list[StepResult] = []
        for _ in range(max_steps):
            step = next_step(case_id)
            if step is None:
                break
            res = self.run_step(case_id, step)
            results.append(res)
            if res.halted or not res.ok:
                break
        return WorkflowRun.build(case_id, results, engine="loop")

    def _run_langgraph(self, case_id: int, max_steps: int) -> "WorkflowRun":
        graph = self._graph()
        final = graph.invoke({"case_id": case_id, "results": [], "next": None},
                             config={"recursion_limit": max_steps * 2 + 2})
        return WorkflowRun.build(case_id, final["results"], engine="langgraph")

    def _graph(self):
        builder = StateGraph(_GraphState)

        def router(state: _GraphState) -> dict[str, Any]:
            last = state["results"][-1] if state["results"] else None
            if last is not None and (last.halted or not last.ok):
                return {"next": None}
            return {"next": next_step(state["case_id"])}

        builder.add_node("router", router)
        for step in STEPS:
            builder.add_node(step, lambda state, step=step: {"results": [self.run_step(state["case_id"], step)]})
            builder.add_edge(step, "router")
        builder.add_edge(START, "router")
        builder.add_conditional_edges("router", lambda st: st["next"] or END,
                                      {**{s: s for s in STEPS}, END: END})
        return builder.compile()


try:
    from langgraph.graph import END, START, StateGraph

    _HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover
    _HAS_LANGGRAPH = False
    END = START = None  # type: ignore[assignment]


class _GraphState(TypedDict):
    case_id: int
    results: Annotated[list[StepResult], operator.add]
    next: str | None


@dataclass
class WorkflowRun:
    case_id: int
    engine: str
    steps: list[StepResult] = field(default_factory=list)
    final_status: str | None = None
    next_step: str | None = None
    halted: bool = False

    @classmethod
    def build(cls, case_id: int, steps: list[StepResult], engine: str) -> "WorkflowRun":
        with session_scope() as s:
            case = s.get(Case, case_id)
            status = case.status if case else None
            nxt = next_step_for(case) if case else None
        return cls(case_id, engine, steps, status, nxt, any(r.halted for r in steps))

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "engine": self.engine, "final_status": self.final_status,
                "next_step": self.next_step, "halted": self.halted,
                "steps": [r.as_dict() for r in self.steps]}
