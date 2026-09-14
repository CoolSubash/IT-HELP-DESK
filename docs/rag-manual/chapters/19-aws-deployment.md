# AWS Deployment Considerations

## Scope of this chapter

Everything elsewhere in this manual was verified against a local development environment: a local Docker Postgres container, the local-disk storage backend, and the deterministic development embedding provider -- none of it required an AWS account. This chapter covers what changes when this phase's components move to a real AWS deployment. None of the infrastructure described here was provisioned or deployed during this implementation; this is deployment guidance, not a deployment report, and is written as such.

## Bedrock: enabling and permitting the embedding model

`EMBEDDING_PROVIDER=bedrock` switches `app/rag/embeddings/service.py` to `BedrockEmbeddingProvider` (Chapter 5), which calls `amazon.titan-embed-text-v2:0` via `bedrock-runtime`'s `InvokeModel` API. Two things must be true in the target AWS account/region before this works:

1. **Model access must be explicitly enabled.** Bedrock gates access to each foundation model per AWS account and region -- this is a one-time console action (or an equivalent API call) granting the account permission to invoke this specific model; `InvokeModel` calls fail until this is done, independent of IAM permissions.
2. **The API server's IAM identity needs `bedrock:InvokeModel`, scoped to this specific model.** A minimal policy, resource-scoped rather than wildcarded:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0"
    }
  ]
}
```

`boto3` is already a project dependency (used by the existing SES email integration from an earlier phase), so no new AWS SDK is introduced -- only a new service client and this new permission. `AWS_REGION` should be set to a region where this model is available and enabled.

## S3: private storage for uploaded knowledge-base files

`KNOWLEDGE_STORAGE_BACKEND=s3` switches `app/rag/storage.py` to `S3FileStorage` (Chapter 7/12). Required setup:

1. **A private bucket**, with S3 Block Public Access enabled at the bucket level -- this is the actual privacy guarantee (Chapter 12), not any per-object ACL; `S3FileStorage` deliberately never passes an ACL that could override it.
2. **`KNOWLEDGE_STORAGE_S3_BUCKET`** set to that bucket's name.
3. **An IAM policy** granting the API server's identity `s3:PutObject`/`s3:GetObject`, scoped to the specific key prefix this code actually writes under (`knowledge-documents/*`), not the whole bucket or account:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::<bucket-name>/knowledge-documents/*"
    }
  ]
}
```

Enabling default server-side encryption on the bucket is recommended -- it closes the encryption-at-rest gap Chapter 12 names explicitly for the local-storage default, at no cost to application code.

## RDS for PostgreSQL: enabling pgvector

The `vector` extension used throughout this phase (Chapter 6) is available on Amazon RDS for PostgreSQL, but requires two RDS-specific administrative steps beyond what a self-managed Docker Postgres needs: selecting an RDS Postgres engine version that supports the extension, and explicitly allowing it via the RDS parameter group's extension allowlist before `CREATE EXTENSION vector` (already present in `migrations/0006_knowledge_chunks_and_vector.sql`) will succeed. This was confirmed working at version `0.8.6` against the local `pgvector/pgvector:pg16` Docker image during this implementation -- the equivalent RDS engine/extension-version pairing should be confirmed for the specific target RDS instance before relying on it.

**A genuine operational tradeoff worth monitoring as the corpus grows:** the HNSW index this migration builds (Chapter 6) has no training step and works well from an empty table, which is why it was the right choice at this project's current scale (a handful of example documents). As the real corpus grows well beyond that -- into the range where a full index rebuild becomes a meaningful operation -- HNSW's build time and memory usage grow with corpus size, and a full rebuild is generally more expensive than IVFFlat's. This is not a concern at the scale this phase actually operated at, but is worth watching as a real deployment's document count grows; it would be reasonable to revisit this specific tradeoff if and when that happens, rather than pre-optimizing for a scale this project hasn't reached.

## Networking and least privilege

phase7.md section 18's "database access is restricted" requirement (Chapter 12) is fundamentally an infrastructure concern, not something this phase's application code can enforce on its own. In a real deployment, this means VPC security groups that allow inbound Postgres connections only from the API server's own security group -- never `0.0.0.0/0` -- and, more broadly, keeping the database off any public subnet entirely.

## Secrets and credentials

`.env.example`'s `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` fields exist for local development, where there's no AWS-native identity to assume. **They should not be used directly in a real AWS deployment.** The recommended pattern is for the API server to run under an IAM role -- an ECS task role, an EC2 instance profile, or the equivalent for whatever compute platform is chosen -- so that `boto3`'s default credential chain picks up short-lived, automatically-rotated credentials with no long-lived access key stored anywhere, environment variable or otherwise. This is standard AWS practice generally, not specific to this project, but is worth stating explicitly here since the local `.env.example` file's presence could otherwise be misread as "the" credential mechanism rather than a development-only convenience.

## Cost awareness

Two usage-proportional costs are introduced by enabling the production paths: Bedrock Titan embedding calls are billed per input token, and S3 storage/requests follow standard S3 pricing. Both are small at this project's current example-document scale (eight documents, a handful of chunks each) and become worth monitoring only if ingestion volume grows meaningfully -- for instance, a bulk historical-documentation import significantly larger than this project's current seed corpus.

## Deployment checklist

Every setting that must change from its local-development default before this phase's components are genuinely production-ready:

1. `EMBEDDING_PROVIDER=bedrock`, with Bedrock model access granted and the IAM policy above attached.
2. `KNOWLEDGE_STORAGE_BACKEND=s3` and `KNOWLEDGE_STORAGE_S3_BUCKET` set, with the bucket privately configured and the IAM policy above attached.
3. The target Postgres instance (RDS or otherwise) has the `vector` extension enabled at the engine/parameter-group level.
4. Database network access restricted to the API server's own security group.
5. AWS credentials sourced from an IAM role, not static access keys.
6. Reiterating Chapter 12's central point: `require_admin`'s `X-Admin-Id` header check is a development-phase stand-in, not real authentication (Chapter 12 explains exactly what it does and doesn't guarantee) -- this API should sit behind either real authentication or a network-level restriction (a private VPC, a VPN, an authenticating API gateway in front of it) before it is exposed beyond a fully trusted internal network.
