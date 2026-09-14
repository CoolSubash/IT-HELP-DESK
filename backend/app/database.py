"""
Raw psycopg2 connection pool -- no ORM.

Every query anywhere in this backend (app/services/, seed/seed_data.py,
migrations/run_migrations.py) is a plain SQL string executed through a
psycopg2 connection. This module is the one place that knows how to obtain
one.

`get_db()` is a FastAPI dependency: it hands a route a connection, commits
if the route handler finished without raising, rolls back if it didn't, and
always returns the connection to the pool afterward. This mirrors what
`Session`/`get_db()` did in an ORM setup -- the pattern of "one connection
per request, always cleaned up" doesn't change just because the query layer
did.
"""
from collections.abc import Generator

import psycopg2.extras
from pgvector.psycopg2 import register_vector
from psycopg2 import pool as pg_pool
from psycopg2.extensions import connection as PGConnection

from app.config import settings

# Without this, psycopg2 would hand back plain strings for UUID columns and
# require plain strings (not uuid.UUID objects) as query parameters. This
# registers automatic conversion both ways, so the rest of the codebase can
# just use `uuid.UUID` everywhere, matching a normal Python type.
psycopg2.extras.register_uuid()

connection_pool = pg_pool.SimpleConnectionPool(
    minconn=1, maxconn=10, dsn=settings.database_url
)


def get_db() -> Generator[PGConnection, None, None]:
    conn = connection_pool.getconn()
    # Mirrors register_uuid() above, for the `vector` column
    # (migrations/0006_knowledge_chunks_and_vector.sql): without this, a
    # Python list passed as a query param wouldn't adapt to pgvector's
    # `vector` type, and a fetched embedding would come back as a raw
    # string instead of a list[float]. register_vector() looks up the
    # type's OID on *this* connection, which is why it's called here
    # (every checkout) rather than once at import time -- the pool's
    # connections aren't guaranteed to exist yet when this module loads.
    # It's a single fast catalog lookup, and psycopg2 doesn't re-register
    # a type it already knows, so paying it per checkout is cheap.
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        connection_pool.putconn(conn)
