# 04 — API Design

Two distinct surfaces:

1. **Admin REST API** — consumed by the Next.js dashboard. Public-facing (behind auth), stable
   contract, versionable.
2. **Agent Tool Contracts** — internal Python function interfaces the agent orchestrator calls.
   Not HTTP endpoints; they run in-process in the `worker` service. Documented here as contracts
   because they are the authorization boundary described in `project.md` §9–10.

Plus one inbound webhook for email.

---

## 1. Auth

- `POST /api/auth/login` — `{ email, password }` → sets httpOnly JWT session cookie.
- `POST /api/auth/logout`
- `GET /api/auth/me` — returns current admin's identity + role.

All `/api/**` routes below except `/api/auth/login` and `/api/webhooks/*` require a valid admin
session. Superadmin-only routes are marked.

## 2. Admin REST API

### Dashboard
- `GET /api/dashboard/summary` → counts for FR-14 (open tickets, needs-attention, AI-resolved,
  investigating, avg resolution time, inbound volume, escalations).
- `GET /api/dashboard/trends?range=30d` → time series for resolution trend + common issue
  categories chart.

### Tickets
- `GET /api/tickets?status=&category=&priority=&assignee=&q=&page=&limit=` → paginated list.
- `GET /api/tickets/:id` → full detail: ticket fields, AI diagnosis/confidence, KB references,
  similar-ticket references, current `service_status`/`account_status` snapshot at diagnosis time,
  full `ticket_messages`, full `ai_actions` timeline (FR-16).
- `PATCH /api/tickets/:id` — `{ status?, priority?, assigned_admin_id? }` (FR-17).
- `POST /api/tickets/:id/notes` — `{ body_text }` → internal note (FR-17).
- `POST /api/tickets/:id/reply` — `{ body_text }` → admin's **portal reply** (FR-17). Inserts a
  `ticket_messages` row with `type=outbound_email, channel=portal, author_admin_id=<current admin>`,
  sets `tickets.status = Waiting for User`, then hands off to the same outbound email job agent
  replies use. This is distinct from an admin's **direct-email reply**, which never calls this
  endpoint — it arrives at `/api/webhooks/inbound-email` instead and is classified there (see §3).

### Approvals (sensitive actions)
- `GET /api/approvals?status=pending_approval` → the queue for FR-18.
- `POST /api/approvals/:action_id/approve` → triggers tool execution.
- `POST /api/approvals/:action_id/reject` — `{ reason }` → records rejection, re-notifies agent.

### Knowledge Base
- `GET /api/kb/documents?status=&category=&q=`
- `POST /api/kb/documents` — multipart upload → stores to S3, creates `kb_documents` row
  (`status=processing`), enqueues chunk+embed job.
- `GET /api/kb/documents/:id` → metadata + processing status + chunk count.
- `DELETE /api/kb/documents/:id` → removes file + chunks + embeddings.
- `POST /api/kb/documents/:id/reindex` → re-chunk/re-embed (e.g. after an embedding model change).

### Users & Devices
- `GET /api/users?q=&department=&role=`
- `GET /api/users/:id` → profile + ticket history.
- `GET /api/devices?user_id=&status=`
- `GET /api/devices/:id` → device detail + associated issue history.

### Search
- `GET /api/search?q=` → federated search across tickets, users, devices, KB documents,
  historical resolutions (FR-19). Implementation: parallel targeted queries (ticket_number exact
  match, user email/name ILIKE, kb_chunks full-text or vector search) merged and ranked, not a
  single generic full-text index across dissimilar tables.

### Admins (superadmin only)
- `GET /api/admins`
- `POST /api/admins`
- `PATCH /api/admins/:id`
- `DELETE /api/admins/:id`

## 3. Inbound Email Webhook

