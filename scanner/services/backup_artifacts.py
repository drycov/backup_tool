"""Immutable native backup metadata and optional S3 replication."""
import hashlib
import logging
import os

from core.models import BackupArtifact, Device

logger = logging.getLogger(__name__)


def fingerprint(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def register_artifact(name, kind, path):
    device = Device.objects.get(name=name)
    digest, size = fingerprint(path)
    if not size:
        raise ValueError("Empty backup artifact")
    artifact, created = BackupArtifact.objects.get_or_create(
        device=device, kind=kind, filename=path.name,
        defaults={"sha256": digest, "size_bytes": size},
    )
    if not created and (artifact.sha256 != digest or artifact.size_bytes != size):
        raise ValueError("Artifact identity collision")
    bucket = os.environ.get("BACKUP_S3_BUCKET", "").strip()
    if bucket:
        key = "backups/{}/{}/{}".format(device.pk, kind, path.name)
        try:
            from services.storage_s3 import replicate
            replicate(path, bucket, key, digest)
            artifact.remote_key = key
            artifact.remote_status = "uploaded"
        except Exception:
            logger.exception("backup storage | S3 replication failed | artifact=%s", artifact.pk)
            artifact.remote_status = "failed"
        artifact.save(update_fields=["remote_key", "remote_status"])
    return artifact


def verify_artifact(artifact, path):
    digest, size = fingerprint(path)
    return {"status": "verified" if digest == artifact.sha256 and size == artifact.size_bytes else "mismatch",
            "sha256": digest, "size_bytes": size, "expected_sha256": artifact.sha256}
