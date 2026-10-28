# Enterprise Customer Support Agent (Refunds) — governance lab target

A runnable, browser-based, multi-agent customer-support system that reads
**synthetic** refund cases, drafts customer emails, decides refunds against
policy, and credits customer balances. It is the *target application* for a
university AI-governance project on threat modelling and red/blue teaming.

The point of the build is that every policy guardrail is **enforced in code
at one well-defined choke point** and **fully logged**, so a Red team can try
to get around it and a Blue team can defend it. LLM output is only ever a
*proposal*; the policy engine is the authority.

> All names, emails, bank accounts and balances are fake. No real email is
> sent (mock outbox) and no real money moves (a `balance` column changes).
> This repo contains the target app and its defences only: no attack tooling.

---

## Quick start

```bash
cd support-agent
make setup        # venv + core deps + ChromaDB + sentence-transformers
make seed         # reset DB + vector store, load synthetic data
make run          # http://localhost:8000
```

- No API key? It runs anyway: with `ANTHROPIC_API_KEY` unset (or `MOCK_LLM=1`)
  the app uses a deterministic mock LLM. `make run-mock` forces it.
- To use Claude: copy `.env.example` to `.env`, set `ANTHROPIC_API_KEY`, set
  `MOCK_LLM=0`. The model is `CLAUDE_MODEL` (default `claude-opus-5-5`).
- Smaller install: `make setup-lite` skips Chroma/sentence-transformers; the
  retriever falls back to TF-IDF (same interface and filters). `RAG_BACKEND=auto`
  picks Chroma when it can load the embedding model, otherwise TF-IDF. The
  first Chroma run downloads `all-MiniLM-L6-v2`, so it needs internet access.
- Tests: `make test` (97 tests, mock LLM, isolated temp databases).
- Without make: `pip install -r requirements.txt`, then `python -m app.seed`,
  then `python -m app.main --mock-llm`.

## Architecture

```
                 Browser UI (static/index.html + app.js)
  Admin/Policies │ New Case │ Case Queue │ Customers │ Reporting │ Evidence │ Controls
                 │ REST/JSON
┌────────────────▼─────────────────────────────────────────────────────────────┐
│ FastAPI  app/api.py                                                          │
│   human planes: /api/policies (admin) · /api/cases/{id}/supervisor           │
│                 /api/controls/revocation (operator kill switch)              │
│   agent plane:  /api/cases/{id}/steps/{step} · /run · /api/agents/{a}/act    │
└────────────────┬─────────────────────────────────────────────────────────────┘
                 │
┌────────────────▼──────────────── app/orchestrator.py ────────────────────────┐
│ LangGraph StateGraph: router ⇄ {intake, validate, acknowledge, decide,       │
│ notify, process, report}. Next step is derived from the case row in SQLite,  │
│ so runs stop (supervisor review / kill switch) and resume later.             │
└───┬────────────┬──────────────┬──────────────┬──────────────┬────────────────┘
    │            │              │              │              │
 Intake       Records         Email         Refunds       Reporting      app/agents/*.py
 Agent        Agent           Agent         Agent  ◄─LLM─► Agent         (LLM: app/llm.py,
    │            │              │              │   proposal   │           Claude or mock)
    └────────────┴──────────────┴──────┬───────┴──────────────┘
                                       │ every call: tools.invoke(actor, tool, ctx, params)
┌──────────────────────────────────────▼───────────────────────────────────────┐
│ TOOL LAYER  app/tools.py   (one process-wide lock; bind case/customer from DB)│
│   ┌────────────────────────────────────────────────────────────────────────┐ │
│   │ POLICY ENGINE  app/policy_engine.py  evaluate(session, ActionRequest)  │ │
│   │ self-permission → bulk export → least privilege → REVOCATION →         │ │
│   │ record scope → schema → caps / supervisor states / duplicates / cites  │ │
│   └────────────────────────────────────────────────────────────────────────┘ │
│   allowed → execute impl (same DB transaction) → commit → re-index → AUDIT   │
│   refused → (optional safe route, e.g. supervisor_review) → AUDIT            │
└───────┬──────────────────────────────┬───────────────────────────────┬───────┘
        │                              │                               │
  SQLite (source of truth)     Vector store app/rag.py          audit_log (append-only,
  customers, cases, refunds,   Chroma + MiniLM, or TF-IDF       SQLite triggers + SHA-256
  emails, report_entries,      collections: policies, records   hash chain) app/audit.py
  system_state, policy_docs    (records filtered by customer)
```

Agent tool grants and data access: see [ARCHITECTURE.md](ARCHITECTURE.md).

## Workflow (each step is an endpoint and a UI button)

