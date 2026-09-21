from services.env_settings import get_env_export, get_env_public


def test_env_public_masks_secrets(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("SCANNER_PORT", "8123")

    payload = get_env_public()
    items = {item["name"]: item for item in payload["items"]}

    assert items["JWT_SECRET"]["secret"] is True
    assert items["JWT_SECRET"]["value"] != "super-secret"
    assert items["JWT_SECRET"]["set"] is True
    assert items["SCANNER_PORT"]["value"] == "8123"


def test_env_export_excludes_secret_values(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("SCANNER_PORT", "8123")

    export = get_env_export()

    assert "JWT_SECRET=" in export
    assert "super-secret" not in export
    assert "SCANNER_PORT=8123" in export
