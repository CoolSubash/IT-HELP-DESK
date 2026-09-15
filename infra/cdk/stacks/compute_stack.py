"""
Runs the FastAPI backend as a container on ECS Fargate, behind an
INTERNAL Application Load Balancer (no direct internet route -- see the
module docstring in api_stack.py for what actually exposes this
publicly). This is the piece that makes docs/rag-manual's "Lambda has to
reach a real FastAPI URL" gap (email ingestion) and the dashboard's own
API calls both actually possible from outside this machine -- before
this stack, FastAPI only ever ran as `uvicorn` on localhost.

Uses the aws_ecs_patterns.ApplicationLoadBalancedFargateService L3
construct rather than hand-wiring ECS service + target group + listener
+ ALB separately: it's the same resources CloudFormation would end up
with either way, with far less code (and far less surface area to get a
health check or security group rule subtly wrong on a construct this
security-sensitive). The ALB itself is still constructed explicitly
(passed in via `load_balancer=`) rather than left to the pattern's own
default, so `internal`/`vpc_subnets` are both spelled out instead of
relying on the pattern's implicit "internal -> whichever subnets aren't
public" behavior.

The backend image needs to exist in ECR before this stack's service can
start successfully -- see registry_stack.py's PushInstructions output.
"""
from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        repository: ecr.IRepository,
        database_cluster: rds.DatabaseCluster,
        *,
        knowledge_base_bucket_name: str | None = None,
        it_support_email: str = "it-support@university.edu",
        image_tag: str = "latest",
        email_provider: str = "ses",
        cors_allowed_origins: list[str] | None = None,
        email_webhook_secret_arn: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cluster = ecs.Cluster(self, "HelpdeskEcsCluster", vpc=vpc, container_insights=True)

        # Plain environment variables (non-secret config) vs. `secrets`
        # (pulled from Secrets Manager at container start, never baked
        # into the task definition or visible in `describe-tasks`) --
        # DB_USER/DB_PASSWORD below are the only two that actually need
        # that treatment; everything else here is fine as plain config.
        #
        # No DATABASE_URL set directly: app/config.py expects one
        # connection-string env var, but the password only exists inside
        # Aurora's generated secret at deploy time, not as something
        # this stack's Python code could concatenate into a plain string
        # ahead of time. backend/entrypoint.sh builds DATABASE_URL from
        # these DB_* parts (and the injected secrets) at container
        # startup instead -- see that file for why this lives in the
        # container's entrypoint rather than a change to app/config.py.
        environment = {
            "ENVIRONMENT": "production",
            # Defaults to "ses" -- ItHelpdeskEmailIngestionStack's SES
            # setup (receiving) and this stack's SendRawEmail permission
            # just below (sending) both exist for real now. Pass
            # -c email_provider=dev to fall back to log-only sending for
            # a test deploy that shouldn't email real people.
            "EMAIL_PROVIDER": email_provider,
            "IT_SUPPORT_EMAIL": it_support_email,
            # False (real signature-secret checking, app/routers/email.py's
            # _verify_webhook_secret) once ItHelpdeskEmailIngestionStack's
            # own secret is known and wired in as EMAIL_WEBHOOK_SECRET
            # below. True (unauthenticated -- anyone who finds this
            # stack's public API Gateway URL can POST fake emails) only
            # as a fallback for a deploy that has never had the email
            # stack deployed yet -- see infra/README.md and
            # .github/workflows/deploy.yml's deploy-backend job for why
            # that's a real, temporary first-run state, not a permanent
            # default choice.
            "EMAIL_WEBHOOK_DEV_MODE": "false" if email_webhook_secret_arn else "true",
            "KNOWLEDGE_STORAGE_BACKEND": "s3",
            "EMBEDDING_PROVIDER": "dev",  # switch to "bedrock" via redeploy once ready -- IAM permission is already granted below
            "AWS_REGION": self.region,
            "DB_HOST": database_cluster.cluster_endpoint.hostname,
            "DB_PORT": str(database_cluster.cluster_endpoint.port),
            "DB_NAME": "helpdesk",
            # app/config.py's cors_allowed_origins -- defaults to the
            # local-dev list (see that file) if not overridden. Pass
            # -c cors_allowed_origins=https://<frontend ALB DNS or
            # custom domain> at deploy time once frontend_stack.py has
            # been deployed at least once (its ALB DNS is stable across
            # redeploys -- see infra/README.md).
            **({"CORS_ALLOWED_ORIGINS": ",".join(cors_allowed_origins)} if cors_allowed_origins else {}),
        }
        if knowledge_base_bucket_name:
            environment["KNOWLEDGE_STORAGE_S3_BUCKET"] = knowledge_base_bucket_name

        secrets = {
            "DB_USER": ecs.Secret.from_secrets_manager(database_cluster.secret, field="username"),
            "DB_PASSWORD": ecs.Secret.from_secrets_manager(database_cluster.secret, field="password"),
        }
        if email_webhook_secret_arn:
            # Imported by ARN (a plain string, like knowledge_base_bucket_name
            # above), not a live cross-stack construct reference -- avoids
            # adding a CloudFormation dependency between this stack and
            # ItHelpdeskEmailIngestionStack in either direction. ecs.Secret
            # handles granting this task's execution role
            # secretsmanager:GetSecretValue on exactly this one secret
            # automatically, same as the DB_USER/DB_PASSWORD secrets above.
            imported_webhook_secret = secretsmanager.Secret.from_secret_complete_arn(
                self, "ImportedEmailWebhookSecret", email_webhook_secret_arn
            )
            secrets["EMAIL_WEBHOOK_SECRET"] = ecs.Secret.from_secrets_manager(imported_webhook_secret)

        # internal=True: no internet gateway route, no public IP -- this
        # ALB is reachable only from inside the VPC. api_stack.py's
        # API Gateway VPC Link is the only thing that reaches it from
        # outside the VPC's own subnets, over AWS's private network
        # rather than the public internet. Placed in the same
        # PRIVATE_WITH_EGRESS subnets as the Fargate tasks themselves
        # (not PUBLIC) -- an internal ALB has no need for a subnet with
        # an internet-gateway route.
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "BackendAlb",
            vpc=vpc,
            internet_facing=False,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "HelpdeskFargateService",
            cluster=cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            load_balancer=alb,
            public_load_balancer=False,
            # False, not the pattern's own default (open to 0.0.0.0/0) --
            # the rule added just below (VPC CIDR only) replaces it. Not
            # a direct security-group reference to api_stack.py's VPC
            # Link: ApiGatewayStack already depends on this stack for
            # the listener itself, so a live SG-to-SG reference the
            # other way would be a cyclic stack dependency -- the exact
            # problem database_stack.py's own CIDR-based Aurora rule
            # documents avoiding, for the same reason.
            open_listener=False,
            # Fargate tasks stay in the private subnets (no public IP of
            # their own) -- the NAT gateway network_stack.py already
            # provisions (for Aurora's private-mode option) is what
            # gives these tasks their own outbound path (pulling image
            # layers, calling Bedrock), so there's no extra NAT cost
            # from this choice.
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            assign_public_ip=False,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_ecr_repository(repository, tag=image_tag),
                container_port=8000,
                environment=environment,
                secrets=secrets,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="helpdesk-backend", log_retention=logs.RetentionDays.TWO_WEEKS
                ),
            ),
        )

        # ALB target group health check -- matches the existing
        # GET /health endpoint (app/routers/health.py), which already
        # confirms the database connection works, not just that the
        # process started.
        service.target_group.configure_health_check(path="/health", healthy_http_codes="200")

        # Lets api_stack.py's VPC Link ENIs (which live in these same
        # PRIVATE_WITH_EGRESS subnets, see that stack) reach this ALB.
        # VPC-CIDR-scoped, not a reference to the VPC Link's own security
        # group, for the same cyclic-dependency reason as the comment on
        # open_listener above.
        alb.connections.allow_from(
            ec2.Peer.ipv4(vpc.vpc_cidr_block),
            ec2.Port.tcp(80),
            "Anything inside this VPC (concretely: api_stack.py API Gateway VPC Link) -- see open_listener comment above for why this is not a security-group reference",
        )

        # No security-group rule added here connecting to Aurora --
        # database_stack.py already allows the whole VPC's CIDR in on
        # 5432 (see that file's comment for why it's CIDR-based rather
        # than a direct cross-stack security-group reference, which
        # would create a cyclic stack dependency given ComputeStack
        # already depends on DatabaseStack for the cluster itself).
        # These Fargate tasks living in the VPC is what makes that rule
        # apply to them; nothing to add on this side.

        # --- IAM: task role (what the running container is allowed to
        # do against AWS APIs), distinct from the task execution role
        # ApplicationLoadBalancedFargateService already sets up
        # automatically for ECR pull + CloudWatch Logs. No static AWS
        # credentials are set as environment variables anywhere in this
        # stack -- app/rag/storage.py's S3FileStorage and
        # bedrock_provider.py both fall back to boto3's default
        # credential chain when settings.aws_access_key_id isn't set,
        # which inside an ECS task means these temporary,
        # automatically-rotated task role credentials. This is the
        # production-recommended path over the KnowledgeBaseApiUser IAM
        # user (knowledge_base_stack.py) that local/non-AWS development
        # uses instead. ---
        if knowledge_base_bucket_name:
            bucket = s3.Bucket.from_bucket_name(self, "ImportedKnowledgeBaseBucket", knowledge_base_bucket_name)
            service.task_definition.task_role.add_to_principal_policy(
                iam.PolicyStatement(
                    sid="ReadWriteDeleteKnowledgeDocumentsOnly",
                    actions=["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
                    resources=[bucket.arn_for_objects("knowledge-documents/*")],
                )
            )

        # Granted proactively (even though EMBEDDING_PROVIDER=dev above)
        # so switching to EMBEDDING_PROVIDER=bedrock later is a plain
        # redeploy of this stack's environment, not a second IAM change
        # -- see app/rag/embeddings/bedrock_provider.py.
        service.task_definition.task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="InvokeTitanEmbeddingModelOnly",
                actions=["bedrock:InvokeModel"],
                resources=[f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"],
            )
        )

        # Outbound admin replies -- app/email/ses_provider.py's
        # AWSSESProvider.send_email() calls ses:SendRawEmail directly
        # from this same FastAPI process (no Lambda involved on the
        # outbound side -- see that module's docstring for why sending
        # doesn't need the S3+Lambda bridge receiving does). SES has no
        # per-identity resource ARN to scope this to the way S3/Bedrock
        # above are scoped to one bucket prefix / one model, but the
        # ses:FromAddress condition achieves the same intent: this task
        # role can only ever send AS it_support_email, never spoof an
        # arbitrary from-address, even though the action itself has to
        # be granted on "*".
        service.task_definition.task_role.add_to_principal_policy(
            iam.PolicyStatement(
                sid="SendOutboundReplyEmailOnly",
                actions=["ses:SendRawEmail"],
                resources=["*"],
                conditions={"StringEquals": {"ses:FromAddress": it_support_email}},
            )
        )

        # Exposed for api_stack.py to build its VPC Link integration
        # against -- this is what makes the backend reachable from
        # outside the VPC at all, since the ALB above is internal.
        self.service = service
        self.listener = service.listener

        CfnOutput(
            self,
            "InternalBackendUrl",
            value=f"http://{service.load_balancer.load_balancer_dns_name}",
            description="VPC-internal only -- unreachable from outside the VPC. The public URL is ItHelpdeskApiStack's ApiGatewayUrl output.",
        )
        CfnOutput(self, "EcsClusterName", value=cluster.cluster_name)
        CfnOutput(self, "EcsServiceName", value=service.service.service_name)
