"""
Runs the Next.js dashboard as a container on ECS Fargate, behind its own
PUBLIC Application Load Balancer -- the browser-facing edge of the
three-tier shape this deployment follows (frontend edge / backend edge
[api_stack.py] / private application+data tiers). A browser has to be
able to reach the page itself directly, unlike the backend API, which
sits behind API Gateway instead of its own public ALB (see
api_stack.py's module docstring for why those two edges look different).

The Fargate task itself still lives in the VPC's private subnets (no
public IP of its own) -- only this ALB is internet-facing, identical to
compute_stack.py's task placement, just with a public rather than
internal load balancer in front.

frontend/Dockerfile bakes NEXT_PUBLIC_API_BASE_URL into the JS bundle at
*build* time (Next.js inlines NEXT_PUBLIC_* vars into client code, they
can't be swapped at container start the way compute_stack.py's
entrypoint.sh assembles DATABASE_URL from ECS secrets) -- so the image
this stack runs must already have been built against api_stack.py's
ApiGatewayUrl. This stack has no opinion on that; it only runs whatever
image_tag was pushed to the frontend ECR repository.
"""
from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_logs as logs
from constructs import Construct


class FrontendStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        repository: ecr.IRepository,
        *,
        image_tag: str = "latest",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cluster = ecs.Cluster(self, "FrontendEcsCluster", vpc=vpc, container_insights=True)

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "FrontendFargateService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            public_load_balancer=True,
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            assign_public_ip=False,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_ecr_repository(repository, tag=image_tag),
                container_port=3000,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="helpdesk-frontend", log_retention=logs.RetentionDays.TWO_WEEKS
                ),
            ),
        )

        # Next.js's own server responds 200 on "/" once it's up -- no
        # dedicated health-check route exists in the frontend (unlike
        # the backend's GET /health), and none is needed for a
        # stateless page-serving tier like this.
        service.target_group.configure_health_check(path="/", healthy_http_codes="200")

        self.service = service

        CfnOutput(self, "FrontendUrl", value=f"http://{service.load_balancer.load_balancer_dns_name}")
        CfnOutput(self, "EcsClusterName", value=cluster.cluster_name)
        CfnOutput(self, "EcsServiceName", value=service.service.service_name)
