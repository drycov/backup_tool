"""Fail-closed restore preflight and short-lived signed confirmation."""
from django.core import signing
from django.conf import settings
from core.models import BackupArtifact, Device
from services.backup_artifacts import verify_artifact
from services.mikrotik_backup import MikrotikBackup, MikrotikBackupError

SALT = "backup-tools.recovery.v1"


def preflight(name, kind, filename, user_id):
    device = Device.objects.filter(name=name, enabled=True).first()
    if not user_id or not device or device.model != "routeros" or device.maintenance:
        raise MikrotikBackupError("Enabled RouterOS device outside maintenance required")
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        raise MikrotikBackupError("Python engine required")
    artifact = BackupArtifact.objects.filter(device=device, kind=kind, filename=filename).first()
    if not artifact:
        raise MikrotikBackupError("Registered immutable artifact required")
    path = MikrotikBackup().resolve_download(name, kind, filename)
    if verify_artifact(artifact, path)["status"] != "verified":
        raise MikrotikBackupError("Artifact integrity check failed")
    payload = {"device": device.pk, "name": name, "ip": device.ip, "kind": kind,
               "file": filename, "sha256": artifact.sha256, "user": user_id}
    return {"confirmation": signing.dumps(payload, salt=SALT), "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes, "device": name, "ip": device.ip,
            "compatibility": "inventory model only; hardware and RouterOS version require manual verification",
            "warning": "Binary restore may reboot; RSC import merges commands and is not a full rollback."}


def validate_confirmation(token, name, kind, filename, user_id):
    try:
        payload = signing.loads(token, salt=SALT, max_age=300)
    except signing.BadSignature as exc:
        raise MikrotikBackupError("Restore confirmation invalid or expired") from exc
    current = preflight(name, kind, filename, user_id)
    expected = signing.loads(current["confirmation"], salt=SALT)
    if payload != expected:
        raise MikrotikBackupError("Restore target or artifact changed")
    return payload
