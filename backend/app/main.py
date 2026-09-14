"""
FastAPI application entrypoint. Wires together config, database, routers,
and error handling. Business logic lives in app/services/, not here or in
routers/ -- this file should stay small no matter how many features get
added.

The two exception handlers are what let every service raise a plain
`NotFoundError`/`ConflictError` (see app/errors.py) instead of routers each
building their own `HTTPException` -- one place decides "NotFoundError
means HTTP 404", instead of that mapping being repeated at every call site.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.errors import ConflictError, NotFoundError, ValidationError
from app.rag.storage import StorageNotConfiguredError
from app.routers import (
    admins,
    agent_actions,
    dashboard,
    email,
    health,
    knowledge,
    messages,
    ticket_events,
    tickets,
    users,
)

app = FastAPI(title="IT Helpdesk Agent API", version="0.1.0")

# The Phase 3 dashboard (Next.js) calls this API directly from the
# browser rather than through a Next.js server proxy, so the browser's
# same-origin policy has to be explicitly relaxed for the dashboard's
# origin. There's no cookie-based auth here to worry about leaking
# cross-site -- this API has no sessions at all yet.
app.add_middleware(
    CORSMiddleware,
    # 3001 included because `next dev` silently falls back to it whenever
    # 3000 is already taken by something else on the machine.
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(messages.router)
app.include_router(ticket_events.router)
app.include_router(agent_actions.router)
app.include_router(admins.router)
app.include_router(dashboard.router)
app.include_router(email.router)
app.include_router(knowledge.router)


@app.exception_handler(NotFoundError)
def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
def handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(StorageNotConfiguredError)
def handle_storage_not_configured(request: Request, exc: StorageNotConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})
