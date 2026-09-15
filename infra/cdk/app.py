#!/usr/bin/env python3
"""
CDK app entry point. Run `cdk synth`/`cdk deploy` from this directory
(infra/cdk/) -- see infra/README.md for the full deployment walkthrough,
required context values, and cost notes for each stack.

Eight stacks, three-tier shape (deploy/destroy any subset -- only the
dependencies noted below are enforced):
    ItHelpdeskEmailIngestionStack    Phase 5A: SES -> S3 -> Lambda -> FastAPI
    ItHelpdeskKnowledgeBaseStack     Phase 7: S3 bucket for knowledge-base documents
    ItHelpdeskNetworkStack           VPC shared by every stack below
    ItHelpdeskDatabaseStack          Aurora PostgreSQL, private data tier (needs network)
    ItHelpdeskRegistryStack          ECR repositories for both container images
    ItHelpdeskComputeStack           Backend: ECS Fargate + INTERNAL ALB
                                      (needs network + database + registry)
    ItHelpdeskApiStack               Public edge for the backend: HTTP API Gateway
                                      + VPC Link -> the internal ALB above
                                      (needs compute)
    ItHelpdeskFrontendStack          Frontend: ECS Fargate + PUBLIC ALB
                                      (needs network + registry)
"""
import aws_cdk as cdk

from stacks.api_stack import ApiGatewayStack
from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.email_stack import EmailIngestionStack
from stacks.frontend_stack import FrontendStack
from stacks.github_oidc_stack import GithubOidcStack
from stacks.knowledge_base_stack import KnowledgeBaseStack
from stacks.network_stack import NetworkStack
from stacks.registry_stack import RegistryStack

app = cdk.App()

# The one stack you deploy by hand, once, with your own AWS credentials
# -- see github_oidc_stack.py's module docstring for why this can't be
# part of the automated chain below. Not instantiated unless both
# context values are given, so `cdk synth`/`cdk deploy` with no args
# (or CI's own deploys, which never pass these) don't need to know
# about it at all.
github_org = app.node.try_get_context("github_org")
github_repo = app.node.try_get_context("github_repo")
# Only needed if your repo has GitHub's "immutable subject claim"
# feature enabled -- see github_oidc_stack.py's module docstring for
# what this is and how to check. Find yours with:
#   gh api repos/<owner>/<repo> --jq '.owner.id, .id'
github_owner_id = app.node.try_get_context("github_owner_id")
github_repo_id = app.node.try_get_context("github_repo_id")
if github_org and github_repo:
    GithubOidcStack(
        app,
        "ItHelpdeskGithubOidcStack",
        github_org=github_org,
        github_repo=github_repo,
        github_owner_id=github_owner_id,
        github_repo_id=github_repo_id,
        description="One-time: lets GitHub Actions (main branch only) deploy every other stack via OIDC, no long-lived AWS keys",
    )

EmailIngestionStack(
    app,
    "ItHelpdeskEmailIngestionStack",
    description="Phase 5A: SES -> S3 -> Lambda -> FastAPI inbound email ingestion",
)

KnowledgeBaseStack(
    app,
    "ItHelpdeskKnowledgeBaseStack",
    description="Phase 7: S3 bucket + IAM identity for knowledge-base document storage",
)

network_stack = NetworkStack(
    app,
    "ItHelpdeskNetworkStack",
    description="VPC shared by the Aurora and ECS stacks",
)

# cdk deploy -c aurora_publicly_accessible=false -c aurora_allowed_cidr=203.0.113.7/32
# publicly_accessible defaults to true -- this project's current need
# (running migrations.run_migrations directly from a local machine) --
# see database_stack.py's module docstring for how/why to flip it once
# that's no longer needed.
aurora_publicly_accessible = app.node.try_get_context("aurora_publicly_accessible")
aurora_publicly_accessible = True if aurora_publicly_accessible is None else str(aurora_publicly_accessible).lower() == "true"
aurora_allowed_cidr = app.node.try_get_context("aurora_allowed_cidr")

