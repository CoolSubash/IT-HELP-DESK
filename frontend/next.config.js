/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output -- infra/cdk/stacks/frontend_stack.py runs this in
  // ECS Fargate from Dockerfile's runtime stage, which copies only
  // .next/standalone + .next/static (a self-contained node_modules
  // subset), not the full node_modules tree `next start` would need.
  output: "standalone",
};

module.exports = nextConfig;
