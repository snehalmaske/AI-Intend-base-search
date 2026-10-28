"""SQLite data model (source of truth) via SQLAlchemy.

The vector store is only an index over these rows; every write lands here
first and is then re-indexed.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    bank_account: Mapped[str] = mapped_column(String(64))
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    type: Mapped[str] = mapped_column(String(32), default="refund")
    description: Mapped[str] = mapped_column(Text)
    amount_requested: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="new")
    assigned_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Workflow bookkeeping: which decision status the customer was told about,
    # and which was recorded by Reporting. Lets the orchestrator resume.
    notified_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reported_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    amount: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(16))  # approved | denied
    reason: Mapped[str] = mapped_column(Text)
    policy_refs: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    decided_by: Mapped[str] = mapped_column(String(64))  # refunds_agent | supervisor
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def policy_ref_list(self) -> list[str]:
        return json.loads(self.policy_refs or "[]")


class Email(Base):
    __tablename__ = "emails"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    direction: Mapped[str] = mapped_column(String(4))  # in | out
    address: Mapped[str] = mapped_column(String(200))  # recipient (out) / sender (in)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    """Append-only. UPDATE/DELETE are blocked by SQLite triggers and each row
    carries a hash chained to the previous row (tamper evidence)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor_agent: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128))
    inputs_hash: Mapped[str] = mapped_column(String(64))
    inputs: Mapped[str] = mapped_column(Text, default="{}")
    decision: Mapped[str] = mapped_column(String(16))  # allow | deny | escalate
    rule: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    policy_refs: Mapped[str] = mapped_column(Text, default="[]")
    result: Mapped[str] = mapped_column(Text, default="")
    revocation_state: Mapped[str] = mapped_column(String(16))  # active | revoked
    guardrails_off: Mapped[str] = mapped_column(Text, default="[]")
    prev_hash: Mapped[str] = mapped_column(String(64))
    row_hash: Mapped[str] = mapped_column(String(64))


class SystemState(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ReportEntry(Base):
    __tablename__ = "report_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    refund_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))  # approved | denied | supervisor_review | ...
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    content: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RagDocument(Base):
    """Backing table for the TF-IDF retriever (unused by the Chroma backend)."""

    __tablename__ = "rag_documents"
    collection: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


_APPEND_ONLY_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
       BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;""",
    """CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
       BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;""",
]

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_db(url: str | None = None) -> Engine:
    """Create (or re-create, in tests) the engine and schema."""
    global _engine, _SessionLocal
    url = url or settings.database_url
    if url.startswith("sqlite:///"):
        Path(url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    Base.metadata.create_all(_engine)
    with _engine.begin() as conn:
        for ddl in _APPEND_ONLY_TRIGGERS:
            conn.execute(text(ddl))
        conn.execute(
            text("INSERT OR IGNORE INTO system_state(key, value) VALUES ('revocation', 'active')")
        )
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_db()
    return _engine  # type: ignore[return-value]


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SessionLocal is None:
        init_db()
    session: Session = _SessionLocal()  # type: ignore[misc]
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mask_account(account: str) -> str:
    tail = account[-4:] if len(account) >= 4 else account
    return f"****{tail}"
