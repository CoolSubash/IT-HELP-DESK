"""
Shared VPC for Aurora PostgreSQL (database_stack.py) and the ECS-hosted
FastAPI backend (compute_stack.py). Its own stack, not folded into
either of those, so it has its own lifecycle -- tearing down the
database or compute stack for a cost-saving pause doesn't force
recreating the network underneath them.
"""
from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # nat_gateways=1, not CDK's default of one-per-AZ: a second NAT
        # gateway buys AZ-redundant egress, which this project's scale
        # doesn't need and costs another ~$32/month sitting idle. One
        # gateway is a single point of failure for outbound internet
        # from the private subnets (Bedrock calls, pulling container
        # image layers) -- an acceptable tradeoff here, revisit if this
        # ever needs real production HA.
        #
        # Two subnet tiers, not three: PUBLIC (has a route to the
        # Internet Gateway -- the ALB lives here, and Aurora too when
        # database_stack.py's publicly_accessible flag is on) and
        # PRIVATE_WITH_EGRESS (routes outbound through the NAT gateway,
        # no inbound from the internet -- where compute_stack.py's
        # Fargate tasks live when NOT using the assign_public_ip cost
        # shortcut). No isolated/no-egress tier -- nothing here needs
        # to be unable to reach the internet at all.
        self.vpc = ec2.Vpc(
            self,
            "HelpdeskVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(
                    name="Private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24
                ),
            ],
        )
