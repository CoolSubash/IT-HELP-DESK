"""
Runs the FastAPI backend as a container on ECS Fargate, behind a public
Application Load Balancer. This is the piece that makes
docs/rag-manual's "Lambda has to reach a real, public FastAPI URL" gap
(email ingestion) and the dashboard's own API calls both actually
possible from outside this machine -- before this stack, FastAPI only
ever ran as `uvicorn` on localhost.

Uses the aws_ecs_patterns.ApplicationLoadBalancedFargateService L3
construct rather than hand-wiring ECS service + target group + listener
+ ALB separately: it's the same resources CloudFormation would end up
with either way, with far less code (and far less surface area to get a
health check or security group rule subtly wrong on a construct this
security-sensitive).

The backend image needs to exist in ECR before this stack's service can
start successfully -- see registry_stack.py's PushInstructions output.
"""
from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
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
            "EMAIL_PROVIDER": "dev",  # no real SES deployment exists yet -- see email_stack.py
            "IT_SUPPORT_EMAIL": it_support_email,
            "EMAIL_WEBHOOK_DEV_MODE": "true",
            "KNOWLEDGE_STORAGE_BACKEND": "s3",
            "EMBEDDING_PROVIDER": "dev",  # switch to "bedrock" via redeploy once ready -- IAM permission is already granted below
            "AWS_REGION": self.region,
            "DB_HOST": database_cluster.cluster_endpoint.hostname,
            "DB_PORT": str(database_cluster.cluster_endpoint.port),
            "DB_NAME": "helpdesk",
        }
        if knowledge_base_bucket_name:
            environment["KNOWLEDGE_STORAGE_S3_BUCKET"] = knowledge_base_bucket_name

        secrets = {
            "DB_USER": ecs.Secret.from_secrets_manager(database_cluster.secret, field="username"),
            "DB_PASSWORD": ecs.Secret.from_secrets_manager(database_cluster.secret, field="password"),
        }

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "HelpdeskFargateService",
            cluster=cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            public_load_balancer=True,
            # Fargate tasks stay in the private subnets (no public IP of
            # their own) -- only the load balancer is internet-facing.
            # The NAT gateway network_stack.py already provisions (for
            # Aurora's private-mode option) is what gives these tasks
            # their own outbound path (pulling image layers, calling
            # Bedrock), so there's no extra NAT cost from this choice.
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

        CfnOutput(self, "BackendUrl", value=f"http://{service.load_balancer.load_balancer_dns_name}")
        CfnOutput(self, "EcsClusterName", value=cluster.cluster_name)
        CfnOutput(self, "EcsServiceName", value=service.service.service_name)
