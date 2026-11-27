"""Optional S3-compatible replication; credentials use standard AWS environment."""
import os

import boto3
from botocore.config import Config


def replicate(path, bucket, key, digest):
    client = boto3.client(
        "s3", endpoint_url=os.environ.get("BACKUP_S3_ENDPOINT") or None,
        config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2},
                      s3={"addressing_style": "path"}),
    )
    extra = {"Metadata": {"sha256": digest}}
    if os.environ.get("BACKUP_S3_SSE", "AES256"):
        extra["ServerSideEncryption"] = os.environ.get("BACKUP_S3_SSE", "AES256")
    client.upload_file(str(path), bucket, key, ExtraArgs=extra)
    info = client.head_object(Bucket=bucket, Key=key)
    if info["ContentLength"] != path.stat().st_size or info.get("Metadata", {}).get("sha256") != digest:
        raise RuntimeError("Remote artifact metadata mismatch")
