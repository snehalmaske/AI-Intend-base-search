import threading

from app import state
from app.agents import IntakeAgent
from app.db import Refund, SystemState, session_scope
from app.orchestrator import Orchestrator
from app.tools import ToolContext, invoke

from .conftest import CARMEN_85, balance


def test_weekly_cap_denies_request_that_would_exceed():
    before = balance(3)
    run = Orchestrator().run(CARMEN_85)  # $440 already approved this week
    assert run.final_status == "denied"
    decide = next(s for s in run.steps if s.step == "decide")
    assert decide.calls[-1].verdict.rule == "weekly_cumulative_cap"
    assert balance(3) == before


def test_weekly_total_comes_from_ledger_not_counter():
    with session_scope() as s:
        state.set_weekly_counter(s, 3, 0.0)  # tamper with the display counter
    with session_scope() as s:
        assert s.get(SystemState, "weekly_total:3").value == "0.00"
    assert Orchestrator().run(CARMEN_85).final_status == "denied"


ITEMS = ["toaster", "umbrella", "backpack", "monitor cable", "yoga mat", "coffee grinder"]


def test_cumulative_small_refunds_stop_at_cap():
    intake, orch = IntakeAgent(), Orchestrator()
    outcomes = []
    for item in ITEMS:  # Esther (customer 5) has no refunds this week
        cid = intake.submit(5, f"The {item} I received is defective", 100.0).data["case_id"]
        outcomes.append(orch.run(cid).final_status)
    assert outcomes == ["processed"] * 5 + ["denied"]


def test_supervisor_approval_is_also_capped():
    from .conftest import BRUNO_250

    orch, intake = Orchestrator(), IntakeAgent()
    assert orch.run(BRUNO_250).final_status == "supervisor_review"
    for item in ITEMS[:3]:  # $285 approved for Bruno while the $250 case waits
        cid = intake.submit(2, f"The {item} I received is defective", 95.0).data["case_id"]
        assert orch.run(cid).final_status == "processed"
    res = invoke("supervisor", "supervisor_decide", ToolContext(case_id=BRUNO_250),
                 {"decision": "approve", "reason": "looks fine"})
    assert not res.ok and res.verdict.rule == "weekly_cumulative_cap"


def test_concurrent_approvals_cannot_exceed_cap():
    """Parallel workflows for one customer race on the weekly total; the
    engine's lock + same-transaction check must keep the total <= $500."""
    intake = IntakeAgent()
    ids = [intake.submit(1, f"The {item} arrived shattered", 95.0).data["case_id"]
           for item in ITEMS + ["lamp", "vase"]]
    threads = [threading.Thread(target=lambda c=c: Orchestrator().run(c)) for c in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with session_scope() as s:
        approved = sum(r.amount for r in s.query(Refund).filter(Refund.customer_id == 1,
                                                                 Refund.decision == "approved"))
    assert approved <= 500.0
