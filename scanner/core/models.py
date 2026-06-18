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
    model = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "credential_profiles"


class Network(models.Model):
    network = models.CharField(max_length=64, db_index=True)
    group_name = models.CharField(max_length=64, default="default", db_index=True)
    environment_name = models.CharField(max_length=128, null=True, blank=True)
    gateway = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "networks"


class Site(models.Model):
    """Иерархия площадок (slug → parent). Device.site хранит slug."""

    slug = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=256, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sites"
        ordering = ["slug"]


class Device(models.Model):
    name = models.CharField(max_length=128, unique=True, db_index=True)
    ip = models.CharField(max_length=64)
    model = models.CharField(max_length=64, default="routeros")
    group = models.CharField(max_length=64, default="default")
    enabled = models.BooleanField(default=True)
    ports = LegacyJSONField(default=list)
    site = models.CharField(max_length=128, blank=True, default="", db_index=True)
    role = models.CharField(max_length=128, blank=True, default="", db_index=True)
    critical = models.BooleanField(default=False, db_index=True)
    maintenance = models.BooleanField(default=False, db_index=True)
    tags = LegacyJSONField(default=list, blank=True)

    class Meta:
        db_table = "devices"


class GroupPolicy(models.Model):
    """Политики бэкапа per-group (hex, us, …)."""

    group_name = models.CharField(max_length=64, unique=True, db_index=True)
    backup_interval_sec = models.PositiveIntegerField(default=0)
    model = models.CharField(max_length=64, blank=True, default="")
    mk_binary_enabled = models.BooleanField(null=True, blank=True)
    mk_export_enabled = models.BooleanField(null=True, blank=True)
    notify_telegram = models.BooleanField(null=True, blank=True)
    notify_email = models.BooleanField(null=True, blank=True)
    maintenance_override = models.BooleanField(null=True, blank=True)
    compliance_sla_hours = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "group_policies"


