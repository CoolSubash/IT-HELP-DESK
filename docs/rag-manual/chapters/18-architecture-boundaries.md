# Architecture Boundaries

## The rule, in phase7.md's own words

Section 22 states this project's architecture rule directly, and this manual has treated it as load-bearing throughout, not as a one-time design note:

| Layer | Responsibility |
|---|---|
| PostgreSQL | Application state + ticket history |
| Knowledge Base | Official IT documentation |
| RAG | Find relevant knowledge |
| Future AI Agent | Reason + decide + use tools + respond |

Three prohibitions follow directly from this table, quoted from phase7.md, each worth examining concretely rather than restating abstractly:

**"Do not make the AI responsible for basic retrieval."** Concretely, this would mean asking a language model to somehow search the knowledge base by reasoning about it in free text -- describing the corpus to an LLM and asking it to guess or recall which document is relevant -- rather than calling a deterministic, indexed, directly-testable vector query. That would be slower (an LLM call instead of a millisecond-scale indexed database query), less reliable (a model's free-text recall of "what's in the knowledge base" is not the same as actually querying it), unauditable (no score, no ranking, no way to test "did the right document come back" the way Chapter 16's evaluation harness does), and entirely unnecessary, since retrieval over a fixed corpus of embedded, indexed documents is a solved, mechanical problem that gains nothing from an LLM's judgment. This implementation's `retrieval_service.search()` is exactly that deterministic, testable, indexed query -- and it has no dependency on any LLM at all.

**"Do not store all ticket conversations as knowledge-base documents."** Chapter 3 covers this in full: nothing in `ingestion_service.py` accepts a `ticket_id` or any reference to ticket data, and the only two ways a row ever appears in `knowledge_documents` are an explicit admin upload through `POST /admin/knowledge` or the curated seed script. There is no automatic pipeline, scheduled job, or code path anywhere in this codebase that takes ticket or message content and turns it into a knowledge-base document.

**"Do not use RAG as a replacement for the ticket database."** `retrieval_service.search()` only ever queries `knowledge_chunks` joined to `knowledge_documents` -- it has no awareness that `tickets`, `messages`, or `ticket_events` exist at all. A specific ticket's own history is answered by the pre-existing, unchanged `ticket_service.get_ticket_history()`, a direct SQL lookup by `ticket_id` -- strictly more precise for that specific question than any similarity search could be, and this phase never attempts to duplicate or replace it.

## What this phase explicitly does not build, verified item by item

phase7.md section 23 lists nine things as out of scope for this phase. Here is that list, verbatim, with a direct confirmation against the actual codebase for each:

- **An AI agent.** Does not exist. There is no module, class, or function anywhere in this codebase that reasons about a student's message and decides on a course of action.
- **Automatic AI replies.** Does not exist. Nothing in this codebase generates text intended to be sent to a student.
- **Bedrock chat generation.** Bedrock *is* used in this phase -- but only for embeddings, via `bedrock-runtime`'s `InvokeModel` API against Titan Text Embeddings (Chapter 5). Nothing in this codebase calls a Bedrock *chat* or *text-generation* model, and nothing automatically triggers any Bedrock call as a side effect of a student's message arriving.
- **Ticket classification by AI.** Does not exist. Ticket `category` is still set exactly the way it was before this phase (student-provided, or defaulted by the email ingestion pipeline) -- nothing in this phase reads a ticket and assigns it a category using AI.
- **Automatic escalation.** Does not exist. `retrieval_service.search()` returns data; it never calls `ticket_service.update_ticket_status()` or any other mutating function. No RAG code path changes a ticket's status.
- **Email response generation.** Does not exist. The existing (pre-Phase-7) outbound email path, `app/email/service.py`'s `send_admin_reply()`, sends only what an admin explicitly wrote -- nothing from this phase's retrieval results is ever composed into an outbound email automatically.
- **Autonomous tools.** Does not exist. There is no tool-calling loop, no agent framework, and no mechanism anywhere in this codebase for an LLM to invoke actions.
- **Automatic ticket closure.** Does not exist, for the same reason as automatic escalation above: RAG code never mutates ticket state.
- **A human-approval workflow.** Does not exist, because there is nothing yet that needs approving -- no AI-generated action exists in this codebase for a human to approve or reject.

Every item on this list was checked directly against the actual source during this implementation, not assumed absent by omission.

## How a future AI agent phase will actually connect to what was built here

This phase deliberately does not speculate about how the eventual AI agent phase will be designed beyond what is directly implied by the interfaces this phase itself hands it -- but those interfaces are worth stating precisely, since they are the concrete payoff of everything documented in this manual.

A future agent, running inside this same FastAPI backend process (there is no reason for it to live anywhere else, and no reason to add an HTTP hop to talk to code in the same process), will:

1. Call `retrieval_service.search()` directly, in Python, to get `RETRIEVED KNOWLEDGE` -- the exact function this manual's Chapter 9 documents in full, already tested against 8 real tests covering ranking, filtering, and exclusion behavior.
2. Separately call the already-existing, unchanged `ticket_service.get_ticket_history()` to get `TICKET HISTORY` for the specific ticket in question.
3. Combine those two, plus the student's `CURRENT MESSAGE`, into whatever context format that future phase's own requirements determine is appropriate -- a decision this phase deliberately leaves open, per Chapter 11's discussion of why `build_rag_context()` stops exactly where it does.
4. Only at that point involve an LLM -- for reasoning, deciding what (if anything) to do, and drafting a response. Not for retrieval, which by the time that phase begins is already a solved, deterministic, separately-tested problem (Chapters 9 and 16), with no need for an LLM's involvement at all.

Everything documented in this manual exists to make step 1 of that future sequence something the next phase's author can simply call, trust, and build on -- rather than something they need to design, implement, or re-verify from scratch.
