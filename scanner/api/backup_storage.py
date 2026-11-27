from pathlib import Path

from django.views.decorators.http import require_http_methods
from api.helpers import error_response, json_response, require_permission
from core.models import BackupArtifact, Device
from services import auth
from services.object_scope import device_in_scope
from services.mikrotik_backup import MikrotikBackup, MikrotikBackupError
from services.backup_artifacts import verify_artifact


@require_http_methods(["GET"])
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def artifact_integrity(request):
    name = request.GET.get("device", "")
    kind = request.GET.get("kind", "")
    filename = request.GET.get("file", "")
    device = Device.objects.filter(name=name).first()
    if not device or not device_in_scope(request.api_user, device):
        return error_response("Device unavailable", status=403)
    if kind not in ("bin", "rsc") or not filename or Path(filename).name != filename:
        return error_response("Invalid artifact", status=400)
    artifact = BackupArtifact.objects.filter(device=device, kind=kind, filename=filename).first()
    try:
        path = MikrotikBackup().resolve_download(name, kind, filename)
    except MikrotikBackupError:
        return json_response({"status": "missing"})
    if not artifact:
        return json_response({"status": "untracked"})
    try:
        return json_response({**verify_artifact(artifact, path), "remote_status": artifact.remote_status})
    except OSError:
        return error_response("Artifact unavailable", status=503)
