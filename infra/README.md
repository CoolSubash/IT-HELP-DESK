# infra

AWS infrastructure-as-code for **Phase 5A** (inbound email ingestion),
**Phase 7** (knowledge-base document storage), and **hosting** -- a
three-tier deployment (public edges / private application tier / private
data tier) for both the FastAPI backend and the Next.js dashboard. See
the root README's "Phase 5" section for the email flow's full architecture
explanation, and `docs/rag-manual`'s AWS deployment chapter for the
knowledge-base side. This file is the "how do I run this folder" quick
reference, both for the automatic pipeline and for running any single
stack by hand.

## Architecture

```
Internet
   |
   |-- https:// --> [ API Gateway (api_stack.py) ] --VPC Link-->--+
   |                                                               |
   `-- http:// --> [ Frontend ALB (frontend_stack.py) ]            |
                          |                                        |
                    VPC ("HelpdeskVpc", network_stack.py)          |
                    +------------------------------------------+   |
                    | Public subnets: both ALBs above,          |   |
                    |   Aurora when aurora_publicly_accessible  |   |
                    |------------------------------------------|   |
                    | Private subnets (NAT egress only):        |   |
                    |   Frontend ECS Fargate <--- image tier    |   |
                    |   Backend ALB (internal) <-----------------+
                    |        |                                  |
                    |   Backend ECS Fargate (compute_stack.py)  |
                    |        |                                  |
                    |   Aurora PostgreSQL (database_stack.py)   |
                    +------------------------------------------+
```

Frontend and backend are each their own ECS Fargate service; only the
backend sits behind API Gateway rather than its own public ALB (see
`api_stack.py`'s module docstring for why). Aurora is always inside the
VPC, reachable from the backend over the VPC's internal network either
way -- `aurora_publicly_accessible` (default `true`, see
`database_stack.py`) is purely about whether it's *also* reachable from
outside the VPC, currently kept on so migrations can run without a
bastion host; `.github/workflows/deploy.yml`'s `migrate` job opens (and
immediately revokes) access for its own runner's IP on every run rather
than leaving a standing hole open.

```
infra/
  cdk/                     CDK app -- describes the AWS resources
    app.py                   instantiates every stack below
    cdk.json
    requirements.txt
    stacks/
      github_oidc_stack.py     One-time, deployed by hand: lets GitHub Actions deploy everything else
      email_stack.py           Phase 5A: SES -> S3 -> Lambda -> FastAPI
      knowledge_base_stack.py  Phase 7: S3 bucket + IAM user for KB document storage
      network_stack.py         VPC shared by every stack below
      database_stack.py        Aurora PostgreSQL (private data tier)
      registry_stack.py        ECR repositories for both container images
      compute_stack.py         Backend: ECS Fargate + INTERNAL ALB
      api_stack.py             Public edge for the backend: HTTP API Gateway + VPC Link
      frontend_stack.py        Frontend: ECS Fargate + PUBLIC ALB
  lambda/email_ingestion/   The actual Lambda code the email stack deploys
    handler.py               entry point
    email_parser.py           .eml -> NormalizedEmail (stdlib only)
    fastapi_client.py         HTTPS POST to FastAPI (stdlib only)
    models.py                 NormalizedEmail dataclass
    requirements-dev.txt      pytest + moto (test-only; nothing is needed at runtime)
    tests/
```

Real dependency chains (CDK enforces these automatically via
`add_dependency` in `app.py`): `ItHelpdeskComputeStack` needs
`ItHelpdeskNetworkStack`, `ItHelpdeskDatabaseStack`, and
`ItHelpdeskRegistryStack`; `ItHelpdeskApiStack` needs
`ItHelpdeskComputeStack` (it wraps that stack's ALB listener);
`ItHelpdeskFrontendStack` needs `ItHelpdeskNetworkStack` and
`ItHelpdeskRegistryStack`. `ItHelpdeskEmailIngestionStack`,
`ItHelpdeskKnowledgeBaseStack`, and `ItHelpdeskGithubOidcStack` don't
depend on any of the others.

## Automatic deployment (CI/CD) -- push to `main` and it deploys itself

`.github/workflows/deploy.yml` deploys every stack above (except
`ItHelpdeskGithubOidcStack`) and builds/pushes both container images on
every push to `main`. **You can watch it happen visually**: open the
Actions tab on GitHub for this repo, click the running workflow, and it
renders the job graph below as a live DAG (each box goes
queued -> running -> green, with the same `needs:` shape this file
describes) -- no separate tool needed for that.

```
deploy-foundation --> migrate ------------------\
        \--> build-backend --------------------- deploy-backend --> build-frontend --> deploy-frontend
                                                        \--------------------------> deploy-email
