# 01 — Requirements

Source: `project.md`. This document restates that spec as concrete functional/non-functional
requirements, actors, and explicit assumptions, so design decisions downstream have something
precise to point back to.

## 1. Actors

| Actor | Access | Description |
|---|---|---|
| **Student / Employee** | Email only — never logs into any app | Sends issues to the IT support email address, receives AI or admin replies by email |
| **IT Administrator** | Web dashboard | Reviews tickets, approves/rejects sensitive AI actions, manages KB, manages users/devices |
| **Superadmin** (assumed) | Web dashboard | Everything an Administrator can do, plus manage other admin accounts |
| **AI Agent** | No direct human access; acts through authorized tools only | Automated actor that reads inbound email, investigates, and acts within its authorization boundary |

## 2. Functional Requirements

### 2.1 Email Ingestion & Threading
- FR-1: System ingests inbound email to a single IT support address.
- FR-2: System identifies the sending user by email address; if unknown, a minimal user record is created (or the message is routed to an "unrecognized sender" queue — see Open Question OQ-1).
- FR-3: A new inbound email either creates a new ticket or is appended to an existing ticket's conversation, based on email threading (`Message-ID` / `In-Reply-To` / `References` headers, with subject/ticket-token matching as fallback).
- FR-3a: On every inbound email, the sender address is checked against known admin accounts *before* the student-identification logic runs. A match means this is an admin's direct-email reply on an existing ticket (see FR-17a), not a new or continuing student message.
- FR-4: All inbound/outbound emails for a ticket are stored and viewable as a single conversation.
- FR-4a: A reply from an admin (via either channel) moves the ticket to `Waiting for User`; a new inbound student email moves it to `AI Investigating` (or `Waiting for Admin` if already escalated).

### 2.2 AI Agent Reasoning Loop
For every new inbound message, the agent must, in order:
1. Parse and understand the email.
2. Identify the user.
3. Classify the issue category.
4. Retrieve relevant KB chunks (RAG).
5. Retrieve the user's own ticket history.
6. Retrieve similar resolved tickets from other users.
7. Query structured data (user/device/service status) as needed.
8. Form a diagnosis with a confidence level.
9. Decide: respond automatically, take a safe tool action, propose a sensitive action for approval, or escalate to a human.
10. If a tool is called, verify the tool's result before using it in a response.
11. Send an email response and/or create an escalation.
12. Persist a full record of retrieved sources, reasoning, tool calls, and outcome.

- FR-5: Every AI decision must be explainable after the fact from stored data alone (no "black box" — diagnosis, confidence, sources, and actions must all be queryable per ticket).

### 2.3 RAG Knowledge Base
- FR-6: Admins can upload, view, delete, search, and re-index KB documents (PDF, DOCX, TXT, Markdown at minimum).
- FR-7: Uploaded documents are chunked and embedded asynchronously; the dashboard shows processing status (`Processing`, `Ready`, `Failed`) per document.
- FR-8: Every AI response/diagnosis records which KB documents/chunks contributed to it.

### 2.4 Historical Ticket Intelligence
- FR-9: The agent can retrieve a given user's prior tickets and surface repeat-issue patterns (e.g. "2 prior VPN issues, both resolved by certificate renewal").
- FR-10: The agent can retrieve similar tickets across *all* users via semantic similarity over issue+resolution text, independent of RAG document search.

### 2.5 Tool Calling & Authorization
- FR-11: The agent may only act through a fixed set of named, schema-validated tools (see `04-api-design.md` §3). No raw DB or infra access.
- FR-12: Each tool is classified `safe` (agent may execute autonomously) or `sensitive` (requires admin approval before execution).
- FR-13: Sensitive tool calls are recorded as a pending action; execution is blocked until an admin approves or rejects it. Rejection must be recorded with a reason and surfaced back into the agent's context for the ticket.

