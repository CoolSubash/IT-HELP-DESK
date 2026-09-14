# System Context

## The application before this phase

By the time Phase 7 began, the AI IT Helpdesk Agent was already a working, tested, five-phase application. Understanding what already existed matters because phase7.md is explicit about a rule this manual takes seriously throughout: **do not redesign what already works.** Every design decision in this phase either reuses existing infrastructure directly or extends it in a way that's consistent with how the rest of the codebase is already built.

What already existed, in outline:

```text
Student
   |
   v
Email
   |
   v
Amazon SES
   |
   v
S3
   |
   v
Lambda
   |
   v
FastAPI
   |
   v
PostgreSQL
```

And, inside that FastAPI + PostgreSQL backend, a working system supporting:

- **Users** -- students and staff identified by email, no login (see the Security chapter for why this matters to Phase 7's own authorization design).
- **Tickets** -- one row per IT issue, with a status transition graph (`NEW -> AI_INVESTIGATING -> ... -> RESOLVED -> CLOSED`, with reopen edges), category, priority, and assignment to an admin.
- **Messages** -- the full conversation on a ticket, inbound and outbound, with email threading headers.
- **Ticket events** -- an append-only audit trail of every status change, assignment, and reopening.
- **Email threading** -- matching an inbound reply to the right existing ticket via `In-Reply-To`, `References`, thread ID, or an explicit ticket number in the subject line, in that priority order.
- **Ticket status** -- the full state machine described above, already tested against real transition rules.
- **Admin dashboard** -- a Next.js frontend for IT staff to view and manage tickets.
- **Inbound email processing** -- SES/Lambda-based ingestion turning an inbound email into a ticket or a reply on an existing one.
- **Ticket history** -- a merged, chronological view of messages, events, and (eventually) AI actions per ticket.

None of this changed in Phase 7. Not one existing migration was modified, not one existing service function's behavior changed, and not one existing endpoint's contract changed. The `knowledge_documents` table already existed (as a placeholder, with no rows ever written to it) from the very first migration in this project -- Phase 7's job was to finish what that placeholder was waiting for, not to redesign it.

## Where RAG fits

The objective for this phase, stated directly in phase7.md, is to build the retrieval layer that will eventually sit between "a student sends a message" and "the (future) AI agent responds":

```text
Student Message
       |
       v
    FastAPI
       |
       v
Current Ticket
       +
Ticket History
       |
       v
 RAG Retrieval
       |
       v
Relevant Knowledge
       |
       v
Future AI Agent
```

This phase builds exactly the "RAG Retrieval" box and the "Relevant Knowledge" it produces. It deliberately stops there. The arrow from "Relevant Knowledge" into "Future AI Agent" exists in this diagram, and this phase makes sure the data on the near side of that arrow (the retrieved knowledge, in a clean, documented JSON shape) is ready and correct -- but nothing on the far side of that arrow was built. There is no AI agent in this codebase. There is no code path anywhere that takes a retrieved chunk and turns it into a reply a student would see.

## What "knowledge base" means here, concretely

The knowledge base is the IT department's own documentation -- the kind of internal reference material an experienced help-desk staffer already has memorized, written down so a system (eventually, an AI agent; for now, an admin using the search preview endpoint) can look it up. The eight example documents seeded into this project's knowledge base (`backend/seed/knowledge_docs/*.md`) are representative of exactly this kind of material:

```text
VPN Troubleshooting Guide
WiFi Troubleshooting Guide
Password Reset Procedure
Student Account Setup
Microsoft Office Installation
Campus Network Guide
Printer Troubleshooting
Known IT Issues
```

This is categorically different from a ticket. A ticket is a record of one specific incident involving one specific person. A knowledge document is a piece of institutional knowledge that applies to every future incident of a similar kind. Chapter 3 makes this distinction precise, because getting it wrong -- for instance, by treating old resolved tickets as knowledge-base documents -- is exactly the mistake phase7.md warns against, and one this implementation was careful to avoid.

## The technology choices this phase made, and why they were already decided

Two of Phase 7's biggest architectural decisions were effectively already made before this phase started, by earlier planning documents in this same project:

- **`docker-compose.yml`** (written in Phase 1) already pins the `pgvector/pgvector:pg16` image for the local Postgres container, with a comment explicitly noting: *"We use the pgvector image... even though Phase 1 doesn't use vector columns yet: RAG (a later phase) will need the `vector` extension, and pinning the image now avoids swapping the base image... later."* This phase's vector storage decision (Chapter 6) was already anticipated and prepared for.
- **`docs/05-tech-stack.md`** (also written before this phase) already lays out the reasoning for PostgreSQL + pgvector over a separate vector database, and already names Amazon Bedrock as the intended embedding provider, consistent with the project's broader AWS-native direction (SES for email, Lambda for ingestion). This phase's embedding provider decision (Chapter 5) confirms and implements that earlier direction rather than deciding it fresh.

Both of these are called out here because a system context chapter should be honest about what was actually a decision made *in* this phase versus a decision *inherited* by this phase. The two most consequential infrastructure choices in this manual -- Postgres+pgvector for storage, and Bedrock for embeddings -- were both already settled by the time implementation began. What Phase 7 actually decided was everything *around* those two anchors: how documents are chunked, how the embedding provider is abstracted so it can be swapped, how failures are handled, how versioning works, how retrieval is scoped and filtered, and how the whole thing is tested and evaluated.

## A map of what changed on disk

For orientation, everything Phase 7 added or touched, grouped by kind:

```text
backend/
  app/
    rag/                        NEW -- the entire RAG subsystem (see Chapters 4-9)
    auth.py                     NEW -- admin authorization stand-in (see Chapter 12)
    routers/knowledge.py        NEW -- the admin HTTP API (see Chapter 8)
    schemas/
      knowledge_document.py     EXTENDED -- two new columns added
      knowledge_chunk.py        NEW
      knowledge_search.py       NEW
    config.py                   EXTENDED -- RAG-specific settings added
    database.py                 EXTENDED -- pgvector type registration added
    errors.py                   EXTENDED -- ValidationError added
    main.py                     EXTENDED -- new router + exception handler wired in
  migrations/
    0006_knowledge_chunks_and_vector.sql   NEW
  seed/
    knowledge_docs/*.md         NEW -- 8 example documents
    seed_knowledge_base.py      NEW
  scripts/
    evaluate_retrieval.py       NEW
  tests/
    test_rag_chunking.py        NEW
    test_rag_embeddings.py      NEW
    test_rag_extraction.py      NEW
    test_rag_ingestion.py       NEW
    test_rag_retrieval.py       NEW
    test_knowledge_api.py       NEW
  requirements.txt              EXTENDED -- python-multipart, pgvector, pypdf, python-docx
  requirements-dev.txt          EXTENDED -- reportlab (test-fixture generation only)
  .env.example                  EXTENDED -- RAG settings documented
docs/
  rag-manual/                   NEW -- this manual
.gitignore                      EXTENDED -- local knowledge-file storage excluded
README.md                       EXTENDED -- a Phase 7 section added
```

Every one of these is explained in the chapters that follow, in the order a reader building an understanding of the system from scratch would actually want them.
