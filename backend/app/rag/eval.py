"""
Retrieval evaluation (phase7.md #15): "do not judge RAG only by whether
the application runs." This module measures whether the ACTUAL relevant
document comes back for a realistic question, against a small hand-labeled
dataset (EVAL_DATASET below, paired with the example documents in
seed/knowledge_docs/ -- run `python -m seed.seed_knowledge_base` first, or
evaluate() returns all-zero scores against an empty knowledge base).

Metric definitions, both computed at the CHUNK level (what
retrieval_service.search() actually returns) against a single labeled
"expected document" per question:

  Recall@K    = 1 if any chunk from the expected document appears in the
                top K results, else 0. With exactly one relevant document
                per question (this dataset's design, matching phase7.md
                #15's own examples), Recall@K is precisely "did the
                correct document/chunk appear in Top K" -- phase7.md
                #15's literal ask -- averaged across the dataset.
                (General IR Recall@K is "relevant items retrieved" /
                "total relevant items"; with exactly one relevant item
                that fraction is 1 or 0, i.e. exactly the hit-rate above.)

  Precision@K = (chunks in the top K that belong to the expected
                document) / K. Unlike Recall@K, this is penalized by
                irrelevant chunks crowding the top K -- a correct chunk
                at position 1 of a top-5 result still scores only 0.2 if
                the other four are from unrelated documents. This is why
                both numbers matter together: Recall@K alone can't tell
                "found immediately, surrounded by noise" apart from
                "found immediately, dominant result" -- Precision@K can.

See docs/rag-manual's evaluation chapter for the full worked results
table (this project's actual numbers, from a real run against the dev
embedding provider and the seed corpus) and for why retrieval quality is
checked BEFORE the AI agent phase begins: a wrong or noisy retrieval
result silently becomes a wrong AI answer with no visible error anywhere
-- the agent has no way to know the knowledge base handed it the wrong
document.
"""
from dataclasses import dataclass, field

from psycopg2.extensions import connection as PGConnection

from app.rag import retrieval_service

DEFAULT_K_VALUES = (1, 3, 5)


@dataclass
class EvalCase:
    question: str
    expected_title: str


# Paired 1:1 with seed/knowledge_docs/*.md (see that folder's README for
# the full text of each document). Kept intentionally small (phase7.md
# #15: "create A SMALL evaluation dataset") -- enough to catch a broken
# chunking/embedding/retrieval change, not a statistically rigorous
# benchmark; docs/rag-manual's testing chapter covers how to grow this
# safely (one labeled question per new document, at minimum).
EVAL_DATASET: list[EvalCase] = [
    EvalCase("My VPN says authentication failed.", "VPN Troubleshooting Guide"),
    EvalCase("VPN client won't connect at all, error VPN-ERR-403.", "VPN Troubleshooting Guide"),
    EvalCase("I forgot my student password.", "Password Reset Procedure"),
    EvalCase("I need to reset MFA on my account, I got a new phone.", "Password Reset Procedure"),
    EvalCase("Campus WiFi keeps disconnecting.", "WiFi Troubleshooting Guide"),
    EvalCase("How do I set up my new student account for the first time?", "Student Account Setup"),
    EvalCase("How do I install Microsoft Office on my laptop as a student?", "Microsoft Office Installation"),
    EvalCase("What's the wired ethernet setup for the dorms?", "Campus Network Guide"),
    EvalCase("The library printer says paper jam but there's no paper stuck.", "Printer Troubleshooting"),
    EvalCase("Is there a known outage affecting campus email today?", "Known IT Issues"),
]


@dataclass
class EvalCaseResult:
    question: str
    expected_title: str
    retrieved_titles: list[str]
    hits_at_k: dict[int, bool] = field(default_factory=dict)
    precision_at_k: dict[int, float] = field(default_factory=dict)


@dataclass
class EvalReport:
    cases: list[EvalCaseResult]
    recall_at_k: dict[int, float]
    precision_at_k: dict[int, float]


def evaluate(
    conn: PGConnection,
    dataset: list[EvalCase] = EVAL_DATASET,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
) -> EvalReport:
    max_k = max(k_values)
    cases: list[EvalCaseResult] = []

    for case in dataset:
        results = retrieval_service.search(conn, case.question, top_k=max_k)
        titles_in_order = [result["title"] for result in results]

        case_result = EvalCaseResult(
            question=case.question, expected_title=case.expected_title, retrieved_titles=titles_in_order
        )
        for k in k_values:
            top_k_titles = titles_in_order[:k]
            case_result.hits_at_k[k] = case.expected_title in top_k_titles
            relevant_in_top_k = sum(1 for title in top_k_titles if title == case.expected_title)
            case_result.precision_at_k[k] = relevant_in_top_k / k if k > 0 else 0.0
        cases.append(case_result)

    recall_at_k = {
        k: sum(1 for c in cases if c.hits_at_k[k]) / len(cases) if cases else 0.0 for k in k_values
    }
    precision_at_k = {
        k: sum(c.precision_at_k[k] for c in cases) / len(cases) if cases else 0.0 for k in k_values
    }
    return EvalReport(cases=cases, recall_at_k=recall_at_k, precision_at_k=precision_at_k)


def format_report(report: EvalReport) -> str:
    lines = ["Retrieval evaluation report", "=" * 27, ""]
    for k in sorted(report.recall_at_k):
        lines.append(f"Recall@{k}:    {report.recall_at_k[k]:.2%}")
        lines.append(f"Precision@{k}: {report.precision_at_k[k]:.2%}")
        lines.append("")

    lines.append("Per-question detail:")
    for case in report.cases:
        hits = ", ".join(f"@{k}={'HIT' if v else 'miss'}" for k, v in sorted(case.hits_at_k.items()))
        lines.append(f'  "{case.question}"')
        lines.append(f"    expected: {case.expected_title}")
        lines.append(f"    retrieved (top {max(case.hits_at_k)}): {case.retrieved_titles}")
        lines.append(f"    {hits}")
    return "\n".join(lines)
