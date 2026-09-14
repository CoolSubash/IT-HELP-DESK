"""
Phase 7 supplement: AWS infrastructure for knowledge-base document
storage.

    Browser --PUT (presigned URL)--> S3 --GetObject--> FastAPI (extract/chunk/embed/store)

Deliberately NOT the same shape as email_stack.py's SES -> S3 -> Lambda
-> FastAPI flow: there is no Lambda here. Knowledge-base document
processing is triggered by an explicit call from the frontend
(POST /admin/knowledge/{id}/complete) after its direct-to-S3 upload
finishes, not by an S3 event notification -- see
backend/app/rag/ingestion_service.py's complete_pending_upload() and
docs/rag-manual's testing/AWS-deployment chapters for why that choice
was made over an event-driven Lambda. If that decision changes later, a
Lambda + S3 event notification would attach here the same way
email_stack.py's does.
"""
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

KNOWLEDGE_DOCUMENTS_KEY_PREFIX = "knowledge-documents/"


class KnowledgeBaseStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # cdk deploy -c dashboard_origins=https://dashboard.example.com,http://localhost:3000
        # Comma-separated -- every origin the browser will PUT an upload
        # from needs to be listed here, or S3 rejects the PUT with a CORS
        # error before this app's own code ever sees the request. Defaults
        # to the two ports `next dev` actually uses locally (see
        # backend/app/main.py's CORSMiddleware -- 3001 is next dev's
        # fallback when 3000 is already taken).
        dashboard_origins_context = self.node.try_get_context("dashboard_origins")
        dashboard_origins = (
            dashboard_origins_context.split(",")
            if dashboard_origins_context
            else ["http://localhost:3000", "http://localhost:3001"]
        )

        # --- S3 ---------------------------------------------------------
        # Same posture as email_stack.py's InboundEmailBucket: SSE-S3
        # encrypted, fully private (BLOCK_ALL -- phase7.md #18's "S3
        # objects are private if S3 is used"), HTTPS-only, and RETAIN on
        # stack deletion since this bucket holds real IT documentation an
        # accidental `cdk destroy` should never be able to take with it.
        #
        # The CORS rule is the one thing email_stack.py's bucket doesn't
        # need and this one does: SES writes to that bucket itself
        # (server-side), but a knowledge-base upload is a *browser*
        # PUTting directly to S3 with a presigned URL
        # (app/rag/storage.py's S3FileStorage.presign_upload_url()) --
        # without this, the browser's PUT is blocked by the browser's own
        # CORS enforcement before S3 even sees it.
        knowledge_base_bucket = s3.Bucket(
            self,
            "KnowledgeBaseBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT],
                    allowed_origins=dashboard_origins,
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
        )

        # --- IAM ----------------------------------------------------------
        # The identity FastAPI's boto3 client signs presigned URLs with
        # and uses for its own reads/writes (app/rag/storage.py's
        # S3FileStorage). An IAM User, not a Role, because this backend
        # runs as a plain long-lived process (local uvicorn today; no
        # ECS/EC2 compute stack exists yet in this repo to attach a role
        # to) -- see the CfnOutput below for the one manual step CDK
        # can't do: minting an actual access key for this user.
        #
        # Scoped narrowly and explicitly (matching email_stack.py's
        # style, not a broad bucket.grant_read_write()): PutObject,
        # GetObject, and DeleteObject, only under knowledge-documents/ --
        # still no ListBucket (nothing in this app ever needs to
        # enumerate the bucket's contents; every read/write/delete
        # already knows its exact key from the database) and no access
        # to any other prefix or bucket. DeleteObject exists so
        # ingestion_service.py's delete_document() (a hard delete) can
        # actually remove the S3 object, not just the database row --
        # earlier versions of this stack omitted it, which is why hard
        # delete used to leave orphaned files in S3; see that function's
        # docstring for the current (fixed) behavior.
        api_user = iam.User(self, "KnowledgeBaseApiUser")
        api_user.add_to_policy(
            iam.PolicyStatement(
                sid="ReadWriteDeleteKnowledgeDocumentsOnly",
                actions=["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
                resources=[knowledge_base_bucket.arn_for_objects(f"{KNOWLEDGE_DOCUMENTS_KEY_PREFIX}*")],
            )
        )

        # --- Outputs ---------------------------------------------------
        CfnOutput(self, "KnowledgeBaseBucketName", value=knowledge_base_bucket.bucket_name)
        CfnOutput(self, "KnowledgeBaseApiUserName", value=api_user.user_name)
        CfnOutput(
            self,
            "NextStep",
            value=(
                "CDK cannot mint IAM access keys (CloudFormation has no resource for it -- "
                "credentials are a security-sensitive one-time output, not something to leave "
                "sitting in a stack's state). Run once: "
                f"aws iam create-access-key --user-name {api_user.user_name} "
                "-- then put its AccessKeyId/SecretAccessKey into backend/.env as "
                "AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, and KnowledgeBaseBucketName above into "
                "KNOWLEDGE_STORAGE_S3_BUCKET."
            ),
        )