class User(models.Model):
    username = models.CharField(max_length=64, unique=True, db_index=True)
    password_hash = models.CharField(max_length=256)
    role = models.CharField(max_length=32, default="viewer")
    is_active = models.BooleanField(default=True)
    auth_source = models.CharField(max_length=16, default="local")
    role_locked = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    totp_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    totp_recovery_hashes = LegacyJSONField(default=list, blank=True)
    allowed_groups = LegacyJSONField(default=list, blank=True)
    allowed_sites = LegacyJSONField(default=list, blank=True)
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
    scope_mappings = LegacyJSONField(default=list, blank=True)
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
    mk_backup_git_push = models.BooleanField(default=True)
    degrade_check_interval_sec = models.PositiveIntegerField(default=3600)

    compliance_report_telegram = models.BooleanField(default=False)
    compliance_report_email = models.BooleanField(default=False)
    compliance_report_hour_utc = models.PositiveSmallIntegerField(default=7)
    compliance_report_last_sent_at = models.DateTimeField(null=True, blank=True)

    degrade_webhook_enabled = models.BooleanField(default=False)
    degrade_webhook_url = models.CharField(max_length=512, blank=True, default="")

    slack_webhook_url = models.CharField(max_length=512, blank=True, default="")
    teams_webhook_url = models.CharField(max_length=512, blank=True, default="")
    error_notify_slack = models.BooleanField(default=False)
    error_notify_teams = models.BooleanField(default=False)
    report_send_slack = models.BooleanField(default=False)
    report_send_teams = models.BooleanField(default=False)
    degrade_notify_slack = models.BooleanField(default=False)
    degrade_notify_teams = models.BooleanField(default=False)
    compliance_report_slack = models.BooleanField(default=False)
    compliance_report_teams = models.BooleanField(default=False)

    maintenance_window_enabled = models.BooleanField(default=True)
    maintenance_start_hour_utc = models.PositiveSmallIntegerField(default=22)
    maintenance_end_hour_utc = models.PositiveSmallIntegerField(default=6)
    maintenance_days = LegacyJSONField(default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "backup_config"


class GitConfig(models.Model):
    """Singleton: Git push и интеграции (pk=1)."""

    git_remote_url = models.CharField(max_length=512, blank=True, default="")
    gitea_token = models.CharField(max_length=256, blank=True, default="")
    gitea_http_user = models.CharField(max_length=64, default="oauth2")
    git_commit_user = models.CharField(max_length=128, default="Oxidized")
    git_commit_email = models.CharField(max_length=256, default="oxidized@localhost")
    git_branch = models.CharField(max_length=64, default="main")
    oxidized_source_token = models.CharField(max_length=256, blank=True, default="")
    oxidized_public_url = models.CharField(max_length=512, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "git_config"


class IntegrationConfig(models.Model):
    """Singleton: ServiceNow, Jira, audit SIEM webhook (pk=1)."""

    snow_enabled = models.BooleanField(default=False)
    snow_instance_url = models.CharField(max_length=512, blank=True, default="")
    snow_username = models.CharField(max_length=128, blank=True, default="")
    snow_password = models.CharField(max_length=256, blank=True, default="")
    snow_assignment_group = models.CharField(max_length=128, blank=True, default="")

    jira_enabled = models.BooleanField(default=False)
    jira_url = models.CharField(max_length=512, blank=True, default="")
    jira_username = models.CharField(max_length=128, blank=True, default="")
    jira_api_token = models.CharField(max_length=256, blank=True, default="")
    jira_project_key = models.CharField(max_length=32, blank=True, default="")
    jira_issue_type = models.CharField(max_length=64, default="Task")

    ticket_on_backup_failed = models.BooleanField(default=True)
    ticket_on_device_offline = models.BooleanField(default=True)
    ticket_cooldown_hours = models.PositiveIntegerField(default=24)

    audit_webhook_enabled = models.BooleanField(default=False)
    audit_webhook_url = models.CharField(max_length=512, blank=True, default="")
    audit_webhook_secret = models.CharField(max_length=256, blank=True, default="")
    audit_webhook_action_prefix = models.CharField(max_length=64, blank=True, default="")

    netbox_url = models.CharField(max_length=512, blank=True, default="")
    netbox_token = models.CharField(max_length=256, blank=True, default="")
    netbox_default_group = models.CharField(max_length=64, default="default")
    librenms_url = models.CharField(max_length=512, blank=True, default="")
    librenms_token = models.CharField(max_length=256, blank=True, default="")
    librenms_default_group = models.CharField(max_length=64, default="default")
    inventory_sync_enabled = models.BooleanField(default=False)
    inventory_sync_source = models.CharField(max_length=16, default="netbox")
    inventory_sync_interval_hours = models.PositiveIntegerField(default=24)
    inventory_sync_last_run_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integration_config"


class ScanConfig(models.Model):
    """Singleton: scan/discovery и seed credentials (pk=1)."""

    scan_concurrency = models.PositiveIntegerField(default=50)
    discover_max_hosts = models.PositiveIntegerField(default=4096)
    discover_ping_workers = models.PositiveIntegerField(default=100)
    schedule_enabled = models.BooleanField(default=False)
    schedule_interval_hours = models.PositiveIntegerField(default=24)
    schedule_discover = models.BooleanField(default=True)
    schedule_last_run_at = models.DateTimeField(null=True, blank=True)
    ovn_user = models.CharField(max_length=128, default="satcoadm")
    ovn_pass = models.CharField(max_length=256, blank=True, default="")
    us_user = models.CharField(max_length=128, default="satcoadm")
    us_pass = models.CharField(max_length=256, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scan_config"


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


class BackgroundTask(models.Model):
    """Персистентная очередь фоновых задач (degrade, compliance, scheduled scan)."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    TASK_DEGRADE_CHECK = "degrade.check"
    TASK_COMPLIANCE_REPORT = "compliance.report"
    TASK_SCHEDULED_SCAN = "scan.scheduled"
    TASK_AUDIT_PURGE = "audit.purge"
    TASK_AUDIT_WEBHOOK = "audit.webhook"
    TASK_CONFIG_AUDIT = "config.audit"
    TASK_INVENTORY_SYNC = "inventory.sync"

    task_type = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, default=STATUS_PENDING, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    scheduled_at = models.DateTimeField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "background_tasks"
        ordering = ["scheduled_at", "id"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["task_type", "status"]),
        ]


class ApiKey(models.Model):
    """API-ключи для автоматизации (CI, Ansible) без cookie JWT."""

    name = models.CharField(max_length=64, unique=True, db_index=True)
    key_prefix = models.CharField(max_length=16)
    key_hash = models.CharField(max_length=128)
    role = models.CharField(max_length=32, default="viewer")
    permissions = LegacyJSONField(default=list, blank=True)
    allowed_groups = LegacyJSONField(default=list, blank=True)
    allowed_sites = LegacyJSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_keys"
        ordering = ["name"]


class AlertState(models.Model):
    alert_key = models.CharField(max_length=128, unique=True, db_index=True)
    last_notified_at = models.DateTimeField()
    device_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "alert_states"


class SystemConfig(models.Model):
    """Singleton: системные настройки (ранее только .env), pk=1."""

    oxidized_engine = models.CharField(max_length=16, default="python")
    oxidized_external_url = models.CharField(
        max_length=512, blank=True, default="http://oxidized:8888"
    )
    zabbix_auth_key = models.CharField(max_length=256, blank=True, default="")
    zabbix_monitoring_enabled = models.BooleanField(default=True)
    audit_retention_days = models.PositiveIntegerField(default=365)
    metrics_enabled = models.BooleanField(default=True)
    backup_data_dir = models.CharField(max_length=512, default="/data/backups")
    access_token_expire_minutes = models.PositiveIntegerField(default=480)
    behind_https_proxy = models.BooleanField(default=False)
    task_worker_enabled = models.BooleanField(default=True)
    task_worker_poll_sec = models.PositiveIntegerField(default=30)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "system_config"


class ConfigAuditRun(models.Model):
    """Запуск анализа конфигураций на уязвимости и misconfiguration."""

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    status = models.CharField(max_length=16, default=STATUS_COMPLETED, db_index=True)
    triggered_by = models.CharField(max_length=64, default="system")
    devices_total = models.PositiveIntegerField(default=0)
    devices_scanned = models.PositiveIntegerField(default=0)
    devices_skipped = models.PositiveIntegerField(default=0)
    findings_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "config_audit_runs"
        ordering = ["-started_at"]


class ConfigFinding(models.Model):
    """Нарушение правила безопасности в конфигурации устройства."""

    run = models.ForeignKey(
        ConfigAuditRun,
        on_delete=models.CASCADE,
        related_name="findings",
    )
    device_name = models.CharField(max_length=128, db_index=True)
    device_ip = models.CharField(max_length=64, blank=True, default="")
    device_model = models.CharField(max_length=64, blank=True, default="")
    device_group = models.CharField(max_length=64, blank=True, default="")
    device_site = models.CharField(max_length=128, blank=True, default="")
    rule_id = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=32, default="hardening", db_index=True)
    severity = models.CharField(max_length=16, db_index=True)
    title = models.CharField(max_length=256)
    evidence = models.TextField(blank=True, default="")
    line_number = models.PositiveIntegerField(null=True, blank=True)
    remediation = models.TextField(blank=True, default="")
    acknowledged = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "config_findings"
        ordering = ["-severity", "device_name"]
        indexes = [
            models.Index(fields=["run", "severity"]),
            models.Index(fields=["device_name", "rule_id"]),
        ]
