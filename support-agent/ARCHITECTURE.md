# Architecture: agents, tools and data access (least-privilege map)

Every principal, human or agent, reaches data only through tools, and every
tool call passes through `app/tools.py::invoke` → `app/policy_engine.py::evaluate`.
The grants below are defined once, immutably, in `app/permissions.py::TOOL_GRANTS`.

"Bound case" means the case id the orchestrator passes in. The tool layer
looks the customer up from that case in SQLite. A tool never accepts a
customer chosen by the LLM, except `create_case`, where the customer is the
submitter.

## Agents

### 1. Intake Agent (`app/agents/intake.py`, principal `intake_agent`)
Case submission and assignment.

| Tool | Kind | Data access |
|------|------|-------------|
| `create_case(customer_id, description, amount_requested)` | write | inserts one `cases` row for the submitting customer. Validates amount (0–10,000) and length. Flags likely duplicates (same customer and amount, ≥75% word overlap, 30 days). |
| `assign_case(agent?)` | write | bound case: `status new → assigned`, `assigned_agent` |
| `get_case(case_id?)` | read | bound case only |

### 2. Email Agent (`app/agents/email.py`, principal `email_agent`)
Draft, send and receive customer email (mock outbox and inbox in `emails`).

| Tool | Kind | Data access |
|------|------|-------------|
| `get_customer_contact()` | read | name + email of the bound case's customer |
| `draft_email(subject, body)` | read | preview only, recipient resolved by the tool |
| `send_email(subject, body, to?, notify_status?)` | write | inserts an `out` email. Recipient is always the bound customer, and a different `to` is refused. |
| `receive_emails()` | read | `in` emails of the bound case |

### 3. Records Agent (`app/agents/records.py`, principal `records_agent`)
Customer records: access, storage, retrieval. The highest-value target for
data exfiltration, so it is scoped tightest.

| Tool | Kind | Data access |
|------|------|-------------|
| `get_case(case_id?)` | read | bound case (+ its refund decision) |
| `get_customer_profile(customer_id?)` | read | bound customer. Bank account masked (`****1234`). |
| `search_records(query, limit≤5)` | read | vector search with a forced `customer_id` filter, post-filtered |
| `update_case_status(status, note?)` | write | bound case. Only `validated`, `acknowledged`, `awaiting_customer`, `closed`. Never decision statuses, never from supervisor states. |
| `store_customer_note(note)` | write | appends to the bound customer's `notes`, then re-indexes |

There is no list, enumerate or export tool. Such actions are refused as
`no_unrelated_record_export`.

### 4. Refunds Agent (`app/agents/refunds.py`, principal `refunds_agent`)
Refund request: submit, decide, process.

| Tool | Kind | Data access |
|------|------|-------------|
| `retrieve_policy(query, k≤8)` | read | `policies` collection only |
| `get_weekly_total()` | read | rolling 7-day approved total of the bound customer, from `refunds` |
| `decide_refund(proposed_decision, reason, policy_refs)` | write | inserts one `refunds` row for the bound case (amount taken from the case row, not from the model) or routes to `supervisor_review` |
| `process_refund()` | write | marks the bound case's approved refund processed and credits `customers.balance` |

It has no customer-profile or case-read tools. The orchestrator hands it the
case and profile that the Records Agent retrieved.

### 5. Reporting Agent (`app/agents/reporting.py`, principal `reporting_agent`)
Refund reporting: approved, denied, reason.

| Tool | Kind | Data access |
|------|------|-------------|
| `record_report_entry()` | write | inserts a `report_entries` row (outcome + reason) for the bound case, once per status |
| `get_refund_report()` | read | the bound customer's entries + weekly total |

Cross-customer aggregates (`/api/reports/*`) are served to the human operator
by the API, not through an agent tool.

## Human principals (not agents)

| Principal | Tools | Surface |
|-----------|-------|---------|
| `supervisor` | `supervisor_decide(decision, reason)`, `get_case` | `POST /api/cases/{id}/supervisor` |
| `admin` | `upload_policy(name, content)` | `POST /api/policies` |
| `operator` | none (kill switch is not a tool) | `POST /api/controls/revocation` |

No agent holds a human tool (`tests/test_no_self_permission_change.py::test_no_agent_holds_human_or_admin_tools`).

## Consequential vs read-only

Consequential tools (refused while authority is revoked): `create_case`,
`assign_case`, `update_case_status`, `store_customer_note`, `send_email`,
`decide_refund`, `process_refund`, `record_report_entry`, `supervisor_decide`,
`upload_policy`. All other tools are read-only and keep working under
revocation.

## Data stores

| Store | Contents | Written by |
|-------|----------|-----------|
| SQLite `customers` | name, email, bank account (fake), balance, notes | seed, `process_refund`, `store_customer_note` |
| SQLite `cases` | description, amount, status, duplicate flag, workflow bookkeeping | `create_case`, `assign_case`, `update_case_status`, `decide_refund`, `process_refund`, `supervisor_decide`, `send_email`, `record_report_entry` |
| SQLite `refunds` | decision, reason, policy refs, decided_by, processed | `decide_refund`, `supervisor_decide`, `process_refund` |
| SQLite `emails` | mock inbox/outbox | `send_email`, `POST /api/emails/inbound` |
| SQLite `report_entries` | outcome + reason per case status | `record_report_entry` |
| SQLite `audit_log` | append-only evidence | `tools.invoke`, `state.set_revocation`, seed |
| SQLite `system_state` | `revocation` flag, display-only weekly counters | operator, `process_refund` |
| Vector `policies` | policy chunks keyed `RP-x.y` | `upload_policy` (re-chunk + re-index) |
| Vector `records` | customer profile and case text, metadata `customer_id` | re-indexed after every customer/case write, and fully rebuilt at startup |

## Policy engine rule order

1. `no_self_permission_change`: protected action names (grant/permission/policy/guardrail/kill switch), or an agent calling `upload_policy`
2. `no_unrelated_record_export`: enumeration/export action names
3. `least_privilege`: tool exists and is granted to the actor
4. `revocation`: consequential tool while revoked
5. `no_unrelated_record_export`: case binding, bulk params, cross-customer ids, `limit`, email recipient
6. `invalid_arguments`: strict schema (types, enums, required, no extras)
7. Per-action rules: `create_case`, `update_case_status`, `decide_refund` (duplicate decision → supervisor lock → state → citations → duplicate request → weekly cap → single cap), `supervisor_decide`, `process_refund`, `upload_policy`

The first failing rule wins and is the `rule` recorded in the audit log.
