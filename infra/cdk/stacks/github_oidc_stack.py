"""
The one piece of this whole deployment that a human still has to create
by hand, once, with their own AWS credentials -- there's an inherent
chicken-and-egg problem here: GitHub Actions needs AWS permissions to
deploy anything, but it can't grant itself those permissions before it
has any. Every other stack in infra/cdk deploys automatically from
.github/workflows/deploy.yml once this one exists; this file just makes
that one manual step be "run one `cdk deploy`" instead of "click through
the IAM console."

Creates:
  - An OIDC identity provider trusting token.actions.githubusercontent.com
    (GitHub's own OIDC token issuer for Actions workflows).
  - An IAM role that role can assume, trust-scoped to ONE GitHub repo
    (no other repository, fork, or user can assume it) and ONE branch
    (`main` -- a PR from a branch can build/test, but only a merge to
    main can deploy).

No long-lived AWS access keys are stored in GitHub at all: each workflow
run exchanges a short-lived GitHub-issued OIDC token for short-lived AWS
credentials via sts:AssumeRoleWithWebIdentity, valid only for that run.

Deploy once:
    cdk deploy ItHelpdeskGithubOidcStack \
      -c github_org=<your-github-username-or-org> \
      -c github_repo=<this-repo-name>
Then put the DeployRoleArn output into this repo's GitHub Actions
variables as AWS_DEPLOY_ROLE_ARN (Settings -> Secrets and variables ->
Actions -> Variables -- not a Secret, an ARN isn't sensitive on its own).
"""
from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class GithubOidcStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_org: str,
        github_repo: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        provider = iam.OpenIdConnectProvider(
            self,
            "GithubActionsOidcProvider",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )

        # StringEquals on `aud` (always "sts.amazonaws.com" for this use
        # case) + StringLike on `sub` scoped to exactly one repo and one
        # ref -- this is what stops any other GitHub repository (or a PR
        # branch, or a fork) from ever being able to assume this role,
        # even though the OIDC provider itself trusts all of GitHub's
        # token issuer.
        deploy_role = iam.Role(
            self,
            "GithubActionsDeployRole",
            role_name="it-helpdesk-github-actions-deploy",
            assumed_by=iam.FederatedPrincipal(
                provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{github_org}/{github_repo}:ref:refs/heads/main"
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
            description="Assumed by GitHub Actions (main branch only) to deploy infra/cdk's stacks -- see github_oidc_stack.py",
        )

        # Deliberately broad within this account (not scoped down to
        # named resource ARNs the way compute_stack.py's task-role
        # policies are) -- this role IS the deploy mechanism for
        # CloudFormation/ECS/ECR/RDS/VPC/IAM/apigatewayv2 resources
        # across every stack in this app, and CDK deploys routinely need
        # to create/modify IAM roles and policies as part of that (e.g.
        # every new ECS task role). Scoping this further would mean
        # hand-maintaining an allowlist that breaks the next time a
        # stack adds a new resource type. The trust policy above (one
        # repo, one branch) is what actually bounds the blast radius --
        # not this permissions policy.
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                sid="CdkDeployAccess",
                actions=[
                    "cloudformation:*",
                    "ecs:*",
                    "ecr:*",
                    "ec2:*",
                    "elasticloadbalancing:*",
                    "apigateway:*",
                    "rds:*",
                    "secretsmanager:*",
                    "logs:*",
                    "iam:*",
                    # ssm:GetParameter on /cdk-bootstrap/.../version -- the
                    # CDK CLI reads this directly (with the caller's own
                    # credentials, before assuming any bootstrapped role)
                    # on every single `cdk deploy`/`cdk bootstrap` to check
                    # the bootstrap stack's version. Without it, every
                    # deploy from this role would fail at that check.
                    "ssm:*",
                    "s3:*",
                    "lambda:*",
                    "ses:*",
                    "sts:AssumeRole",
                ],
                resources=["*"],
            )
        )

        CfnOutput(
            self,
            "DeployRoleArn",
            value=deploy_role.role_arn,
            description="Put this into GitHub Actions repository VARIABLES (not secrets) as AWS_DEPLOY_ROLE_ARN",
        )
