"""
Shared pytest fixtures.

Tests run against a real Postgres database (see backend/.env.example /
infra/docker-compose.yml) -- there's no SQLite fallback and no mocking: the
whole point of Phase 1 is verifying that the actual schema and constraints
work, so tests talk to the same engine that runs in production.

`_create_schema` applies every migration once per test session and drops
the whole `public` schema afterward. `db` gives each test its own
connection; tests avoid colliding with each other's data by using distinct
emails/identifiers rather than relying on per-test rollback isolation.
"""
import pathlib

import psycopg2
import psycopg2.extras
import pytest

from app.config import settings

psycopg2.extras.register_uuid()

MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "migrations"

# app/config.py's real default is KNOWLEDGE_STORAGE_BACKEND=s3 (Phase 7) --
# the actual deployment target. Forcing "local" here, once, for the whole
# test session is what lets every test that uploads a document (PDF/TXT/
# MD/DOCX ingestion, the admin API's upload/versioning/duplicate tests)
# run with zero AWS credentials, regardless of that default -- matching
# EMBEDDING_PROVIDER's existing "dev" default, which needed no equivalent
# override since dev already is what tests want. See
# app/rag/storage.py's LocalFileStorage/S3FileStorage and
# docs/rag-manual's testing chapter.
settings.knowledge_storage_backend = "local"


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
                cur.execute(sql_file.read_text())
        conn.commit()
    finally:
        conn.close()

    yield

    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def db():
    conn = psycopg2.connect(settings.database_url)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
