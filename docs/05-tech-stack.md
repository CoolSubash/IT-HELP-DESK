# 05 — Technology Stack

## Summary

| Layer | Choice | Alternative considered | Why this one |
|---|---|---|---|
| Primary database | **PostgreSQL 16** | MySQL, MongoDB | Strong relational integrity for tickets/users/devices/approvals; JSONB for flexible fields; mature, boring, well-understood |
| Vector search | **pgvector** extension on the same Postgres | Pinecone, Qdrant, Weaviate | Keeps embeddings transactionally consistent with the ticket/KB rows that reference them; one database to operate; sufficient performance at helpdesk scale (thousands–low millions of chunks) |
| Cache / job queue broker | **Redis** | RabbitMQ, SQS | Simple, doubles as cache for dashboard aggregates and broker for background jobs |
| Background jobs | **Celery** (Python) or **RQ** | BullMQ (Node) | Matches Python backend; used for email processing, embedding generation, agent runs |
| Object storage | **S3-compatible** (AWS S3 or MinIO for local dev) | Storing files in Postgres | Raw KB files (PDF/DOCX) shouldn't bloat the relational DB; Postgres stores only metadata + extracted text |
| Backend API | **Python 3.12 + FastAPI** | Node.js + NestJS | Best ecosystem for document parsing (`unstructured`, `pypdf`), embeddings, and the Anthropic SDK's tool-use loop |
| Agent / LLM | **Anthropic Claude** (Messages API, tool use) | OpenAI GPT | Already the working environment; native structured tool-calling with authorization gating fits FR-11–FR-13 directly |
| Embedding model | **Voyage AI** (`voyage-3`) or OpenAI `text-embedding-3-large` | Local sentence-transformers | Managed, no GPU infra to run; good retrieval quality for enterprise doc RAG |
| Frontend (Admin Dashboard) | **Next.js (App Router) + TypeScript + Tailwind + shadcn/ui** | Plain React + Vite | SSR for dashboard data, good DX, one of the most common stacks for internal admin tools |
| Auth (dashboard) | **JWT session cookies**, argon2/bcrypt password hashing | OAuth/SSO | Simple for v1; SSO (Okta/Azure AD) is a natural v2 add given "enterprise" framing |
| Inbound email | **Provider inbound-parse webhook** (Postmark Inbound, or AWS SES + SNS → HTTPS) | IMAP polling | Push-based, lower latency, no polling infra, built-in spam/parsing handling |
| Outbound email | Same provider's send API (Postmark / SES) | SMTP directly | Threading headers, delivery tracking, bounce handling come for free |
| Containerization | **Docker Compose** for local dev (postgres+pgvector, redis, minio, api, worker, web) | — | Standard, reproducible local environment before any cloud deploy decision |

## Why Postgres + pgvector specifically (expanded)

Your spec (`project.md` §8) explicitly separates three kinds of retrieval the agent must combine:

1. **RAG over company documentation** → embeddings over KB chunks.
2. **Historical ticket retrieval** → embeddings over past issue+resolution text.
3. **Structured queries** → users, tickets, devices, statuses, permissions.

All three are read together in a single agent turn ("find similar VPN tickets that are also
`Resolved` and belong to a `student` role"). Doing that as one SQL query against Postgres+pgvector
(`ORDER BY embedding <=> query_embedding LIMIT 5 WHERE status = 'Resolved'`) is simpler and more
consistent than round-tripping between a relational DB and a separate vector service and joining
the results in application code. If corpus size or query volume later outgrows pgvector, the
migration path is narrow and contained: `search_knowledge_base()` and `search_similar_tickets()`
are already the only call sites (see `04-api-design.md` §3), so the storage engine behind them can
change without touching the agent logic.

## Local dev environment (assumed shape)

```
docker-compose.yml
├── postgres (pgvector/pgvector:pg16 image)
├── redis
├── minio (S3-compatible, local KB file storage)
├── api        (FastAPI — dashboard REST API + inbound email webhook)
├── worker     (Celery — embedding jobs, agent runs, outbound email)
└── web        (Next.js dashboard)
```

Flag if you'd rather standardize on Node.js end-to-end (single language across web + API +
worker) — the DB/API designs in this doc set don't depend on the backend language, only the
tool-call contracts in `04-api-design.md` would need re-expressing in TypeScript signatures
instead of Python ones.
