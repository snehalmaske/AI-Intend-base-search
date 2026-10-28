"""Every test gets a fresh SQLite DB, the TF-IDF retriever, the mock LLM and
the seed data. Guardrails start ON for every test."""
from __future__ import annotations

import pytest

from app import llm, rag
from app.config import GUARDRAIL_NAMES, settings
from app.db import Case, Customer, init_db, session_scope
from app.seed import seed

# Seeded demo case ids (see app/seed.py DEMO_CASES), in order.
ALICE_45, BRUNO_250, CARMEN_85, DMITRI_DUP, ESTHER_100, FARID_10001, GRACE_DENY = range(5, 12)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(settings, "chroma_dir", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "rag_backend", "tfidf")
    monkeypatch.setattr(settings, "mock_llm", True)
    monkeypatch.setattr(settings, "guardrails", {g: True for g in GUARDRAIL_NAMES})
    rag.reset_store()
    mock = llm.MockLLM()
    llm.set_llm(mock)
    init_db()
    seed(reset=False)
    yield mock
    llm.set_llm(None)
    rag.reset_store()


def case_row(case_id: int) -> Case:
    with session_scope() as s:
        return s.get(Case, case_id)


def balance(customer_id: int) -> float:
    with session_scope() as s:
        return s.get(Customer, customer_id).balance


def advance_to(case_id: int, status: str) -> None:
    """Run single steps until the case reaches ``status``."""
    from app.orchestrator import Orchestrator, next_step

    orch = Orchestrator()
    for _ in range(10):
        if case_row(case_id).status == status:
            return
        step = next_step(case_id)
        assert step, f"stuck at {case_row(case_id).status}"
        assert orch.run_step(case_id, step).ok
    raise AssertionError(f"never reached {status}")
