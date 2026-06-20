"""OpenAPI 3.1 спецификация основных API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _pydantic_schemas() -> dict[str, Any]:
    from services import schemas as s

    models: list[type[BaseModel]] = [
        s.Device,
        s.DeviceCreate,
        s.Inventory,
        s.LoginRequest,
        s.UserPublic,
        s.AuthUserResponse,
        s.UserCreate,
        s.UserUpdate,
        s.RbacMatrixResponse,
        s.LdapConfigPublic,
    ]
    merged: dict[str, Any] = {
        "Error": {
            "type": "object",
            "properties": {"detail": {"type": "string"}},
        },
    }
    for model in models:
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            continue
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        defs = schema.pop("$defs", None) or {}
        merged[model.__name__] = schema
        merged.update(defs)
    merged["CustomRole"] = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "slug": {"type": "string"},
            "label": {"type": "string"},
            "description": {"type": "string"},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "is_system": {"type": "boolean"},
        },
    }
    merged["CustomRoleCreate"] = {
        "type": "object",
        "required": ["slug", "label", "permissions"],
        "properties": {
            "slug": {"type": "string"},
            "label": {"type": "string"},
            "description": {"type": "string"},
            "permissions": {"type": "array", "items": {"type": "string"}},
        },
    }
    return merged


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
            "schemas": _pydantic_schemas(),
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
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/LoginRequest"},
                        }
                    }
                },
            },
        },
        "/api/auth/me": {
            "get": {
                "tags": ["auth"],
                "summary": "Current user profile",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AuthUserResponse"},
                            }
                        }
                    }
                },
            }
        },
        "/api/auth/rbac": {
            "get": {
                "tags": ["auth"],
                "summary": "RBAC matrix (builtin + custom roles)",
            },
        },
        "/api/auth/users": {
            "get": {"tags": ["admin"], "summary": "List users"},
            "post": {
                "tags": ["admin"],
                "summary": "Create local user",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UserCreate"},
                        }
                    }
                },
            },
        },
        "/api/auth/users/{id}": {
            "put": {
                "tags": ["admin"],
                "summary": "Update user (role, scope, custom_role)",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UserUpdate"},
                        }
                    }
                },
            },
            "delete": {"tags": ["admin"], "summary": "Delete user"},
        },
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
        "/api/auth/api-keys/{id}/rotate": {
            "post": {"tags": ["admin"], "summary": "Rotate API key (new secret returned once)"},
        },
        "/api/auth/custom-roles": {
            "get": {"tags": ["admin"], "summary": "List custom RBAC roles"},
            "post": {
                "tags": ["admin"],
                "summary": "Create custom role",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CustomRoleCreate"},
                        }
                    }
                },
            },
        },
        "/api/auth/custom-roles/{id}": {
            "put": {"tags": ["admin"], "summary": "Update custom role"},
            "delete": {"tags": ["admin"], "summary": "Delete custom role"},
        },
        "/api/inventory/import/netbox": {
            "post": {"tags": ["inventory"], "summary": "Import devices from NetBox"},
        },
        "/api/inventory/import/librenms": {
            "post": {"tags": ["inventory"], "summary": "Import devices from LibreNMS"},
        },
        "/api/inventory/topology/netbox": {
            "get": {"tags": ["inventory"], "summary": "Network topology graph from NetBox cables"},
        },
        "/api/sites": {
            "get": {"tags": ["inventory"], "summary": "Site hierarchy"},
        },
        "/inventory": {
            "get": {
                "tags": ["inventory"],
                "summary": "Full inventory",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Inventory"},
                            }
                        }
                    }
                },
            },
            "put": {"tags": ["inventory"], "summary": "Replace inventory"},
        },
        "/inventory/devices": {
            "post": {
                "tags": ["inventory"],
                "summary": "Add device",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/DeviceCreate"},
                        }
                    }
                },
            },
        },
        "/inventory/devices/bulk": {
            "post": {"tags": ["inventory"], "summary": "Bulk update devices"},
        },
        "/scan": {"post": {"tags": ["scan"], "summary": "Start scan/discovery"}},
        "/scan/status": {"get": {"tags": ["scan"], "summary": "Scan job status"}},
        "/scan/latest": {"get": {"tags": ["scan"], "summary": "Latest scan results"}},
        "/api/scan/trends": {"get": {"tags": ["scan"], "summary": "Scan trends"}},
        "/api/compliance/summary": {
            "get": {"tags": ["compliance"], "summary": "Compliance dashboard data"},
        },
        "/api/compliance/by-site": {
            "get": {"tags": ["compliance"], "summary": "Compliance grouped by site"},
        },
        "/api/compliance/export": {
            "get": {"tags": ["compliance"], "summary": "Export CSV/PDF"},
        },
        "/api/oxidized/health": {
            "get": {"tags": ["oxidized"], "summary": "Oxidized engine health"},
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
            "get": {
                "tags": ["settings"],
                "summary": "LDAP settings",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/LdapConfigPublic"},
                            }
                        }
                    }
                },
            },
            "put": {"tags": ["settings"], "summary": "Update LDAP settings"},
        },
        "/api/settings/integrations": {
            "get": {"tags": ["settings"], "summary": "Integration settings (NetBox, SIEM, tickets)"},
            "put": {"tags": ["settings"], "summary": "Update integration settings"},
        },
        "/api/audit": {"get": {"tags": ["admin"], "summary": "Audit log"}},
        "/api/audit/export": {"get": {"tags": ["admin"], "summary": "Audit CSV export"}},
        "/api/provisioning/templates": {
            "get": {"tags": ["admin"], "summary": "List provision templates"},
            "post": {"tags": ["admin"], "summary": "Create provision template"},
        },
        "/api/provisioning/templates/generate": {
            "post": {"tags": ["admin"], "summary": "Generate provision templates from device configs"},
        },
        "/api/provisioning/templates/generate/run": {
            "post": {"tags": ["admin"], "summary": "Start async provision template generation"},
        },
        "/api/provisioning/templates/generate/runs/{run_id}": {
            "get": {"tags": ["admin"], "summary": "Provision template generation run status and log"},
        },
        "/api/provisioning/analysis": {
            "get": {"tags": ["admin"], "summary": "Analyze device config clusters and complex devices"},
        },
        "/api/provisioning/analysis/run": {
            "post": {"tags": ["admin"], "summary": "Start async provision cluster analysis"},
        },
        "/api/provisioning/analysis/runs/{run_id}": {
            "get": {"tags": ["admin"], "summary": "Provision cluster analysis run status and log"},
        },
        "/api/provisioning/templates/{id}": {
            "get": {"tags": ["admin"], "summary": "Get provision template"},
            "put": {"tags": ["admin"], "summary": "Update provision template"},
            "delete": {"tags": ["admin"], "summary": "Delete provision template"},
        },
        "/api/provisioning/preview": {
            "post": {"tags": ["admin"], "summary": "Render template preview for device"},
        },
        "/api/provisioning/run": {
            "post": {"tags": ["admin"], "summary": "Apply template (or dry-run)"},
        },
        "/api/provisioning/runs": {
            "get": {"tags": ["admin"], "summary": "Provision run history"},
        },
        "/api/provisioning/bulk": {
            "get": {"tags": ["admin"], "summary": "List bulk provision runs or preview targets"},
        },
        "/api/provisioning/bulk/run": {
            "post": {"tags": ["admin"], "summary": "Start bulk provision via task queue"},
        },
        "/api/provisioning/bulk/{id}": {
            "get": {"tags": ["admin"], "summary": "Get bulk provision run status"},
        },
    }
