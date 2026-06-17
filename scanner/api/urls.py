from django.urls import path

from api import views

urlpatterns = [
    path("ui", views.ui_page, name="ui"),
    path("api/ui/config", views.ui_config, name="ui-config"),
    path("api/auth/login", views.login_view, name="auth-login"),
    path("api/auth/logout", views.logout_view, name="auth-logout"),
    path("api/auth/me", views.auth_me, name="auth-me"),
    path("api/auth/users", views.auth_users_dispatch, name="auth-users"),
    path("api/auth/users/<int:user_id>", views.auth_user_detail, name="auth-user-detail"),
    path("api/settings/oxidized", views.oxidized_settings_dispatch, name="settings-oxidized"),
    path("api/settings/ldap", views.ldap_settings_dispatch, name="settings-ldap"),
    path("api/settings/ldap/test", views.ldap_settings_test_view, name="settings-ldap-test"),
    path("api/oxidized/health", views.oxidized_health, name="oxidized-health"),
    path("api/oxidized/logs", views.oxidized_logs, name="oxidized-logs"),
    path("api/oxidized/source", views.oxidized_source, name="oxidized-source"),
    path("api/oxidized/models", views.oxidized_models, name="oxidized-models"),
    path("oxidized-proxy", views.oxidized_proxy, name="oxidized-proxy-root"),
    path("oxidized-proxy/<path:path>", views.oxidized_proxy, name="oxidized-proxy"),
    path("api/oxidized/nodes", views.oxidized_nodes, name="oxidized-nodes"),
    path("api/oxidized/nodes/<str:name>", views.oxidized_node_show, name="oxidized-node-show"),
    path(
        "api/oxidized/nodes/<str:name>/versions",
        views.oxidized_node_versions,
        name="oxidized-node-versions",
    ),
    path(
        "api/oxidized/nodes/<str:name>/versions/<str:oid>",
        views.oxidized_node_version_view,
        name="oxidized-node-version-view",
    ),
    path(
        "api/oxidized/nodes/<str:name>/diff",
        views.oxidized_node_diff,
        name="oxidized-node-diff",
    ),
    path(
        "api/oxidized/nodes/<str:name>/fetch",
        views.oxidized_node_fetch,
        name="oxidized-node-fetch",
    ),
    path("health", views.health, name="health"),
    path("inventory", views.inventory_dispatch, name="inventory"),
    path("inventory/devices", views.inventory_devices_dispatch, name="inventory-devices"),
    path("inventory/devices/<str:name>", views.delete_device_view, name="inventory-device-delete"),
    path("inventory/credentials", views.create_credential_profile_view, name="inventory-credentials-create"),
    path(
        "inventory/credentials/<str:name>",
        views.credential_profile_detail_view,
        name="inventory-credentials",
    ),
    path(
        "inventory/import-network",
        views.import_network_inventory_view,
        name="inventory-import-network",
    ),
    path(
        "inventory/cleanup-discovered",
        views.cleanup_discovered_devices_view,
        name="inventory-cleanup-discovered",
    ),
    path("scan", views.scan_inventory_view, name="scan"),
    path("scan/status", views.scan_status_view, name="scan-status"),
    path("scan/latest", views.get_latest_scan_view, name="scan-latest"),
    path("oxidized/sync", views.sync_oxidized_view, name="oxidized-sync"),
]