database_stack = DatabaseStack(
    app,
    "ItHelpdeskDatabaseStack",
    vpc=network_stack.vpc,
    publicly_accessible=aurora_publicly_accessible,
    allowed_cidr=aurora_allowed_cidr,
    description="Aurora PostgreSQL for the IT Helpdesk backend",
)
database_stack.add_dependency(network_stack)

registry_stack = RegistryStack(
    app,
    "ItHelpdeskRegistryStack",
    description="ECR repository for the FastAPI backend image",
)

# cdk deploy -c knowledge_base_bucket_name=<KnowledgeBaseBucketName from ItHelpdeskKnowledgeBaseStack's output> \
#            -c it_support_email=it-support@your-domain.edu -c image_tag=v1
# Required (no real default baked in here -- every deployment's bucket
# name is unique, see knowledge_base_stack.py's module docstring for
# why): pass the KnowledgeBaseBucketName value from your own deploy of
# ItHelpdeskKnowledgeBaseStack.
knowledge_base_bucket_name = app.node.try_get_context("knowledge_base_bucket_name")
it_support_email = app.node.try_get_context("it_support_email") or "it-support@university.edu"
image_tag = app.node.try_get_context("image_tag") or "latest"
email_provider = app.node.try_get_context("email_provider") or "ses"

# cdk deploy -c cors_allowed_origins=http://<FrontendUrl from ItHelpdeskFrontendStack's output>
# Comma-separated. Falls back to app/config.py's own local-dev default
# (localhost:3000/3001) when not given -- which is why this stack can
# still deploy standalone before ItHelpdeskFrontendStack ever has. Not
# read from frontend_stack directly (a Python cross-stack reference)
# because that would force FrontendStack to deploy before ComputeStack
# on every single deploy, forever, for a value (the ALB's DNS name)
# that's actually stable after the frontend's very first deploy -- see
# infra/README.md for the one-time bootstrap this implies.
cors_allowed_origins_raw = app.node.try_get_context("cors_allowed_origins")
cors_allowed_origins = cors_allowed_origins_raw.split(",") if cors_allowed_origins_raw else None

# cdk deploy -c email_webhook_secret_arn=<InboundEmailSecretArn from ItHelpdeskEmailIngestionStack's output>
# Same "empty on first run, real from the second run onward" pattern as
# cors_allowed_origins above -- see compute_stack.py's own comment on
# what EMAIL_WEBHOOK_DEV_MODE does with this value.
email_webhook_secret_arn = app.node.try_get_context("email_webhook_secret_arn")

compute_stack = ComputeStack(
    app,
    "ItHelpdeskComputeStack",
    vpc=network_stack.vpc,
    repository=registry_stack.repository,
    database_cluster=database_stack.cluster,
    knowledge_base_bucket_name=knowledge_base_bucket_name,
    it_support_email=it_support_email,
    image_tag=image_tag,
    email_provider=email_provider,
    cors_allowed_origins=cors_allowed_origins,
    email_webhook_secret_arn=email_webhook_secret_arn,
    description="Backend: ECS Fargate + internal ALB running the FastAPI backend",
)
compute_stack.add_dependency(network_stack)
compute_stack.add_dependency(database_stack)
compute_stack.add_dependency(registry_stack)

api_stack = ApiGatewayStack(
    app,
    "ItHelpdeskApiStack",
    vpc=network_stack.vpc,
    backend_listener=compute_stack.listener,
    description="Public edge for the backend: HTTP API Gateway + VPC Link into the internal ALB",
)
api_stack.add_dependency(compute_stack)

# cdk deploy -c frontend_image_tag=<commit-sha>
# Separate context key from the backend's `image_tag` so CI can deploy
# either tier independently of the other having a new image ready.
frontend_image_tag = app.node.try_get_context("frontend_image_tag") or "latest"

frontend_stack = FrontendStack(
    app,
    "ItHelpdeskFrontendStack",
    vpc=network_stack.vpc,
    repository=registry_stack.frontend_repository,
    image_tag=frontend_image_tag,
    description="Frontend: ECS Fargate + public ALB running the Next.js dashboard",
)
frontend_stack.add_dependency(network_stack)
frontend_stack.add_dependency(registry_stack)

app.synth()
