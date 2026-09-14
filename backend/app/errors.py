"""
App-level exceptions that carry an HTTP status code, so services can say
*what* went wrong in plain language without knowing anything about HTTP.

Services raise these (e.g. `raise NotFoundError("user not found")`);
app/main.py registers one exception handler per type that turns them into a
clean JSON error response. This keeps routers free of repeated
try/except-around-every-call boilerplate.
"""


class NotFoundError(Exception):
    """Raised when a referenced row (user, ticket, ...) doesn't exist.
    Mapped to HTTP 404."""


class ConflictError(Exception):
    """Raised when a request is well-formed but contradicts the current
    state of the data -- e.g. an invalid ticket status transition. Mapped
    to HTTP 409."""


class ValidationError(Exception):
    """Raised for a well-formed request whose *content* is unusable before
    any database row is touched -- an unsupported file type, an empty
    file (phase7.md #19). Distinct from ConflictError: nothing about
    existing data is contradicted, the input itself just can't be
    processed. Mapped to HTTP 422."""
