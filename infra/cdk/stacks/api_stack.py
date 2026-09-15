"""
The backend's only public entry point. compute_stack.py's ALB is
internal (VPC-only, no internet route) -- this stack puts an HTTP API
Gateway in front of it, connected over a VPC Link (a set of
AWS-managed ENIs inside the VPC's private subnets, not a public
internet hop) rather than exposing the ALB itself to the internet.

Why API Gateway instead of just making the ALB public again: this is
the standard "three-tier" shape the rest of this deployment follows --
public edge (API Gateway here, the frontend's own ALB in
frontend_stack.py) / private application tier (this VPC Link -> the
internal ALB -> ECS Fargate) / private data tier (Aurora, reachable
only from inside the VPC). Nothing in the application tier or data tier
has a route to the internet in the inbound direction; only the two
named edge resources do.

The resulting endpoint (this stack's ApiGatewayUrl output) is what
frontend/.env.local / the frontend Docker build's NEXT_PUBLIC_API_BASE_URL
build-arg should point at, and what email_stack.py's fastapi_base_url
context value should be, once this is deployed. It's a plain HTTP API
with a single catch-all proxy route to the ALB -- FastAPI's own routing
(app/main.py) still decides what each path does; API Gateway here is a
transparent pass-through, not a second routing layer, and adds no CORS
handling of its own (app/main.py's CORSMiddleware, driven by
CORS_ALLOWED_ORIGINS, is what actually answers preflight requests).

This endpoint is stable (same hostname) across every redeploy of this
stack as long as the HttpApi construct itself isn't replaced -- that's
what makes it safe to hardcode as a GitHub Actions repository variable
(API_GATEWAY_URL) for the frontend's image build, rather than needing
to be looked up fresh on every CI run.
"""
from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from constructs import Construct


class ApiGatewayStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        backend_listener: elbv2.IApplicationListener,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # No explicit security_groups passed -- this would otherwise be
        # the natural place to scope one down to "only reach the backend
        # ALB," but compute_stack.py's ALB already grants ingress by VPC
        # CIDR rather than by security-group reference (see that
        # stack's comments): a live SG object created here and handed to
        # that stack's `alb.connections.allow_from(...)` would need this
        # stack to exist before ComputeStack deploys, while ComputeStack
        # -> ApiGatewayStack (for the listener) already goes the other
        # way -- a cyclic stack dependency. VpcLink falls back to the
        # VPC's default security group, which is fine given the CIDR
        # rule already covers "anything inside this VPC."
        vpc_link = apigwv2.VpcLink(
            self,
            "BackendVpcLink",
            vpc=vpc,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        integration = integrations.HttpAlbIntegration(
            "BackendAlbIntegration",
            backend_listener,
            vpc_link=vpc_link,
        )

        # default_integration -- one catch-all route ($default) proxying
        # every path/method to the backend ALB. No per-route mapping
        # here because FastAPI already owns real routing (app/main.py);
        # API Gateway's job in this architecture is purely "get a public
        # HTTPS request into the VPC," not "know what /tickets means."
        http_api = apigwv2.HttpApi(
            self,
            "HelpdeskHttpApi",
            api_name="it-helpdesk-backend-api",
            default_integration=integration,
        )

        CfnOutput(
            self,
            "ApiGatewayUrl",
            value=http_api.url or "",
            description="The backend's real public URL -- use this for NEXT_PUBLIC_API_BASE_URL, fastapi_base_url, and EMAIL_WEBHOOK_DEV_MODE=false webhook targets",
        )
