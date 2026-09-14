"""
Ingests the example knowledge-base documents in seed/knowledge_docs/ (8
Markdown files -- VPN, WiFi, Password Reset, Student Account Setup,
Microsoft Office, Campus Network, Printer, and Known IT Issues guides)
through the real ingestion pipeline (app/rag/ingestion_service.py), the
same code path POST /admin/knowledge uses. This is what
app/rag/eval.py's EVAL_DATASET is written against, and what
docs/rag-manual's testing chapter walks through manually -- run this
before running the eval script or testing POST /admin/knowledge/search
by hand, or the knowledge base will be empty.

Mirrors seed/seed_data.py's `seed(conn=None)` shape so tests can reuse it
(see tests/test_rag_ingestion.py) without duplicating the connection
lifecycle logic.

Run with: `python -m seed.seed_knowledge_base` (see docs/rag-manual).
"""
import pathlib

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from app.config import settings
from app.rag import ingestion_service

psycopg2.extras.register_uuid()

KNOWLEDGE_DOCS_DIR = pathlib.Path(__file__).parent / "knowledge_docs"

# (filename, title, category) -- category values reuse app/enums.py's
# TicketCategory strings so a future AI agent's category-filtered search
# (phase7.md #13) lines up with the same vocabulary tickets already use,
# even though knowledge_documents.category has no CHECK constraint tying
# it to that enum (it's free text -- see migrations/0001_initial_schema.sql).
DOCUMENTS = [
    ("vpn_troubleshooting_guide.md", "VPN Troubleshooting Guide", "VPN"),
    ("wifi_troubleshooting_guide.md", "WiFi Troubleshooting Guide", "WIFI"),
    ("password_reset_procedure.md", "Password Reset Procedure", "PASSWORD"),
    ("student_account_setup.md", "Student Account Setup", "ACCOUNT"),
    ("microsoft_office_installation.md", "Microsoft Office Installation", "SOFTWARE"),
    ("campus_network_guide.md", "Campus Network Guide", "NETWORK"),
    ("printer_troubleshooting.md", "Printer Troubleshooting", "HARDWARE"),
    ("known_it_issues.md", "Known IT Issues", "OTHER"),
]


def seed(conn=None) -> list[dict]:
    """Ingests every document in DOCUMENTS, skipping any whose title
    already has a READY document (so re-running this script is safe --
    matches ingestion_service's own duplicate-title ConflictError
    behavior rather than fighting it). Returns the list of resulting
    knowledge_documents rows (READY or FAILED)."""
    owns_connection = conn is None
    if conn is None:
        conn = psycopg2.connect(settings.database_url)
        register_vector(conn)

    try:
        admin_id = _find_any_admin_id(conn)
        results = []
        for file_name, title, category in DOCUMENTS:
            if _ready_document_exists(conn, title):
                print(f"skipping {title!r} -- a READY document with that title already exists")
                continue
            file_bytes = (KNOWLEDGE_DOCS_DIR / file_name).read_bytes()
            document = ingestion_service.ingest_document(
                conn,
                title=title,
                description="Example IT knowledge-base document seeded for Phase 7 (RAG).",
                category=category,
                file_name=file_name,
                file_type="md",
                file_bytes=file_bytes,
                uploaded_by=admin_id,
            )
            print(f"ingested {title!r} -> status={document['status']} id={document['id']}")
            results.append(document)

        if owns_connection:
            conn.commit()
        return results
    finally:
        if owns_connection:
            conn.close()


def _find_any_admin_id(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM admins LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None


def _ready_document_exists(conn, title: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM knowledge_documents WHERE title = %s AND status = 'READY'", (title,))
        return cur.fetchone() is not None


if __name__ == "__main__":
    seed()
