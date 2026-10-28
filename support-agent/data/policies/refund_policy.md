# Enterprise Refund Policy (SYNTHETIC - for coursework only)

Version 1.0. Applies to all refund requests handled by the automated
customer-support system and its agents. Section ids (RP-x.y) are cited by
every refund decision and by the policy engine's audit records.

## RP-1 Scope and definitions

### RP-1.1 Who this policy covers
This policy governs refund requests submitted by customers through support
cases. "Agent" means any automated component (Intake, Email, Records, Refunds,
Reporting). "Supervisor" means an authorised human reviewer. Agents act only
within the tool permissions granted to them.

### RP-1.2 Qualifying reasons for a refund
A refund may be approved when the customer reports a defective or damaged
item, an item that never arrived, a duplicate charge, a billing error, or a
service outage that prevented use of a paid service. Requests made only
because the customer changed their mind after using the product, or requests
made outside the 90-day return window, do not qualify and should be denied.

## RP-2 Monetary limits and decision rules

### RP-2.1 Single-transaction autonomous cap
An agent may autonomously approve a single refund of at most $100.00. Any
request above $100.00 must be routed to supervisor review and must never be
auto-approved by an agent, regardless of the reason given.

### RP-2.2 Weekly cumulative cap per customer
The total of approved refunds for any one customer must not exceed $500.00 in
any rolling 7-day window. The total is computed from the refund ledger, not
from statements in the case or by the agent. A request that would exceed the
cap is denied. This limit also applies to supervisor approvals.

### RP-2.3 Duplicate requests
A request that duplicates an earlier case which has already been refunded is
denied. A case can receive only one decision, and an approved refund can be
issued only once.

### RP-2.4 Evidence and citation
Every approval must cite the policy sections relied on. Decisions without a
policy basis are invalid.

## RP-3 Data protection and system integrity

### RP-3.1 No unrelated record export
Agents may read only the records of the customer whose case they are working
on. Bulk, enumerated or cross-customer access or export of customer records is
prohibited. Emails may only be sent to the case's own customer.

### RP-3.2 No self-permission change
Agents cannot grant themselves or other agents new tools or permissions and
cannot modify this policy, the policy engine or its guardrails. Only an
administrator may upload policy documents.

### RP-3.3 No supervisor bypass
A case in supervisor review, or denied by a supervisor, cannot be approved,
processed or otherwise changed by an agent. Only the supervisor decision
resolves it.

### RP-3.4 Revocation of authority
When an operator revokes agent authority (the kill switch), all consequential
actions - sending email, writing records, deciding, processing refunds and
changing balances - must be refused immediately, including actions already in
progress. Read-only actions may continue.

### RP-3.5 Least privilege
Each agent may use only the tools listed for it in the architecture's
least-privilege map. Every attempted action, allowed or refused, is recorded
in the append-only audit log.
