"""
Minimal admin-authorization stand-in.

phase7.md #10/#18 asks the knowledge-base admin endpoints to "use the
existing admin authentication/RBAC system" and to make sure "only
authenticated admins can upload/manage documents." There isn't an
existing one to use: as of this phase the backend has no login at all
(root README section 3 -- `admins` is a read-only directory, populated
only by the seed script; every other router in this codebase performs no
authorization check of any kind). Building real authentication is out of
scope for this phase -- it isn't listed anywhere in phase1.md-phase6.md
or phase7.md -- but the knowledge-base endpoints are the first ones in
this codebase that genuinely need to refuse a caller, so *something* has
to exist for phase7.md #20's "non-admin users must not manage the
knowledge base" test to mean anything.

require_admin() is that something, and nothing more: a FastAPI dependency
that trusts an `X-Admin-Id` request header, resolves it against the real
`admins` table (app/services/admin_service.py -- the same table
tickets.assigned_admin_id already references), and rejects the request
(401 if the header is missing, 403 if the id doesn't resolve to a real
admin) otherwise. It is explicitly NOT real authentication: there is no
password, no session, no signature, and anyone who knows or guesses an
admin's UUID passes this check. This is the same kind of deliberate,
clearly-labeled stand-in as EMAIL_WEBHOOK_DEV_MODE (app/email/service.py,
app/routers/email.py) -- not a claim that it's secure, a placeholder that
makes the rest of the system (and its tests) meaningful until real login
exists.

When real admin authentication is built, replace this function's body
with a session/JWT lookup -- every router using it already depends on it
as `admin: dict = Depends(require_admin)`, so no call site changes.
"""
import uuid

from fastapi import Depends, Header, HTTPException
from psycopg2.extensions import connection as PGConnection

from app.database import get_db
from app.errors import NotFoundError
from app.services import admin_service


def require_admin(
    x_admin_id: uuid.UUID | None = Header(default=None, alias="X-Admin-Id"),
    db: PGConnection = Depends(get_db),
) -> dict:
    if x_admin_id is None:
        raise HTTPException(status_code=401, detail="X-Admin-Id header is required for this endpoint")
    try:
        return admin_service.get_admin(db, x_admin_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=403, detail="X-Admin-Id does not match a known admin") from exc
