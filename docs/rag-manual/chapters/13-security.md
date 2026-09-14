# Security

## phase7.md Section 18's Checklist, Addressed Item by Item

phase7.md section 18 lists six specific security requirements for the knowledge base. Here is exactly what was built against each one.

**"Only authenticated admins can upload/manage documents."** Every endpoint under `/admin/knowledge` -- all six of them, with no exceptions -- depends on `require_admin` (`app/auth.py`). The rest of this chapter goes into exactly what that guarantees, and, just as importantly, what it doesn't.

**"S3 objects are private if S3 is used."** `S3FileStorage` (`app/rag/storage.py`, covered in the ingestion pipeline chapter) never passes an ACL on its `put_object` call, relying entirely on the target bucket's own default-private configuration rather than per-object ACLs. This matches AWS's current guidance: S3 has been moving away from ACL-based access control in favor of Block Public Access settings and bucket policies, and a class that never touches ACLs at all cannot accidentally override a bucket's private default with a permissive one. The AWS deployment chapter later in this manual covers the actual bucket policy configuration expected to sit alongside this.

**"Database access is restricted."** This is fundamentally an infrastructure and deployment concern -- IAM policies, security groups, VPC placement, and network ACLs around wherever Postgres actually runs (a self-hosted instance or Amazon RDS) -- rather than something application code can enforce. The AWS deployment chapter gives concrete guidance for this.

**"Embeddings are not exposed publicly."** Enforced in two independent layers, described fully in the API reference chapter's discussion of `GET /admin/knowledge/{id}/chunks`: the `KnowledgeChunkRead` response schema has no field for the embedding at all, and the SQL query behind that endpoint (`ingestion_service.list_chunks()`) never even selects the `embedding` column from the database in the first place. This is deliberately defense-in-depth -- even a future bug that accidentally serialized the wrong dict somewhere couldn't leak the vector through this endpoint, because the raw data fetched from Postgres never contains it to begin with.

**"Documents cannot be accessed without authorization."** Every single endpoint under `/admin/knowledge`, including the search/preview endpoint, requires `require_admin`. There is no unauthenticated read path into the knowledge base anywhere in this implementation.

**"Secrets are not stored in source code."** AWS credentials (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), the Bedrock embedding model id, and the S3 bucket name are all read from environment variables through `app/config.py`'s `Settings` class (`pydantic-settings`, reading from a `.env` file that is listed in `.gitignore` and therefore never committed). Nothing in `app/rag/` hardcodes a credential, bucket name, or API key anywhere.

## `require_admin`: What It Actually Does, and What It Doesn't

This is the part of the chapter that needs to be completely candid, because getting this wrong -- overstating what this mechanism provides -- would be worse than not documenting it at all.

phase7.md section 10 asks the knowledge-base admin endpoints to "use the existing admin authentication/RBAC system." There is no such system to use. As of this phase, this entire backend has no login of any kind, anywhere. The `admins` table (added in an earlier phase, long before RAG existed) is a read-only directory with no password column, no session mechanism, and no login endpoint at all -- admin rows are only ever inserted directly, either by the seed script or, in a real deployment, by whoever operates the database. Every other router in this codebase performs no authorization check whatsoever; this is the first phase of the project where an endpoint genuinely needs to refuse a caller.

Building real authentication was correctly judged to be out of scope for this phase -- it is not listed as a Phase 7 deliverable in phase7.md, and it wasn't built in any earlier phase either. But phase7.md section 20 explicitly requires a test verifying "non-admin users must not manage the knowledge base," which is not a meaningful test to write against an API with no concept of "non-admin" at all. Some gate had to exist.

`require_admin`, defined in `app/auth.py`, is that gate:

```python
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
```

It is a FastAPI dependency that reads a single request header, `X-Admin-Id`, expected to contain an admin's UUID. If the header is missing entirely, it raises HTTP 401. If the header is present but doesn't resolve to a real row in the `admins` table (via the pre-existing `admin_service.get_admin()` function, unchanged from earlier phases), it raises HTTP 403. If it does resolve, the resolved admin's row is returned and made available to the route handler.

State this plainly, without hedging: **this is not real authentication.** There is no password check. There is no session token. There is no cryptographic signature of any kind proving the request actually came from the admin whose id is in the header. Anyone who knows -- or successfully guesses -- a real admin's UUID passes this check completely and can manage the entire knowledge base as that admin. UUIDs are not secrets and were never designed to function as one; they are unguessable in practice only in the sense that guessing one at random is astronomically unlikely, not in the sense that they resist an attacker who has any other way of learning or observing one (for instance, from a response body returned by `GET /admins`, which is a pre-existing, unauthenticated, read-only endpoint listing every admin's id, name, and email).

This is deliberately the same kind of labeled stand-in as `EMAIL_WEBHOOK_DEV_MODE`, an existing mechanism elsewhere in this codebase (`app/email/service.py`, `app/routers/email.py`): in local development, the inbound email webhook accepts requests with no real verification that they actually originated from AWS SNS, because building real SNS message signature verification wasn't the point of that phase either. Neither mechanism claims to be secure. Both exist to make the rest of the system -- and its tests -- meaningful in the absence of the real thing, with the gap clearly documented rather than silently glossed over.

## Why This Design Is Still the Right Call

The alternative to building `require_admin` at all would have been to leave the knowledge-base endpoints completely unauthenticated, like every other endpoint in this codebase currently is. That would have technically satisfied "don't build real authentication, it's out of scope" just as well, but it would have made phase7.md section 20's authorization test impossible to write meaningfully, and it would have left the knowledge-base admin endpoints -- document upload, deletion, and permanent hard-delete -- reachable by literally anyone who could reach the API at all, with zero barrier. `require_admin` is a small, honest middle ground: it is not a security boundary a real deployment should trust, but it is a real, working, testable authorization gate that correctly distinguishes "a request carrying a real admin's identity" from "a request carrying no identity, or a fabricated one" for every purpose this phase actually needs it for.

## Forward Compatibility

Every router using this dependency depends on it the same way: `admin: dict = Depends(require_admin)`. When real session- or JWT-based authentication is eventually built in a later phase, only `require_admin`'s own internal implementation needs to change -- swap the header-lookup logic for a real session/token validation call that still returns an admin dict on success and still raises `HTTPException` on failure. Not a single line in `app/routers/knowledge.py` needs to change, because every route already depends on the abstraction (`require_admin`, a function that produces an admin dict or raises) rather than on the specific mechanism (a trusted header) behind it today.

## Verified

This was confirmed working correctly against the real running API, not just designed on paper: a request to any `/admin/knowledge` endpoint with no `X-Admin-Id` header returns HTTP 401. A request with a syntactically valid but non-existent admin UUID returns HTTP 403. Both are covered by automated tests as well -- `tests/test_knowledge_api.py::test_missing_admin_header_is_rejected`, `test_unknown_admin_id_is_rejected`, and `test_search_without_admin_header_is_rejected` -- so a future change that accidentally weakens or removes this gate on any endpoint would be caught by the test suite immediately, not discovered later in a security review.