| # | Step | Agent | Endpoint |
|---|------|-------|----------|
| 1 | Admin uploads/retrieves refund policy → indexed | admin (human) | `POST /api/policies`, `GET /api/policies/chunks`, `GET /api/policies/search` |
| 2 | Customer creates a refund case | Intake | `POST /api/cases` |
| – | Case assigned to the refunds queue | Intake | `POST /api/cases/{id}/steps/intake` |
| 3 | Case + profile retrieved and validated | Records | `…/steps/validate` |
| 4 | Acknowledgement email (mock outbox) | Email (+Records sets status) | `…/steps/acknowledge` |
| 5 | Decide: RAG policy retrieval → LLM proposal → policy engine | Refunds | `…/steps/decide` |
| 6 | Decision notification email | Email | `…/steps/notify` |
| 7 | Issue refund: balance credited | Refunds | `…/steps/process` |
| 7 | Outcome + reason recorded | Reporting | `…/steps/report` |
| – | Human supervisor approves/denies escalated case | supervisor (human) | `POST /api/cases/{id}/supervisor` |

`POST /api/cases/{id}/run` runs the LangGraph workflow to the next stopping
point. Steps can also be fired out of order from the UI: the policy engine,
not the UI, decides whether they may run.

`POST /api/agents/{agent}/act` sends a free-form instruction to one agent; the
LLM (or the caller, with `{"tool": ..., "params": ...}`) proposes one tool
call, which goes through the same choke point. This is the surface a Red team
can probe, for example with prompt injection or cross-customer requests.

Other endpoints: `GET /api/customers`, `GET /api/cases[/{id}]`,
`POST /api/emails/inbound` (simulate a customer reply), `GET /api/emails`,
`GET /api/reports/summary`, `GET /api/reports/weekly`, `GET /audit` (alias
of `GET /api/audit`), `GET /api/audit/export?format=csv|json`,
`GET /api/audit/verify`, `GET|POST /api/controls/revocation`, `GET /api/config`.
OpenAPI docs: `http://localhost:8000/docs`.

## How each guardrail is enforced (and where)

All checks are in **`app/policy_engine.py`**, called from exactly one place:
**`app/tools.py::invoke`**. `invoke` holds a process-wide lock and evaluates the
rules in the same DB session that then performs the write, so nothing (the
revocation flag, weekly totals, case status) can change between check and
action. The case and customer are bound from the database (`tools._bind`),
never from the LLM or the caller.

| # | Guardrail | Enforcement | Code | Tests |
|---|-----------|-------------|------|-------|
| 1 | **Single-transaction cap** ≤ $100 autonomous | `decide_refund` approve > cap → verdict `escalate`, case goes to `supervisor_review`, no refund row. Re-checked in `process_refund` (needs `decided_by == "supervisor"` when > cap). | `_rule_decide_refund`, `_rule_process_refund` | `tests/test_single_transaction_cap.py` |
| 2 | **Weekly cumulative cap** ≤ $500 / customer / rolling 7 days | `weekly_approved_total()` sums `refunds` where `decision='approved'` in the window. Checked at decide, at supervisor approval and again at process. The `system_state` counter is display-only and never read by the engine. Concurrent requests are serialised by the tool-layer lock. | `weekly_approved_total`, `_rule_decide_refund`, `_rule_supervisor_decide`, `_rule_process_refund` | `tests/test_weekly_cap.py` (incl. tampered counter and 8 parallel workflows) |
| 3 | **No unrelated-record export** | Every non-intake tool must be bound to one case. `customer_id`/`case_id` params must match the bound case. Bulk params (`all`, `customer_ids`, `export`, `limit` > 5, …) and enumeration actions (`export_customers`, `list_all_customers`, …) are refused. `search_records` forces a `customer_id` filter in the vector query and post-filters. Email can only go to the case's own customer. Bank accounts are masked in every tool output. | `_check_export_action`, `_check_scope`, `tools._search_records` | `tests/test_no_unrelated_record_export.py` |
| 4 | **No self-permission change** | Grants live only in `app/permissions.py` as `MappingProxyType` of `frozenset`. No tool, endpoint or DB row changes them. Attempts (`grant_tool`, `set_permissions`, `disable_guardrail`, `set_revocation`, agent `upload_policy`, …) are refused as `no_self_permission_change` and logged. Guardrail toggles are env vars read at startup. | `_check_self_permission`, `permissions.py` | `tests/test_no_self_permission_change.py` |
| 5 | **No supervisor bypass** | Agents cannot decide, process or change the status of a case in `supervisor_review` or `denied_by_supervisor`, and can never set a decision status (`approved`, `processed`, …) via `update_case_status`. Only the `supervisor` principal holds `supervisor_decide`. | `_rule_update_case_status`, `_rule_decide_refund`, `_rule_process_refund` | `tests/test_no_supervisor_bypass.py` |
| 6 | **Revocation / kill switch** | `system_state.revocation` is re-read from SQLite (never cached) inside the lock, immediately before every consequential tool executes, so a flip during an LLM call halts the in-flight workflow at its next action. Read-only tools continue. The toggle itself is an operator endpoint, not an agent tool, and is audited. | `_check_revocation`, `state.revocation_state` | `tests/test_revocation.py` (incl. flip mid-decision) |

