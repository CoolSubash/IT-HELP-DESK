#!/bin/sh
# Container entrypoint for the ECS deployment (infra/cdk/stacks/compute_stack.py).
#
# app/config.py expects one DATABASE_URL connection string; Aurora's
# password only exists inside a Secrets Manager secret at deploy time,
# injected here as DB_PASSWORD (and DB_USER) via ECS's `secrets`
# mechanism -- never baked into the image or the task definition as
# plain text. This script assembles DATABASE_URL from those parts
# immediately before starting the app, so app/config.py itself stays
# exactly as it is for local development (a plain DATABASE_URL in
# backend/.env) -- this composition is a deployment-layer concern, not
# an application one.
#
# If DATABASE_URL is already set (e.g. someone runs this image locally
# with `docker run -e DATABASE_URL=...`), it's left alone.
set -e

if [ -z "$DATABASE_URL" ] && [ -n "$DB_HOST" ]; then
    export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT:-5432}/${DB_NAME:-helpdesk}"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