- `POST /api/webhooks/inbound-email` — signature-verified payload from the email provider
  (Postmark/SES format). Handler logic (see `02-architecture.md` §2 and §4a):
  1. Validate provider signature.
  2. Check `From` address against `admins` (FR-3a).
     - **Match** → this is an admin's direct-email reply. Resolve the existing ticket via
       threading headers, store `ticket_messages` row (`type=outbound_email, channel=email,
       author_admin_id`), set `tickets.status = Waiting for User`. **Do not** enqueue `agent.run`.
     - **No match** → normal student path: resolve/create user → resolve/create ticket via
       threading rules → store row (`type=inbound_email, channel=email, author_user_id`) →
       enqueue `agent.run`.
  3. Return `200`.

This endpoint must be idempotent on the provider's message id (NFR-3) — a retried webhook delivery
must not create a duplicate `ticket_messages` row, regardless of which branch above handled it.

## 4. Agent Tool Contracts

Every tool the agent may call, its classification, and its authorization rule. This table *is*
the enforcement point for `project.md` §9–10 — the tool execution layer checks `classification`
before running anything, regardless of what the LLM decides to call.

| Tool | Classification | Input | Output | Authorization rule |
|---|---|---|---|---|
| `search_knowledge_base(query, top_k)` | safe | query text | ranked KB chunks + doc metadata | none — read-only |
| `search_ticket_history(user_id)` | safe | user id | prior tickets for that user | none — read-only |
| `search_similar_tickets(issue_text, category?, top_k)` | safe | issue text, optional filters | ranked similar tickets | none — read-only |
| `get_user(email_or_id)` | safe | identifier | user profile | none — read-only |
| `get_user_devices(user_id)` | safe | user id | device list | none — read-only |
| `get_device_status(device_id)` | safe | device id | device status | none — read-only |
| `check_service_status(service_name)` | safe | service name | current status | none — read-only |
| `check_account_status(user_id)` | safe | user id | `active/suspended/disabled` | none — read-only |
| `check_permissions(user_id, resource)` | safe | user id, resource | permission set | none — read-only |
| `create_ticket(...)` | safe | ticket fields | ticket id | none — additive, reversible |
| `update_ticket(ticket_id, fields)` | safe | ticket id, fields | updated ticket | restricted to non-sensitive fields (status/category/priority) |
| `assign_ticket(ticket_id, admin_id)` | safe | ticket id, admin id | updated ticket | none |
| `add_ticket_note(ticket_id, text)` | safe | ticket id, text | note id | none |
| `send_email(ticket_id, body)` | safe | ticket id, body | message id | rate-limited per ticket to avoid loops |
| `resolve_ticket(ticket_id, resolution_summary)` | safe | ticket id, summary | updated ticket | none |
| `reset_credentials(user_id)` | **sensitive** | user id | result | requires `ai_actions.status = approved` row |
| `change_permissions(user_id, changes)` | **sensitive** | user id, changes | result | requires approval |
| `grant_system_access(user_id, system)` | **sensitive** | user id, system | result | requires approval |
| `disable_account(user_id)` | **sensitive** | user id | result | requires approval |
| `change_security_settings(user_id, changes)` | **sensitive** | user id, changes | result | requires approval |

Adding a new tool means adding one row to this table (and its `classification`) plus an
implementation — no change to the agent's core loop or the approval mechanism (NFR-6).

### Execution contract (all tools)

Every tool call, regardless of classification, results in exactly one `ai_actions` row:

- `safe` tool → row inserted with `status = executed` (or `failed`) *after* running, in the same
  transaction as the tool's side effect.
- `sensitive` tool → row inserted with `status = pending_approval` *before* anything runs; the
  actual mutation only happens after an admin's `approve` transitions the row to `approved`, which
  the worker picks up to execute, then updates to `executed`.

This guarantees FR-21 (nothing the agent does is unlogged) and NFR-2 (auditability) structurally,
not by convention.

## 5. Outbound Email

Not a public API — a worker job (`email.send`) that: renders the reply, sets `X-Ticket-Id` and
threading headers (`In-Reply-To` = last inbound `Message-ID`), sends via the provider, and writes
the resulting `ticket_messages` row with the provider's returned `Message-ID`.
