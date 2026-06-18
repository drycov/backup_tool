"""Stage 3.2: TOTP 2FA, LDAP scope, external Oxidized diff."""

from __future__ import annotations

import json

import pyotp
import pytest

from services.ldap_scope import resolve_scope_from_ldap_groups
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
def test_ldap_scope_resolve_from_mappings():
    mappings = [
        {"ldap_group": "CN=NetOps", "allowed_groups": ["hex"], "allowed_sites": ["msk"]},
        {"ldap_group": "CN=RO", "allowed_groups": ["us"], "allowed_sites": []},
    ]
    groups, sites = resolve_scope_from_ldap_groups(["CN=NetOps,DC=corp", "CN=Other"], mappings)
    assert groups == ["hex"]
    assert sites == ["msk"]


@pytest.mark.django_db
def test_totp_login_flow(client, db):
    from core.models import User
    from services.auth import hash_password

    User.objects.create(
        username="totpuser",
        password_hash=hash_password("totp-pass"),
        role="operator",
        auth_source="local",
    )
    login(client, "totpuser", "totp-pass")

    setup = client.get("/api/auth/totp/setup")
    assert setup.status_code == 200
    data = setup.json()
    secret = data["secret"]
    recovery_codes = data["recovery_codes"]
    code = pyotp.TOTP(secret).now()

    enable = client.post(
        "/api/auth/totp/enable",
        data=json.dumps({"secret": secret, "code": code, "recovery_codes": recovery_codes}),
        content_type="application/json",
    )
    assert enable.status_code == 200
    assert enable.json().get("totp_enabled") is True

    client.post("/api/auth/logout")

    login_res = client.post(
        "/api/auth/login",
        data=json.dumps({"username": "totpuser", "password": "totp-pass"}),
        content_type="application/json",
    )
    assert login_res.status_code == 200
    body = login_res.json()
    assert body.get("totp_required") is True
    challenge = body["challenge"]

    bad = client.post(
        "/api/auth/totp",
        data=json.dumps({"challenge": challenge, "code": "000000"}),
        content_type="application/json",
    )
    assert bad.status_code == 401

    good_code = pyotp.TOTP(secret).now()
    verify = client.post(
        "/api/auth/totp",
        data=json.dumps({"challenge": challenge, "code": good_code}),
        content_type="application/json",
    )
    assert verify.status_code == 200
    assert verify.json()["user"]["username"] == "totpuser"


@pytest.mark.django_db
def test_external_oxidized_unified_diff(monkeypatch):
    from services import oxidized_diff

    monkeypatch.setattr(oxidized_diff.settings, "OXIDIZED_ENGINE", "external")
    monkeypatch.setattr(oxidized_diff.settings, "OXIDIZED_URL", "http://oxidized.test")

    versions_meta = {
        "group": "hex",
        "versions": [
            {"oid": "oid-new", "epoch": 200, "num": 2},
            {"oid": "oid-old", "epoch": 100, "num": 1},
        ],
    }

    def fake_versions(name):
        return versions_meta, None

    texts = {
        ("oid-new", 200, 2): "line1\nline2-new\n",
        ("oid-old", 100, 1): "line1\nline2\n",
    }

    class FakeResponse:
        def __init__(self, text):
            self.status_code = 200
            self.text = text

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            if "oid=oid-new" in url:
                return FakeResponse(texts[("oid-new", 200, 2)])
            if "oid=oid-old" in url:
                return FakeResponse(texts[("oid-old", 100, 1)])
            return FakeResponse("")

    monkeypatch.setattr("services.oxidized_client.get_node_versions", fake_versions)
    monkeypatch.setattr(oxidized_diff.httpx, "Client", FakeClient)

    diff, err = oxidized_diff.get_node_diff("sw1", "oid-new")
    assert err is None
    assert diff is not None
    assert "line2-new" in diff["patch"]
    assert diff["stat"]["insertions"] >= 1
