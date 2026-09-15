"""
ECR repositories for the backend and frontend container images. Its own
stack (not folded into compute_stack.py/frontend_stack.py) so pushed
images survive tearing either compute stack down for a cost-saving
pause -- you don't want to lose every image and have to rebuild/repush
just because compute was deleted overnight.
"""
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class RegistryStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # image_scan_on_push: free vulnerability scanning on every image
        # pushed, no extra infrastructure. lifecycle_rules caps storage
        # (and cost) by keeping only the 10 most recent images instead of
        # accumulating every build forever. RemovalPolicy.DESTROY (with
        # empty_on_delete) so `cdk destroy` actually removes this instead
        # of leaving an orphaned, still-billing repository behind --
        # ECR's default would otherwise refuse to delete a non-empty repo.
        self.repository = ecr.Repository(
            self,
            "BackendRepository",
            repository_name="it-helpdesk-backend",
            image_scan_on_push=True,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=10)],
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        # Same policy as the backend repo -- see frontend_stack.py for
        # what runs this image (ECS Fargate, behind its own public ALB).
        self.frontend_repository = ecr.Repository(
            self,
            "FrontendRepository",
            repository_name="it-helpdesk-frontend",
            image_scan_on_push=True,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=10)],
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        CfnOutput(self, "RepositoryUri", value=self.repository.repository_uri)
        CfnOutput(self, "FrontendRepositoryUri", value=self.frontend_repository.repository_uri)
        CfnOutput(
            self,
            "PushInstructions",
            value=(
                f"aws ecr get-login-password --region {self.region} | "
                f"docker login --username AWS --password-stdin {self.account}.dkr.ecr.{self.region}.amazonaws.com "
                f"&& docker build -t {self.repository.repository_uri}:latest backend/ "
                f"&& docker push {self.repository.repository_uri}:latest "
                f"&& docker build -t {self.frontend_repository.repository_uri}:latest "
                f"--build-arg NEXT_PUBLIC_API_BASE_URL=<ApiGatewayUrl from ItHelpdeskApiStack's output> frontend/ "
                f"&& docker push {self.frontend_repository.repository_uri}:latest"
            ),
        )
