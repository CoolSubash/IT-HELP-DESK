# Ticket History vs. RAG

## Why this distinction gets its own chapter

phase7.md calls this distinction "critical," and it is worth taking that word seriously before writing a single line of code, because it's the single easiest mistake to make when building a RAG system on top of an application that already has a rich history of past interactions. It would be tempting -- and wrong -- to think "we already have a database full of past tickets and their resolutions, why not just embed all of that and call it the knowledge base?" This chapter explains precisely why that would be wrong, and how this implementation avoids it.

## Two different questions

Every retrieval system answers some question about "what is relevant right now." In this application, there are actually two different questions that sound similar but are not:

- **"What happened on this specific ticket, with this specific person, so far?"** -- answered by PostgreSQL's existing tables (`tickets`, `messages`, `ticket_events`), queried directly, with no embedding or similarity search involved at all. This is `ticket_service.get_ticket_history()`, already built in an earlier phase, untouched by this one.
- **"What does the IT department officially know about this general category of problem?"** -- answered by the RAG knowledge base built in this phase (`knowledge_documents` + `knowledge_chunks`, queried via `retrieval_service.search()`).

phase7.md's own example makes the distinction concrete. A student writes:

> "My VPN is not connecting."

The ticket history for that student's ticket might contain:

```text
Student:
VPN doesn't work.

Admin:
Did you restart the VPN client?

Student:
Yes, still doesn't work.
```

This is a record of one conversation between one student and one admin about one incident. It is useful -- a future AI agent will absolutely want to see it, so it doesn't ask the student to repeat something they already said -- but it is not "knowledge." It doesn't generalize. It doesn't tell you anything about how to fix a *different* student's VPN problem next week.

What RAG should retrieve for the same query is:

```text
VPN Troubleshooting Documentation
```

-- the officially maintained guide that applies to every VPN problem, not just this one conversation. That's `knowledge_chunks` rows belonging to the `VPN Troubleshooting Guide` document in this project's actual seeded knowledge base (`backend/seed/knowledge_docs/vpn_troubleshooting_guide.md`), which this manual's Worked Example chapter traces through the full pipeline.

## Why conflating the two would actively make the system worse, not just redundant

It's worth being specific about the failure mode, because "these are conceptually different" undersells how much conflating them would actually break:

- **Ticket conversations are noisy and unresolved by default.** A raw ticket transcript contains false starts, wrong guesses ("did you restart the VPN client?" -- which, in the example above, *didn't* fix it), incomplete information, and sometimes outright wrong troubleshooting steps an admin tried before finding the real fix. Embedding that directly into a "knowledge base" and retrieving it as if it were authoritative documentation would surface wrong or unresolved advice with the same confidence as the actual VPN Troubleshooting Guide -- there would be no way for a retrieval score to distinguish "this dead-end guess from an unresolved ticket" from "this is the department's verified fix."
- **Ticket data contains information tied to a specific person.** A ticket transcript can reference a student's name, their specific device, their specific error details, sometimes account information. A knowledge base document is written to be general-purpose and safe to retrieve for anyone's similar problem. Treating ticket transcripts as retrievable knowledge risks surfacing one student's personal ticket detail into a different student's context -- a privacy problem this design avoids entirely by construction, not by a filter bolted on afterward.
- **It would make the retrieval evaluation meaningless.** Chapter 15 (Retrieval Evaluation) measures whether a query retrieves the *correct, known-good* document. That evaluation only means something if the corpus being searched is made of vetted, authoritative documents. If the corpus were a mix of official guides and arbitrary past ticket transcripts, "did the right thing come back" would no longer have a clear answer -- there would be no ground truth to evaluate against.
- **It duplicates data that already has a better home.** Ticket history is already fully queryable, indexed, and structured in PostgreSQL via `ticket_service.get_ticket_history()`. There is no retrieval-quality benefit to also embedding it -- only cost (embedding every ticket message, forever, as it accumulates) and risk (the problems above) with no corresponding benefit, since a direct SQL lookup by `ticket_id` is strictly more precise than a similarity search for "find this exact ticket's own history."

## How this shows up in the actual implementation

This isn't just a design principle stated in a comment -- it's enforced by what the code simply does not do:

- Nothing in `backend/app/rag/ingestion_service.py` accepts a `ticket_id`, a `message_id`, or any other reference to ticket data. Its `ingest_document()` function's parameters are exactly what an *administrator uploading an IT document* would supply: `title`, `description`, `category`, `file_name`, `file_type`, `file_bytes`. There is no code path from `tickets`/`messages`/`ticket_events` into `knowledge_documents`/`knowledge_chunks` anywhere in this codebase.
- The only way a row ever appears in `knowledge_documents` is through `POST /admin/knowledge` (an explicit, admin-authorized upload) or the seed script (`backend/seed/seed_knowledge_base.py`, which ingests the eight curated example documents). Nothing runs automatically against ticket data.
- `retrieval_service.search()` only ever queries `knowledge_chunks` joined to `knowledge_documents`. It has no awareness that `tickets` or `messages` tables exist.

## What the future AI agent phase is expected to do with both

This phase doesn't build the AI agent, but phase7.md is explicit about what a *later* phase's context assembly should eventually look like, and it's worth stating here because it's the payoff for keeping these two sources separate now:

```text
CURRENT MESSAGE
        +
TICKET HISTORY
        +
RETRIEVED KNOWLEDGE
        |
        v
    AI AGENT
```

Three distinct inputs, from two distinct systems, combined only at the very last step, by the agent, when it actually reasons about a response. Ticket history answers "what has this specific person already told us." Retrieved knowledge answers "what does the department know about this kind of problem in general." Keeping them as separate inputs -- rather than merging them into one search index -- is what lets a future agent reason about them differently: it can trust the knowledge-base result as authoritative while treating ticket history as context about what's already been tried, and it can cite "per the VPN Troubleshooting Guide" without confusing that with "per what an admin guessed in a different, unrelated ticket last month."

This phase builds only the `RETRIEVED KNOWLEDGE` box. `CURRENT MESSAGE` and `TICKET HISTORY` already exist from earlier phases, untouched. Combining all three into one context object is explicitly left to the future AI agent phase (see the Architecture Boundaries chapter for exactly what's built versus what's deferred).