### 2.6 Administrator Dashboard
- FR-14: A summary view shows: open tickets, tickets needing attention, AI-resolved count, tickets under investigation, avg. resolution time, inbound email volume, escalation count, recent tickets, recent AI actions, common issue categories, and resolution trend over time.
- FR-15: A ticket list view supports filtering/sorting by status, category, priority, assignee, and date.
- FR-16: A ticket detail view shows every field listed in `project.md` §3 and §14: identity, AI diagnosis + confidence, KB sources, historical evidence, live system status snapshot, recommendation, required action, full conversation, and full AI activity timeline.
- FR-17: Admins can manually reassign, reprioritize, add internal notes, and reply to a ticket **directly from the portal** — the reply is composed in the dashboard UI and sent to the user by email.
- FR-17a: An admin may instead reply directly from their own email client (e.g. reply-all on the ticket's email thread, keeping the support alias as a recipient). This reply arrives at the same inbound channel a student's email would, and must be recognized as an admin reply (by matching the sender address against known admin accounts) rather than misfiled as a new customer message.
- FR-17b: Every ticket message — student email, AI-composed reply, admin portal reply, or admin direct-email reply — is stored in one unified, chronologically ordered conversation per ticket, tagged with who authored it and which channel it went through, so the dashboard shows one consistent thread regardless of how any given message was sent.
- FR-17c: When a human (admin) replies through either channel, the AI must not also send a competing reply to the same inbound message — a human response takes over the ticket.
- FR-18: A pending-approvals queue lists all sensitive actions awaiting a decision, with one-click approve/reject.
- FR-19: Global search covers ticket ID, user, email, issue text, device, KB documents, and historical resolutions.
- FR-20: Admins can view users (with department/role/status/ticket history) and devices (with type/OS/status/issue history).

### 2.7 Audit & Logging
- FR-21: Every AI action (tool call, decision, retrieval) is logged with timestamp, inputs, outputs, and reasoning summary, linked to its ticket.
- FR-22: Every admin action affecting a ticket, approval, or KB document is logged with the acting admin's identity and timestamp.

## 3. Non-Functional Requirements

- NFR-1 (Security): Sensitive tools (credential reset, permission change, account disable, security-setting change) are **never** auto-executed. Admin dashboard requires authentication; role-based access separates admin vs superadmin actions.
- NFR-2 (Auditability): Nothing the agent does is unrecoverable or unexplained — every action is logged before/after execution.
- NFR-3 (Reliability): Inbound email must not be lost or duplicated even if the agent or a downstream service fails mid-processing (idempotent ingestion, durable queue, retries).
- NFR-4 (Latency): Simple, high-confidence, safe-action tickets should get an initial AI response within a target of ~1–2 minutes of email receipt (async pipeline, not required to be synchronous with the inbound webhook).
- NFR-5 (Explainability): Confidence must be a first-class, stored value (not just present in a generated text blob) so the dashboard can filter/sort by it.
- NFR-6 (Extensibility): New tools, new KB document types, and new issue categories must be addable without schema migration for the core ticket/user/device model.
- NFR-7 (Data retention): Full conversation and AI action history must be retained for the ticket's lifetime plus a configurable retention period (assume 2 years unless told otherwise — OQ-2).

## 4. Out of Scope (v1)

- Students/employees never get dashboard accounts or a portal login — email is the only channel, per spec.
- Real-time chat/live agent handoff (email-only, not chat-based).
- Multi-tenant support (single organization per deployment, assumed).
- Mobile app.

## 5. Open Questions / Assumptions Made

| ID | Question | Assumption used in this design |
|---|---|---|
| OQ-1 | What happens on email from a completely unknown address? | Create a minimal user record from the email address; ticket proceeds normally, category `Unverified Sender` flag added for admin visibility. |
| OQ-2 | Data retention period? | 2 years, configurable. |
| OQ-3 | Single organization or multi-tenant? | Single organization/tenant for v1. |
| OQ-4 | Embedding/LLM provider? | Anthropic Claude for reasoning + tool use; a standard embedding model (e.g. Voyage AI or OpenAI text-embedding-3) for RAG — see `05-tech-stack.md`. |
| OQ-5 | Email transport (inbound/outbound)? | Provider inbound-parse webhook (e.g. Postmark/SES) rather than IMAP polling, for reliability and lower latency — see `05-tech-stack.md`. |

These are reasonable defaults to keep moving; flag any that should change before the DB/API design is finalized.