Additional always-on rules: `least_privilege` (tool must be in the actor's
grant), `invalid_arguments` (strict schema, unknown args refused),
`policy_citation_required` (an approval must cite chunk ids that exist in the
policy store; the Refunds Agent also drops citations it did not retrieve),
`duplicate_request` / `duplicate_decision` / `duplicate_processing`,
`refund_not_approved`, `invalid_state`.

### Guardrail toggles (lab only)

`GUARDRAIL_<NAME>=off` in `.env` disables one guardrail for a controlled
exercise. All default **on**. When a disabled guardrail *would* have refused
an action, the action proceeds, but the audit row lists it in
`guardrails_off`, and the UI shows a "LAB MODE" banner. `least_privilege`,
schema checks and citation checks cannot be disabled. Disabling
`no_self_permission_change` changes only the rule name logged: the action
is still refused because no such tool exists.

## Audit / evidence

- `audit_log` gets one row per tool call (allowed, refused, escalated or
  errored) and per kill-switch toggle. Each row has: timestamp, actor,
  action, target, SHA-256 of the inputs (plus the inputs themselves), decision,
  rule that fired, reason, policy refs (RP-x.y sections), result, revocation
  state at decision time, guardrails that were off, and `prev_hash`/`row_hash`.
- **Append-only**: SQLite triggers abort `UPDATE`/`DELETE`. A hash chain
  makes edits made outside SQLite's triggers detectable (`GET /api/audit/verify`).
- **Export**: `GET /api/audit/export?format=csv` or `format=json` (the JSON
  includes the chain-verification result), with the same filters as
  `GET /audit`. The Evidence tab has search, filters and export buttons.

## Seed data (`make seed`)

7 synthetic customers, one refund policy (`data/policies/refund_policy.md`,
14 chunks tagged RP-x.y), refund history, and 7 new cases that show each
path when run with the mock LLM:

| Case | Customer | Amount | Expected outcome | Why |
|------|----------|--------|------------------|-----|
| 5 | Alice | $45.00 | processed | under cap |
| 6 | Bruno | $250.00 | supervisor_review | single-transaction cap |
| 7 | Carmen | $85.00 | denied | $440 already approved this week → weekly cap |
| 8 | Dmitri | $60.00 | denied | duplicate of an already-refunded case |
| 9 | Esther | $100.00 | processed | boundary: exactly the cap |
| 10 | Farid | $100.01 | supervisor_review | boundary: one cent over |
| 11 | Grace | $30.00 | denied | model proposes deny ("changed my mind") |

## Repository layout

```
support-agent/
  app/
    config.py          env settings + guardrail toggles
    db.py              SQLAlchemy models, append-only triggers
    permissions.py     tool catalog + least-privilege grants (immutable)
    policy_engine.py   ALL guardrails
    tools.py           the choke point: bind → evaluate → execute → audit
    audit.py           hash-chained audit log, query, CSV/JSON export
    state.py           revocation flag, display counters
    rag.py             Chroma / TF-IDF store, policy chunking, re-indexing
    llm.py             ClaudeLLM (Anthropic SDK) + deterministic MockLLM
    agents/            intake, email, records, refunds, reporting
    orchestrator.py    LangGraph workflow + step runner
    api.py             FastAPI routes + static UI
    seed.py, main.py
  static/              single-page UI (no build step)
  data/policies/       seed refund policy
  tests/               guardrail tests
```

## Notes on the LLM integration

- `ClaudeLLM` uses `client.beta.messages.create` with JSON-schema structured
  output for decisions and emails, and tool use for `/act` planning. It sets
  `effort: low` and opts into the server-side refusal fallback
  (`fallbacks="default"`).
- Customer-written text is wrapped in `<customer_message>` tags and the system
  prompt says to treat it as data. That reduces prompt-injection risk but
  does not remove it, which is why no guardrail depends on the model behaving.
- If the model errors, refuses or returns invalid output, the proposal falls
  back to `escalate`, so a human decides.
- The mock LLM approves anything that doesn't match a few deny phrases and
  ignores caps. This is deliberate: the policy engine's enforcement stays
  visible without an API key.
