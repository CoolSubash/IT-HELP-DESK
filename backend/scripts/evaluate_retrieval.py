"""
CLI wrapper around app/rag/eval.py (phase7.md #15). Run this after
seeding the knowledge base to see the actual current Recall@K/Precision@K
numbers, e.g. after changing chunk size/overlap or switching embedding
providers -- see docs/rag-manual's evaluation chapter for how to read the
report and when a change is worth keeping.

Usage (from backend/, with the venv active and Postgres running):
    python -m migrations.run_migrations
    python -m seed.seed_data              # creates an admin row (used as uploaded_by)
    python -m seed.seed_knowledge_base    # ingests seed/knowledge_docs/*.md
    python -m scripts.evaluate_retrieval
"""
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from app.config import settings
from app.rag import eval as rag_eval

psycopg2.extras.register_uuid()


def main() -> None:
    conn = psycopg2.connect(settings.database_url)
    register_vector(conn)
    try:
        report = rag_eval.evaluate(conn)
        print(rag_eval.format_report(report))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
