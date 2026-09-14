#!/usr/bin/env python3
"""
CDK app entry point. Run `cdk synth`/`cdk deploy` from this directory
(infra/cdk/) -- see infra/README.md for the full deployment walkthrough,
required context values, and cost notes for each stack.

Six independent stacks (deploy/destroy any subset):
    ItHelpdeskEmailIngestionStack    Phase 5A: SES -> S3 -> Lambda -> FastAPI
    ItHelpdeskKnowledgeBaseStack     Phase 7: S3 bucket for knowledge-base documents
    ItHelpdeskNetworkStack           VPC shared by the two stacks below
    ItHelpdeskDatabaseStack          Aurora PostgreSQL (needs the network stack)
    ItHelpdeskRegistryStack          ECR repository for the backend image
    ItHelpdeskComputeStack           ECS Fargate + ALB running the backend
                                      (needs network + database + registry)
"""
import aws_cdk as cdk

from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.email_stack import EmailIngestionStack
from stacks.knowledge_base_stack import KnowledgeBaseStack
from stacks.network_stack import NetworkStack
from stacks.registry_stack import RegistryStack

app = cdk.App()

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

compute_stack = ComputeStack(
    app,
    "ItHelpdeskComputeStack",
    vpc=network_stack.vpc,
    repository=registry_stack.repository,
    database_cluster=database_stack.cluster,
    knowledge_base_bucket_name=knowledge_base_bucket_name,
    it_support_email=it_support_email,
    image_tag=image_tag,
    description="ECS Fargate + ALB running the FastAPI backend",
)
compute_stack.add_dependency(network_stack)
compute_stack.add_dependency(database_stack)
compute_stack.add_dependency(registry_stack)

app.synth()
