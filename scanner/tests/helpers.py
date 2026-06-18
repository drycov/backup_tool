"""Shared test helpers."""

from __future__ import annotations

import json
import os

from django.test import Client


def login(client: Client, username: str = "admin", password: str | None = None) -> None:
    if password is not None:
        attempts = [password]
    elif username == "admin":
        attempts = [
            os.environ.get("ADMIN_PASSWORD"),
            "changeme",
            "pytest-admin-pass",
        ]
        attempts = [p for p in attempts if p]
    else:
        attempts = [password or "changeme"]

    res = None
    for pwd in attempts:
        res = client.post(
            "/api/auth/login",
            data=json.dumps({"username": username, "password": pwd}),
            content_type="application/json",
        )
        if res.status_code == 200:
            return
    assert res is not None and res.status_code == 200, res.content if res else "login failed"
