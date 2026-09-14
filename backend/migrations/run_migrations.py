"""
Tiny migration runner: applies every .sql file in this folder, in filename
order, that hasn't been applied yet. Tracks what's been applied in a
`schema_migrations` table (one row per applied filename).

This replaces a tool like Alembic. Alembic's main value is generating
migrations *from* ORM model changes -- since there's no ORM here, that
value disappears, and plain numbered SQL files plus a record of "which
ones have I already run" is all Phase 1 actually needs.

Usage (from backend/): python -m migrations.run_migrations
"""
import pathlib

import psycopg2

from app.config import settings

MIGRATIONS_DIR = pathlib.Path(__file__).parent


def run_migrations() -> None:
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("SELECT version FROM schema_migrations")
            already_applied = {row[0] for row in cur.fetchall()}
        conn.commit()

        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if sql_file.name in already_applied:
                continue
            print(f"Applying {sql_file.name} ...")
            with conn.cursor() as cur:
                cur.execute(sql_file.read_text())
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (sql_file.name,)
                )
            conn.commit()
            print(f"Applied {sql_file.name}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
