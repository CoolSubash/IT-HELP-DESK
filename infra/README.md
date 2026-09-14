# infra

AWS infrastructure-as-code for **Phase 5A** (inbound email ingestion),
**Phase 7** (knowledge-base document storage), and **hosting** (VPC, Aurora
PostgreSQL, ECR, ECS Fargate + ALB -- runs the FastAPI backend somewhere
AWS can actually reach it, which both Lambda-based flows above need). See
the root README's "Phase 5" section for the email flow's full architecture
explanation, and `docs/rag-manual`'s AWS deployment chapter for the
knowledge-base side. This file is just the "how do I run this folder"
quick reference.

```
infra/
  cdk/                     CDK app -- describes the AWS resources
    app.py                   instantiates all six stacks below
    cdk.json
    requirements.txt
    stacks/
      email_stack.py           Phase 5A: SES -> S3 -> Lambda -> FastAPI
      knowledge_base_stack.py  Phase 7: S3 bucket + IAM user for KB document storage
      network_stack.py         VPC shared by the database and compute stacks
      database_stack.py        Aurora PostgreSQL
      registry_stack.py        ECR repository for the backend image
      compute_stack.py         ECS Fargate + ALB running the backend
  lambda/email_ingestion/   The actual Lambda code the email stack deploys
    handler.py               entry point
    email_parser.py           .eml -> NormalizedEmail (stdlib only)
    fastapi_client.py         HTTPS POST to FastAPI (stdlib only)
    models.py                 NormalizedEmail dataclass
    requirements-dev.txt      pytest + moto (test-only; nothing is needed at runtime)
    tests/
```

All six stacks are independent enough to deploy/destroy individually, with
one real dependency chain: `ItHelpdeskComputeStack` needs
`ItHelpdeskNetworkStack`, `ItHelpdeskDatabaseStack`, and
`ItHelpdeskRegistryStack` to already exist (CDK enforces this automatically
via `add_dependency` in `app.py`). `ItHelpdeskEmailIngestionStack` and
`ItHelpdeskKnowledgeBaseStack` don't depend on any of the others.

## Cost -- read this before deploying the hosting stacks

The email and knowledge-base stacks are pennies. The hosting stacks
(network/database/registry/compute) are not:

| Resource | Running continuously | A short test (deploy, poke around, destroy) |
|---|---|---|
| NAT Gateway | ~$32/month | ~$0.05/hour |
| Aurora PostgreSQL (Serverless v2, 0.5-2 ACU) | ~$50-90+/month | ~$0.10-0.15/hour |
| ECS Fargate (1 task) | ~$15-30/month | ~$0.02-0.05/hour |
| Application Load Balancer | ~$16/month | ~$0.02/hour |
| **Total** | **~$120-200+/month** | **well under $1/hour** |

`database_stack.py` is deliberately configured so `cdk destroy` leaves
nothing billing behind it (no final Aurora snapshot -- see that file's
comments). The risk is forgetting to destroy it, not the short-term cost of
testing it.

## Synthesize (no AWS account needed)

```bash
cd infra/cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cdk synth ItHelpdeskEmailIngestionStack \
  --context fastapi_base_url=https://your-deployed-fastapi.example.com \
  --context it_support_email=it-support@your-domain.edu

cdk synth ItHelpdeskKnowledgeBaseStack \
  --context dashboard_origins=http://localhost:3000,https://your-dashboard.example.com

cdk synth ItHelpdeskNetworkStack
cdk synth ItHelpdeskDatabaseStack
cdk synth ItHelpdeskRegistryStack
cdk synth ItHelpdeskComputeStack
```
This prints the generated CloudFormation template for one stack -- useful to
sanity-check it without touching any real AWS resources or needing
credentials. `cdk list` shows all six stack names together.

## Deploy (you run this -- needs a real, bootstrapped AWS account)

```bash
cd infra/cdk
source .venv/bin/activate
cdk bootstrap                          # once per AWS account/region
```

**Email ingestion:**
```bash
cdk deploy ItHelpdeskEmailIngestionStack \
  --context fastapi_base_url=https://your-deployed-fastapi.example.com \
  --context it_support_email=it-support@your-domain.edu
# Then, once per deploy that changes the receipt rule set (CDK has no
# resource for "activate this rule set" -- it's a plain API call):
aws ses set-active-receipt-rule-set --rule-set-name <ReceiptRuleSetName from the stack output>
```

**Knowledge-base storage:**
```bash
cdk deploy ItHelpdeskKnowledgeBaseStack \
  --context dashboard_origins=https://your-dashboard.example.com
# CDK can't mint IAM access keys -- run once, using the KnowledgeBaseApiUserName
# from the stack output:
aws iam create-access-key --user-name <KnowledgeBaseApiUserName from the stack output>
# Put the resulting AccessKeyId/SecretAccessKey into backend/.env as
# AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, and KnowledgeBaseBucketName
# (also in the stack output) into KNOWLEDGE_STORAGE_S3_BUCKET.
```

**Hosting (network -> database -> registry -> compute, in that order):**
```bash
cdk deploy ItHelpdeskNetworkStack

# aurora_publicly_accessible defaults to TRUE (this project's current need:
# running `python -m migrations.run_migrations` directly from a local
# machine). Always pass your own IP, not the wide-open default:
cdk deploy ItHelpdeskDatabaseStack \
  --context aurora_publicly_accessible=true \
  --context aurora_allowed_cidr=$(curl -s https://checkip.amazonaws.com)/32

# Fetch the generated password (also printed in the stack's own output):
aws secretsmanager get-secret-value \
  --secret-id <AuroraSecretArn from the stack output> \
  --query SecretString --output text | python3 -m json.tool

# Run migrations directly against it from your machine:
cd ../../backend && source .venv/bin/activate
DATABASE_URL="postgresql://helpdesk_admin:<password>@<AuroraClusterEndpoint>:5432/helpdesk" \
  python -m migrations.run_migrations
cd ../infra/cdk

# Once migrations are done, redeploy with public access OFF -- see
# database_stack.py's module docstring for what this actually changes:
cdk deploy ItHelpdeskDatabaseStack --context aurora_publicly_accessible=false
```

```bash
cdk deploy ItHelpdeskRegistryStack
# Build and push the backend image (the ECR push command is also printed
# in this stack's own PushInstructions output):
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker build -t <RepositoryUri from the stack output>:latest ../../backend
docker push <RepositoryUri from the stack output>:latest

cdk deploy ItHelpdeskComputeStack \
  --context knowledge_base_bucket_name=<from the knowledge-base stack's output> \
  --context it_support_email=it-support@your-domain.edu
# BackendUrl in the stack output is the real, public FastAPI URL --
# this is the fastapi_base_url value the email ingestion stack needs.
```

Run `cdk deploy` with no stack name to deploy everything at once (CDK will
ask you to confirm each stack's IAM changes in dependency order).

## Test the Lambda code (no AWS account needed -- S3 is mocked with moto)

```bash
cd infra/lambda/email_ingestion
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

## Tear down (to stop the hosting stacks' ongoing cost)

```bash
cd infra/cdk
source .venv/bin/activate
cdk destroy ItHelpdeskComputeStack ItHelpdeskDatabaseStack ItHelpdeskRegistryStack ItHelpdeskNetworkStack
```
`ItHelpdeskEmailIngestionStack` and `ItHelpdeskKnowledgeBaseStack` cost
close to nothing left running -- no need to destroy those just to stop the
hosting bill.
