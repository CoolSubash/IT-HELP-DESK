# Production image for infra/cdk/stacks/frontend_stack.py (ECS Fargate).
# Not used for local development -- the root README runs the frontend
# directly with `npm run dev` instead; this image exists purely for the
# deployed path. Mirrors backend/Dockerfile's "prod image only" role.
#
# NEXT_PUBLIC_* variables are inlined into the JS bundle by `next build`
# -- they cannot be changed at container start the way backend/entrypoint.sh
# assembles DATABASE_URL from ECS secrets. That means the backend's API
# Gateway URL must be known BEFORE this image is built, not just before
# it's run. The CI/CD pipeline (.github/workflows/deploy.yml) passes it
# as a build-arg once the API Gateway endpoint from api_stack.py is
# stable (see that stack's module docstring for why it's stable across
# redeploys once created).
FROM node:20-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
RUN npm run build

# Separate runtime stage: only the standalone server + static assets
# ship in the final image, not the full node_modules/devDependencies
# tree the build stage needed.
FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
