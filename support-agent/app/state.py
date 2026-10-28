"""Global system state: the revocation kill-switch and informational counters."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import audit
from .db import SystemState, session_scope

ACTIVE = "active"
REVOKED = "revoked"


def revocation_state(session: Session | None = None) -> str:
    """Always read fresh from the database: never cached, so a flip is seen
    by the very next action, including one in the middle of a workflow."""
    if session is None:
        with session_scope() as s:
            return revocation_state(s)
    session.expire_all()
    row = session.get(SystemState, "revocation")
    return row.value if row else ACTIVE


def is_revoked(session: Session | None = None) -> bool:
    return revocation_state(session) == REVOKED


def set_revocation(revoked: bool, *, actor: str, reason: str = "") -> str:
    """Operator control. Deliberately not exposed as an agent tool."""
    new = REVOKED if revoked else ACTIVE
    with session_scope() as s:
        row = s.get(SystemState, "revocation")
        old = row.value if row else ACTIVE
        if row is None:
            s.add(SystemState(key="revocation", value=new))
        else:
            row.value = new
    audit.record(
        actor=actor,
        action="revoke_authority" if revoked else "restore_authority",
        target="system:revocation",
        inputs={"revoked": revoked, "reason": reason},
        decision="allow",
        rule="operator_control",
        reason=reason or f"revocation {old} -> {new}",
        result=f"{old} -> {new}",
        revocation_state=new,
    )
    return new


def set_weekly_counter(session: Session, customer_id: int, total: float) -> None:
    """Display-only cache of the rolling weekly total. The policy engine never
    reads this value; it always recomputes from the refunds table."""
    key = f"weekly_total:{customer_id}"
    row = session.get(SystemState, key)
    if row is None:
        session.add(SystemState(key=key, value=f"{total:.2f}"))
    else:
        row.value = f"{total:.2f}"
