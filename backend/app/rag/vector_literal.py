"""
Round-trips a Python `list[float]` through pgvector's `vector` type in raw
SQL. `register_vector()` (called per-connection in app/database.py) makes
reading a `vector` column back automatically produce a Python list -- but
on the pgvector-python 0.3.x write side, that same call only registers an
adapter for `numpy.ndarray` (see the installed package's
`pgvector/psycopg2/vector.py`: `register_adapter(np.ndarray, VectorAdapter)`),
not for a plain Python `list`. Adding numpy as a project dependency just
to satisfy that felt disproportionate for one adapter call, so instead
every place that writes or filters by an embedding (app/rag/ingestion_service.py,
app/rag/retrieval_service.py) sends it as pgvector's own text literal
format via this helper, with an explicit `::vector` cast at each `%s` in
the SQL -- Postgres parses `"[0.1,0.2,...]"::vector` the same way it
would parse a literal written directly in a query.
"""


def to_pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(component)) for component in vector) + "]"