```

**One-time setup, before the first push can deploy anything** (this is
the only step that isn't itself automated -- see
`github_oidc_stack.py`'s module docstring for exactly why it can't be):

```bash
cd infra/cdk
source .venv/bin/activate
cdk bootstrap                                    # once per AWS account/region
cdk deploy ItHelpdeskGithubOidcStack \
  -c github_org=<your-github-username-or-org> \
  -c github_repo=<this-repo-name>
```

Then, in this GitHub repo's Settings -> Secrets and variables -> Actions
-> **Variables** tab (not Secrets -- none of these are sensitive), add:

| Variable | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | the `DeployRoleArn` output from the command above |
| `IT_SUPPORT_EMAIL` | your real IT support address (optional -- defaults to `it-support@university.edu`) |

That's it. Push to `main`, and everything else -- bootstrap, all nine
stacks (minus the OIDC one), both images, migrations -- happens on its
own from there. The very first run deploys the backend before any
frontend exists yet, so its CORS origin falls back to
`app/config.py`'s local-dev default; the *second* push onward picks up
the real, now-existing frontend URL automatically (see
`deploy.yml`'s own comments for exactly why).

## Manual / local commands (still useful for testing a single stack)

### Cost -- read this before deploying the hosting stacks

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

### Synthesize (no AWS account needed)

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
cdk synth ItHelpdeskApiStack
cdk synth ItHelpdeskFrontendStack
```
This prints the generated CloudFormation template for one stack -- useful to
sanity-check it without touching any real AWS resources or needing
credentials. `cdk list` shows every stack name together.

### Deploy (you run this -- needs a real, bootstrapped AWS account)

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
# The backend's ALB is internal now (see compute_stack.py) -- its
# InternalBackendUrl output is unreachable from outside the VPC on
# purpose. Deploy the API stack next to get a real public URL:

cdk deploy ItHelpdeskApiStack
# ApiGatewayUrl in the stack output is the real, public FastAPI URL --
# this is the fastapi_base_url value the email ingestion stack needs,
# and the NEXT_PUBLIC_API_BASE_URL the frontend image below needs.
```

**Frontend:**
```bash
docker build -t <FrontendRepositoryUri from the registry stack's output>:latest \
  --build-arg NEXT_PUBLIC_API_BASE_URL=<ApiGatewayUrl from above> ../../frontend
docker push <FrontendRepositoryUri from the registry stack's output>:latest

cdk deploy ItHelpdeskFrontendStack
# FrontendUrl in the stack output is what a browser actually loads.
# Once you have it, redeploy the backend so its CORS allowlist includes
# the dashboard's real origin (defaults to localhost otherwise):
cdk deploy ItHelpdeskComputeStack \
  --context knowledge_base_bucket_name=<from the knowledge-base stack's output> \
  --context it_support_email=it-support@your-domain.edu \
  --context cors_allowed_origins=http://<FrontendUrl from above>
```

Run `cdk deploy` with no stack name to deploy everything at once (CDK will
ask you to confirm each stack's IAM changes in dependency order).

### Test the Lambda code (no AWS account needed -- S3 is mocked with moto)

```bash
cd infra/lambda/email_ingestion
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

### Tear down (to stop the hosting stacks' ongoing cost)

```bash
cd infra/cdk
source .venv/bin/activate
cdk destroy ItHelpdeskFrontendStack ItHelpdeskApiStack ItHelpdeskComputeStack \
  ItHelpdeskDatabaseStack ItHelpdeskRegistryStack ItHelpdeskNetworkStack
```
`ItHelpdeskEmailIngestionStack` and `ItHelpdeskKnowledgeBaseStack` cost
close to nothing left running -- no need to destroy those just to stop the
hosting bill.
