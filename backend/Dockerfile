# Production image for infra/cdk/stacks/compute_stack.py (ECS Fargate).
# Not used for local development -- see the root README, which runs the
# backend directly with `uvicorn` against a local .venv instead; this
# image exists purely for the deployed path.
FROM python:3.12-slim

WORKDIR /app

# requirements.txt only, not requirements-dev.txt: pytest/reportlab are
# test-only tooling (see requirements-dev.txt's own comments) with no
# reason to ship in the image that actually serves traffic.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
