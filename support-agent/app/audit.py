"""Append-only, hash-chained audit log.

One row per attempted action that passes through the tool layer (and per
admin control change). Rows are never updated: the SQLite triggers in
``db.py`` abort UPDATE/DELETE, and ``verify_chain`` detects edits made by
bypassing SQLite entirely.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
from typing import Any, Iterable

from sqlalchemy import or_

from .db import AuditLog, session_scope, utcnow

_lock = threading.Lock()
GENESIS = "0" * 64


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def hash_inputs(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def _row_digest(prev_hash: str, fields: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical(fields)).encode()).hexdigest()


def _hashed_fields(row: AuditLog) -> dict[str, Any]:
    return {
        "ts": row.ts.isoformat(),
        "actor_agent": row.actor_agent,
        "action": row.action,
        "target": row.target,
        "inputs_hash": row.inputs_hash,
        "decision": row.decision,
        "rule": row.rule,
        "reason": row.reason,
        "policy_refs": row.policy_refs,
        "result": row.result,
        "revocation_state": row.revocation_state,
        "guardrails_off": row.guardrails_off,
    }


def record(
    *,
    actor: str,
    action: str,
    target: str,
    inputs: dict[str, Any],
    decision: str,
    rule: str,
    reason: str = "",
    policy_refs: Iterable[str] = (),
    result: Any = "",
    revocation_state: str,
    guardrails_off: Iterable[str] = (),
) -> int:
    """Append one audit row and return its id."""
    with _lock, session_scope() as s:
        last = s.query(AuditLog.row_hash).order_by(AuditLog.id.desc()).first()
        prev_hash = last[0] if last else GENESIS
        row = AuditLog(
            ts=utcnow(),
            actor_agent=actor,
            action=action,
            target=target,
            inputs_hash=hash_inputs(inputs),
            inputs=canonical(inputs)[:4000],
            decision=decision,
            rule=rule,
            reason=reason,
            policy_refs=canonical(sorted(set(policy_refs))),
            result=result if isinstance(result, str) else canonical(result)[:4000],
            revocation_state=revocation_state,
            guardrails_off=canonical(sorted(set(guardrails_off))),
            prev_hash=prev_hash,
            row_hash="",
        )
        row.row_hash = _row_digest(prev_hash, _hashed_fields(row))
        s.add(row)
        s.flush()
        return row.id


def verify_chain() -> dict[str, Any]:
    with session_scope() as s:
        prev = GENESIS
        count = 0
        for row in s.query(AuditLog).order_by(AuditLog.id):
            count += 1
            if row.prev_hash != prev or row.row_hash != _row_digest(prev, _hashed_fields(row)):
                return {"ok": False, "rows": count, "first_bad_id": row.id}
            prev = row.row_hash
        return {"ok": True, "rows": count, "first_bad_id": None}


def to_dict(row: AuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "ts": row.ts.isoformat(),
        "actor_agent": row.actor_agent,
        "action": row.action,
        "target": row.target,
        "inputs_hash": row.inputs_hash,
        "inputs": row.inputs,
        "decision": row.decision,
        "rule": row.rule,
        "reason": row.reason,
        "policy_refs": json.loads(row.policy_refs),
        "result": row.result,
        "revocation_state": row.revocation_state,
        "guardrails_off": json.loads(row.guardrails_off),
        "prev_hash": row.prev_hash,
        "row_hash": row.row_hash,
    }


def query(
    *,
    actor: str | None = None,
    action: str | None = None,
    decision: str | None = None,
    rule: str | None = None,
    target: str | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    with session_scope() as s:
        stmt = s.query(AuditLog)
        if actor:
            stmt = stmt.filter(AuditLog.actor_agent == actor)
        if action:
            stmt = stmt.filter(AuditLog.action == action)
        if decision:
            stmt = stmt.filter(AuditLog.decision == decision)
        if rule:
            stmt = stmt.filter(AuditLog.rule == rule)
        if target:
            stmt = stmt.filter(AuditLog.target == target)
        if q:
            like = f"%{q}%"
            stmt = stmt.filter(
                or_(AuditLog.reason.like(like), AuditLog.result.like(like), AuditLog.inputs.like(like))
            )
        rows = stmt.order_by(AuditLog.id.desc()).limit(max(1, min(limit, 10000))).all()
        return [to_dict(r) for r in rows]


EXPORT_FIELDS = [
    "id", "ts", "actor_agent", "action", "target", "decision", "rule", "reason",
    "policy_refs", "result", "revocation_state", "guardrails_off", "inputs_hash",
    "prev_hash", "row_hash",
]


def export_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        r = dict(r)
        r["policy_refs"] = ";".join(r["policy_refs"])
        r["guardrails_off"] = ";".join(r["guardrails_off"])
        writer.writerow(r)
    return buf.getvalue()
