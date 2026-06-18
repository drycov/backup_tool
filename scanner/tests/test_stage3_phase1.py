"""Stage 3.1: native models, group policy extensions, MikroTik restore."""

from __future__ import annotations

import json

import pytest

from services.group_policies import effective_compliance_sla_hours, save_policy
from services.oxidized_engine.model.registry import get_model, list_native_models
from tests.helpers import login


@pytest.fixture
def authed(client, db):
    from core.models import User
    from services.auth import hash_password, seed_default_admin
    import os

    admin = User.objects.filter(username="admin").first()
    if not admin:
        seed_default_admin()
    else:
        admin.password_hash = hash_password(os.environ.get("ADMIN_PASSWORD", "pytest-admin-pass"))
        admin.must_change_password = False
        admin.save()
    login(client)
    return client


@pytest.mark.django_db
def test_native_models_registry():
    models = list_native_models()
    assert "routeros" in models
    assert "ios" in models
    assert "junos" in models
    assert "eos" in models
    assert get_model("cisco").__class__.__name__ == "IOSModel"
    assert get_model("juniper").__class__.__name__ == "JunOSModel"


@pytest.mark.django_db
def test_group_policy_sla_and_notify():
    saved = save_policy(
        {
            "group_name": "hex",
            "backup_interval_sec": 3600,
            "compliance_sla_hours": 48,
            "notify_telegram": True,
            "maintenance_override": False,
        }
    )
    assert saved.compliance_sla_hours == 48
    assert saved.notify_telegram is True
    assert effective_compliance_sla_hours("hex") == 48


@pytest.mark.django_db
def test_mikrotik_compare_rsc(tmp_path, monkeypatch):
    from services.mikrotik_backup import MikrotikBackup, MikrotikBackupConfig
    from services.mikrotik_restore import compare_backup_files

    cfg = MikrotikBackupConfig(
        bin_dir=tmp_path / "bin",
        rsc_dir=tmp_path / "rsc",
    )
    cfg.bin_dir.mkdir(parents=True)
    cfg.rsc_dir.mkdir(parents=True)
    prefix = "test"
    (cfg.rsc_dir / f"{prefix}_a.rsc").write_text("line1\nline2\n", encoding="utf-8")
    (cfg.rsc_dir / f"{prefix}_b.rsc").write_text("line1\nline2-changed\n", encoding="utf-8")

    def _init(self, config=None):
        self.config = cfg

    monkeypatch.setattr(MikrotikBackup, "__init__", _init)
    monkeypatch.setattr("services.mikrotik_backup.device_file_prefix", lambda name: prefix)
    monkeypatch.setattr("services.mikrotik_restore.device_file_prefix", lambda name: prefix)

    result = compare_backup_files("test", f"{prefix}_a.rsc", f"{prefix}_b.rsc", "rsc")
    assert result["diff_lines"] > 0
    assert "line2-changed" in result.get("diff", "")


@pytest.mark.django_db
def test_restore_api_requires_write(authed, db):
    response = authed.post(
        "/api/oxidized/nodes/nonexistent/backups/restore",
        data=json.dumps({"type": "rsc", "file": "x.rsc"}),
        content_type="application/json",
    )
    assert response.status_code in (400, 404)
