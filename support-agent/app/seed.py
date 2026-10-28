"""Seed synthetic data: customers, refund history, one policy, demo cases.

    python -m app.seed            # reset DB + vector store, then seed
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path

from . import audit, rag
from .agents import IntakeAgent
from .config import BASE_DIR, settings
from .db import Case, Customer, Email, Refund, ReportEntry, init_db, session_scope, utcnow
from .tools import invoke

POLICY_FILE = BASE_DIR / "data" / "policies" / "refund_policy.md"

CUSTOMERS = [
    # name, email, fake bank account, starting balance
    ("Alice Archer", "alice.archer@example.test", "SYN-ACCT-4410-2201", 1250.00),
    ("Bruno Bianchi", "bruno.bianchi@example.test", "SYN-ACCT-4410-2202", 310.40),
    ("Carmen Cruz", "carmen.cruz@example.test", "SYN-ACCT-4410-2203", 87.15),
    ("Dmitri Dale", "dmitri.dale@example.test", "SYN-ACCT-4410-2204", 2045.99),
    ("Esther Evans", "esther.evans@example.test", "SYN-ACCT-4410-2205", 560.00),
    ("Farid Faraday", "farid.faraday@example.test", "SYN-ACCT-4410-2206", 15.75),
    ("Grace Gill", "grace.gill@example.test", "SYN-ACCT-4410-2207", 980.20),
]

# Already-processed refunds: (customer index, amount, description, days ago)
HISTORY = [
    (2, 240.00, "Smart thermostat stopped working after two days; replacement unavailable.", 2),
    (2, 200.00, "Charged twice for annual cloud backup plan (billing error).", 4),
    (3, 60.00, "Wireless earbuds arrived with a cracked charging case.", 3),
    (1, 80.00, "Desk lamp delivered with a broken switch.", 20),  # outside the 7-day window
]

# New cases submitted through the Intake Agent: (customer index, amount, description)
DEMO_CASES = [
    (0, 45.00, "The blender I ordered arrived with a cracked jug. Photos attached. Please refund."),
    (1, 250.00, "My ergonomic laptop stand never arrived; tracking has shown 'in transit' for 3 weeks."),
    (2, 85.00, "Noise-cancelling headphones are defective: the left ear cup cuts out constantly."),
    (3, 60.00, "Wireless earbuds arrived with a cracked charging case."),  # duplicate of history
    (4, 100.00, "I was billed twice for my monthly streaming subscription this month."),
    (5, 100.01, "Service outage prevented me from using the paid video-conference plan all week."),
    (6, 30.00, "I just changed my mind about the scarf, I wore it once but no longer want it."),
]


def reset_storage() -> None:
    if settings.database_url.startswith("sqlite:///"):
        db = Path(settings.database_url.replace("sqlite:///", "", 1))
        for suffix in ("", "-wal", "-shm"):
            Path(f"{db}{suffix}").unlink(missing_ok=True)
    shutil.rmtree(settings.chroma_dir, ignore_errors=True)
    rag.reset_store()


def seed(reset: bool = True, policy_path: Path = POLICY_FILE) -> dict:
    if reset:
        reset_storage()
    init_db()

    up = invoke("admin", "upload_policy", params={"name": "refund_policy.md",
                                                  "content": policy_path.read_text()})
    if not up.ok:
        raise RuntimeError(f"policy upload refused: {up.verdict.reason}")

    now = utcnow()
    with session_scope() as s:
        customers = [Customer(name=n, email=e, bank_account=b, balance=bal) for n, e, b, bal in CUSTOMERS]
        s.add_all(customers)
        s.flush()
        for idx, amount, desc, days in HISTORY:
            when = now - timedelta(days=days)
            cust = customers[idx]
            case = Case(customer_id=cust.id, description=desc, amount_requested=amount,
                        status="processed", assigned_agent="refunds_agent", created_at=when,
                        notified_status="approved", reported_status="processed")
            s.add(case)
            s.flush()
            refund = Refund(case_id=case.id, customer_id=cust.id, amount=amount, decision="approved",
                            reason="Historical refund (seed data)", policy_refs=json.dumps(["RP-1.2"]),
                            decided_by="refunds_agent", processed=True, processed_at=when, created_at=when)
            s.add(refund)
            s.flush()
            s.add(ReportEntry(case_id=case.id, customer_id=cust.id, refund_id=refund.id,
                              outcome="approved", amount=amount, reason=refund.reason, created_at=when))
        customer_ids = [c.id for c in customers]

    audit.record(actor="seed", action="seed_data", target="database",
                 inputs={"customers": len(CUSTOMERS), "history": len(HISTORY)},
                 decision="allow", rule="seed_data", reason="synthetic seed data loaded",
                 result="ok", revocation_state="active")
    rag.reindex_all()

    intake = IntakeAgent()
    created = []
    for idx, amount, desc in DEMO_CASES:
        res = intake.submit(customer_ids[idx], desc, amount)
        created.append(res.data.get("case_id"))

    with session_scope() as s:  # one inbound email to exercise the mock inbox
        s.add(Email(case_id=created[0], direction="in", address=CUSTOMERS[0][1],
                    subject="Re: cracked blender jug", body="Just checking on my refund. Thanks!"))

    return {"customers": len(customer_ids), "demo_cases": created,
            "policy_chunks": len(up.data["chunks"]), "rag_backend": rag.get_store().backend}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-reset", action="store_true", help="keep existing data")
    args = parser.parse_args()
    print(json.dumps(seed(reset=not args.no_reset), indent=2))
