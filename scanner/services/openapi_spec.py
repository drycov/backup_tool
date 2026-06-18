"""OpenAPI 3.1 спецификация основных API endpoints."""

from __future__ import annotations

from django.conf import settings


def build_openapi_spec() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Backup Tools API",
            "version": "3.0.0",
            "description": "REST API для инвентаря, сканирования, Oxidized, compliance и настроек.",
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                },
                "apiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API key (bk_…) для автоматизации",
                },
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {"detail": {"type": "string"}},
                },
                "Device": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "ip": {"type": "string"},
                        "model": {"type": "string"},
                        "group": {"type": "string"},
                        "site": {"type": "string"},
                        "role": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "enabled": {"type": "boolean"},
                        "critical": {"type": "boolean"},
                    },
                },
            },
        },
        "security": [{"bearerAuth": []}, {"apiKeyAuth": []}],
        "paths": _paths(),
        "tags": [
            {"name": "auth"},
            {"name": "inventory"},
            {"name": "scan"},
            {"name": "compliance"},
            {"name": "oxidized"},
            {"name": "settings"},
            {"name": "admin"},
            {"name": "observability"},
        ],
    }


def _paths() -> dict:
    return {
        "/health": {
            "get": {"tags": ["observability"], "summary": "Liveness", "security": []},
        },
        "/health/ready": {
            "get": {"tags": ["observability"], "summary": "Readiness (DB + Oxidized)", "security": []},
        },
        "/metrics": {
            "get": {"tags": ["observability"], "summary": "Prometheus metrics", "security": []},
        },
        "/api/openapi.json": {
            "get": {"tags": ["observability"], "summary": "This specification", "security": []},
        },
        "/api/auth/login": {
            "post": {
                "tags": ["auth"],
                "summary": "Login (JWT cookie + body)",
                "security": [],
            },
        },
        "/api/auth/me": {"get": {"tags": ["auth"], "summary": "Current user profile"}},
        "/api/auth/users": {"get": {"tags": ["admin"], "summary": "List users"}},
        "/api/auth/api-keys": {
            "get": {"tags": ["admin"], "summary": "List API keys"},
            "post": {"tags": ["admin"], "summary": "Create API key (raw key returned once)"},
        },
        "/api/auth/api-keys/{id}": {
            "delete": {"tags": ["admin"], "summary": "Delete API key"},
        },
        "/api/auth/api-keys/{id}/revoke": {
            "post": {"tags": ["admin"], "summary": "Revoke API key"},
        },
        "/inventory": {
            "get": {"tags": ["inventory"], "summary": "Full inventory"},
            "put": {"tags": ["inventory"], "summary": "Replace inventory"},
        },
        "/inventory/devices": {
            "post": {"tags": ["inventory"], "summary": "Add device"},
        },
        "/inventory/devices/bulk": {
            "post": {"tags": ["inventory"], "summary": "Bulk update devices"},
        },
        "/scan": {"post": {"tags": ["scan"], "summary": "Start scan/discovery"}},
        "/scan/status": {"get": {"tags": ["scan"], "summary": "Scan job status"}},
        "/api/compliance/summary": {
            "get": {"tags": ["compliance"], "summary": "Compliance dashboard data"},
        },
        "/api/compliance/by-site": {
            "get": {"tags": ["compliance"], "summary": "Compliance grouped by site"},
        },
        "/api/compliance/export": {
            "get": {"tags": ["compliance"], "summary": "Export CSV/PDF"},
        },
        "/api/oxidized/nodes": {"get": {"tags": ["oxidized"], "summary": "List nodes"}},
        "/api/oxidized/nodes/{name}/fetch": {
            "post": {"tags": ["oxidized"], "summary": "Trigger backup fetch"},
        },
        "/api/settings/scan": {
            "get": {"tags": ["settings"], "summary": "Scan settings"},
            "put": {"tags": ["settings"], "summary": "Update scan settings"},
        },
        "/api/settings/backup": {
            "get": {"tags": ["settings"], "summary": "Backup/notify settings"},
            "put": {"tags": ["settings"], "summary": "Update backup settings"},
        },
        "/api/settings/ldap": {
            "get": {"tags": ["settings"], "summary": "LDAP settings"},
            "put": {"tags": ["settings"], "summary": "Update LDAP settings"},
        },
        "/api/audit": {"get": {"tags": ["admin"], "summary": "Audit log"}},
        "/api/audit/export": {"get": {"tags": ["admin"], "summary": "Audit CSV export"}},
    }
