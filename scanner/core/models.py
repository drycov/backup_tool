from django.db import models


class LegacyJSONField(models.JSONField):
    """SQLAlchemy JSON columns may return already-deserialized Python objects."""

    def from_db_value(self, value, expression, connection):
        if isinstance(value, (list, dict, int, float, bool)) or value is None:
            return value
        return super().from_db_value(value, expression, connection)


class CredentialProfile(models.Model):
    name = models.CharField(max_length=64, unique=True, db_index=True)
    group_name = models.CharField(max_length=64, db_index=True)
    username = models.CharField(max_length=128, default="admin")
    password = models.CharField(max_length=256, default="changeme")

    class Meta:
        db_table = "credential_profiles"


class Network(models.Model):
    network = models.CharField(max_length=64, db_index=True)
    group_name = models.CharField(max_length=64, default="default", db_index=True)
    environment_name = models.CharField(max_length=128, null=True, blank=True)
    gateway = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "networks"


class Device(models.Model):
    name = models.CharField(max_length=128, unique=True, db_index=True)
    ip = models.CharField(max_length=64)
    model = models.CharField(max_length=64, default="routeros")
    group = models.CharField(max_length=64, default="default")
    enabled = models.BooleanField(default=True)
    ports = LegacyJSONField(default=list)

    class Meta:
        db_table = "devices"


class User(models.Model):
    username = models.CharField(max_length=64, unique=True, db_index=True)
    password_hash = models.CharField(max_length=256)
    role = models.CharField(max_length=32, default="viewer")
    is_active = models.BooleanField(default=True)
    auth_source = models.CharField(max_length=16, default="local")
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users"


class LdapConfig(models.Model):
    """Singleton: настройки LDAP / Active Directory (pk=1)."""

    DIRECTORY_LDAP = "ldap"
    DIRECTORY_AD = "ad"

    enabled = models.BooleanField(default=False)
    directory_type = models.CharField(max_length=16, default=DIRECTORY_LDAP)
    server = models.CharField(max_length=512, blank=True, default="")
    use_ssl = models.BooleanField(default=False)
    start_tls = models.BooleanField(default=True)
    bind_dn = models.CharField(max_length=512, blank=True, default="")
    bind_password = models.CharField(max_length=512, blank=True, default="")
    user_base = models.CharField(max_length=512, blank=True, default="")
    user_filter = models.CharField(max_length=256, default="(uid={username})")
    user_dn_template = models.CharField(max_length=512, blank=True, default="")
    user_upn_suffix = models.CharField(max_length=256, blank=True, default="")
    admin_groups = models.TextField(blank=True, default="")
    operator_groups = models.TextField(blank=True, default="")
    default_role = models.CharField(max_length=32, default="viewer")
    fallback_local = models.BooleanField(default=True)
    connect_timeout = models.PositiveIntegerField(default=10)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ldap_config"


class BackupConfig(models.Model):
    """Singleton: настройки MikroTik backup и уведомлений (pk=1)."""

    binary_enabled = models.BooleanField(default=True)
    export_enabled = models.BooleanField(default=True)
    hide_sensitive = models.BooleanField(default=False)
    encrypt_password = models.CharField(max_length=256, blank=True, default="")
    purge_enabled = models.BooleanField(default=True)
    purge_keep = models.PositiveIntegerField(default=10)
    bin_dir = models.CharField(max_length=512, default="/var/lib/oxidized/bin")
    rsc_dir = models.CharField(max_length=512, default="/var/lib/oxidized/rsc")
    backup_timeout = models.PositiveIntegerField(default=300)

    error_notify_telegram = models.BooleanField(default=False)
    error_notify_email = models.BooleanField(default=False)
    report_send_telegram = models.BooleanField(default=False)
    report_send_email = models.BooleanField(default=False)

    telegram_token = models.CharField(max_length=256, blank=True, default="")
    telegram_chat_notify = models.CharField(max_length=64, blank=True, default="")
    telegram_chat_report = models.CharField(max_length=64, blank=True, default="")

    smtp_server = models.CharField(max_length=256, blank=True, default="")
    smtp_port = models.PositiveIntegerField(default=465)
    smtp_user = models.CharField(max_length=256, blank=True, default="")
    smtp_password = models.CharField(max_length=256, blank=True, default="")
    smtp_ssl = models.BooleanField(default=True)
    smtp_from = models.CharField(max_length=256, blank=True, default="")
    smtp_to_notify = models.CharField(max_length=256, blank=True, default="")
    smtp_to_report = models.CharField(max_length=256, blank=True, default="")

    degrade_notify_telegram = models.BooleanField(default=False)
    degrade_notify_email = models.BooleanField(default=False)
    stale_days_threshold = models.PositiveIntegerField(default=30)
    alert_cooldown_hours = models.PositiveIntegerField(default=24)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "backup_config"


class ScanRun(models.Model):
    job_id = models.CharField(max_length=32, blank=True, default="")
    discover = models.BooleanField(default=False)
    status = models.CharField(max_length=16, default="completed")
    total = models.PositiveIntegerField(default=0)
    online = models.PositiveIntegerField(default=0)
    offline = models.PositiveIntegerField(default=0)
    partial = models.PositiveIntegerField(default=0)
    scanned_at = models.DateTimeField(db_index=True)
    error = models.TextField(blank=True, default="")
    results_json = LegacyJSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scan_runs"
        ordering = ["-scanned_at"]


class AuditEvent(models.Model):
    username = models.CharField(max_length=64, db_index=True)
    action = models.CharField(max_length=64, db_index=True)
    target = models.CharField(max_length=256, blank=True, default="")
    detail = models.TextField(blank=True, default="")
    ip_address = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_events"
        ordering = ["-created_at"]


class AlertState(models.Model):
    alert_key = models.CharField(max_length=128, unique=True, db_index=True)
    last_notified_at = models.DateTimeField()
    device_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "alert_states"
