"""Stage 3 foundation: API keys, LDAP scope, tags, OpenAPI, compliance by site."""

from __future__ import annotations

import json

import pytest
from django.test import Client

from core.models import ApiKey, Device as DeviceModel
from services.api_keys import create_api_key
from services.ldap_scope import resolve_scope_from_ldap_groups


@pytest.fixture
def authed(client, db):
    from core.models import User
    from services.auth import hash_password, seed_default_admin
    import os
    from tests.helpers import login

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
def test_ldap_scope_mapping():
    mappings = [
        {
            "ldap_group": "CN=NetOps,OU=Groups,DC=corp",
            "allowed_groups": ["hex", "us"],
            "allowed_sites": ["msk"],
        }
    ]
    groups, sites = resolve_scope_from_ldap_groups(
        ["CN=NetOps,OU=Groups,DC=corp,DC=local"], mappings
    )
    assert "hex" in groups
    assert "msk" in sites


@pytest.mark.django_db
def test_api_key_auth(client, db, authed):
    _, raw = create_api_key(name="ci-bot", role="viewer", created_by="admin")
    response = client.get("/api/compliance/summary", HTTP_X_API_KEY=raw)
    assert response.status_code == 200
    assert "compliance_pct" in response.json()


@pytest.mark.django_db
def test_api_key_crud(authed):
    response = authed.post(
        "/api/auth/api-keys",
        data=json.dumps({"name": "ansible", "role": "operator"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["key"].startswith("bk_")
    assert ApiKey.objects.filter(name="ansible").exists()


@pytest.mark.django_db
def test_device_tags_roundtrip(db):
    DeviceModel.objects.create(
        name="sw1",
        ip="10.0.0.1",
        tags=["core", "dc1"],
    )
    from services.inventory import load_inventory

    inv = load_inventory()
    dev = next(d for d in inv.devices if d.name == "sw1")
    assert dev.tags == ["core", "dc1"]


@pytest.mark.django_db
def test_openapi_endpoint(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.")
    assert "/api/compliance/by-site" in spec["paths"]


@pytest.mark.django_db
def test_compliance_by_site(authed):
    response = authed.get("/api/compliance/by-site")
    assert response.status_code == 200
    data = response.json()
    assert "sites" in data
