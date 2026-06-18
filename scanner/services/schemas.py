from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class Device(BaseModel):
    name: str
    ip: str
    model: str = "routeros"
    group: str = "default"
    enabled: bool = True
    ports: list[int] = Field(default_factory=lambda: [44333])
    site: str = ""
    role: str = ""
    critical: bool = False
    maintenance: bool = False
    tags: list[str] = Field(default_factory=list)


class DeviceCreate(BaseModel):
    name: str
    ip: str
    model: str = "routeros"
    group: str = "default"
    enabled: bool = True
    ports: list[int] = Field(default_factory=lambda: [44333])
    site: str = ""
    role: str = ""
    critical: bool = False
    maintenance: bool = False
    tags: list[str] = Field(default_factory=list)


class CredentialProfile(BaseModel):
    name: str
    group_name: str
    username: str
    password: str
    model: str = ""


class CredentialProfileUpdate(BaseModel):
    username: str
    password: str
    group_name: Optional[str] = None
    model: Optional[str] = None


class CredentialProfileCreate(BaseModel):
    name: str
    group_name: str
    username: str
    password: str
    model: Optional[str] = "routeros"


class NetworkEntry(BaseModel):
    network: str
    group_name: str = "default"
    environment_name: Optional[str] = None
    gateway: Optional[str] = None


class Inventory(BaseModel):
    credential_profiles: list[CredentialProfile] = Field(default_factory=list)
    networks: list[NetworkEntry] = Field(default_factory=list)
    devices: list[Device] = Field(default_factory=list)


class PortResult(BaseModel):
    port: int
    open: bool
    latency_ms: Optional[float] = None


class ScanResult(BaseModel):
    name: str
    ip: str
    status: ScanStatus
    ping_ok: bool
    ports: list[PortResult] = Field(default_factory=list)
    scanned_at: datetime
    model: str = "routeros"
    group: str = "default"
    enabled: bool = True


class ScanSummary(BaseModel):
    total: int
    online: int
    offline: int
    partial: int
    scanned_at: datetime
    results: list[ScanResult] = Field(default_factory=list)


class ScanStartResponse(BaseModel):
    job_id: str
    status: str = "running"
    discover: bool = False


class ScanJobStatus(BaseModel):
    job_id: Optional[str] = None
    status: str = "idle"
    phase: str = "idle"
    message: str = ""
    discover: bool = False
    progress_current: int = 0
    progress_total: int = 0
    progress_pct: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    summary: Optional[ScanSummary] = None
    error: Optional[str] = None
    logs: list["ScanLogEntry"] = Field(default_factory=list)


class ScanLogEntry(BaseModel):
    ts: datetime
    level: str = "info"
    message: str


class HealthResponse(BaseModel):
    status: str
    inventory_devices: int
    networks: int
    last_scan: Optional[datetime] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    auth_source: str = "local"
    role_locked: bool = False


class AuthUserResponse(BaseModel):
    id: int
    username: str
    role: str
    permissions: list[str]
    auth_source: str = "local"
    role_locked: bool = False


class RbacMatrixResponse(BaseModel):
    roles: list[dict]
    permissions: list[dict]


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    role_locked: Optional[bool] = None
    allowed_groups: Optional[list[str]] = None
    allowed_sites: Optional[list[str]] = None


class LdapConfigPublic(BaseModel):
    enabled: bool = False
    directory_type: str = "ldap"
    server: str = ""
    use_ssl: bool = False
    start_tls: bool = True
    bind_dn: str = ""
    bind_password_set: bool = False
    user_base: str = ""
    user_filter: str = "(uid={username})"
    user_dn_template: str = ""
    user_upn_suffix: str = ""
    admin_groups: str = ""
    operator_groups: str = ""
    default_role: str = "viewer"
    fallback_local: bool = True
    connect_timeout: int = 10
    configured: bool = False
    scope_mappings: list[dict] = Field(default_factory=list)


class LdapConfigUpdate(BaseModel):
    enabled: bool = False
    directory_type: str = "ldap"
    server: str = ""
    use_ssl: bool = False
    start_tls: bool = True
    bind_dn: str = ""
    bind_password: Optional[str] = None
    user_base: str = ""
    user_filter: str = "(uid={username})"
    user_dn_template: str = ""
    user_upn_suffix: str = ""
    admin_groups: str = ""
    operator_groups: str = ""
    default_role: str = "viewer"
    fallback_local: bool = True
    connect_timeout: int = 10
    scope_mappings: list[dict] = Field(default_factory=list)


class LdapTestRequest(BaseModel):
    mode: str = "bind"
    username: Optional[str] = None
    password: Optional[str] = None


class OxidizedSettingsUpdate(BaseModel):
    interval: int = 3600
    threads: int = 10
    timeout: int = 20
    retries: int = 3
    default_model: str = "routeros"
    ssh_port: int = 44333
    resolve_dns: bool = True
    group_models: dict[str, str] = Field(default_factory=dict)


class BackupSettingsUpdate(BaseModel):
    binary_enabled: bool = True
    export_enabled: bool = True
    hide_sensitive: bool = False
    encrypt_password: Optional[str] = None
    purge_enabled: bool = True
    purge_keep: int = 10
    bin_dir: str = "/var/lib/oxidized/bin"
    rsc_dir: str = "/var/lib/oxidized/rsc"
    backup_timeout: int = 300
    error_notify_telegram: bool = False
    error_notify_email: bool = False
    report_send_telegram: bool = False
    report_send_email: bool = False
    telegram_token: Optional[str] = None
    telegram_chat_notify: str = ""
    telegram_chat_report: str = ""
    smtp_server: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: Optional[str] = None
    smtp_ssl: bool = True
    smtp_from: str = ""
    smtp_to_notify: str = ""
    smtp_to_report: str = ""
    degrade_notify_telegram: bool = False
    degrade_notify_email: bool = False
    stale_days_threshold: int = 30
    alert_cooldown_hours: int = 24
    mk_backup_git_push: bool = True
    degrade_check_interval_sec: int = 3600
    compliance_report_telegram: bool = False
    compliance_report_email: bool = False
    compliance_report_hour_utc: int = 7
    degrade_webhook_enabled: bool = False
    degrade_webhook_url: str = ""
    slack_webhook_url: str = ""
    teams_webhook_url: str = ""
    error_notify_slack: bool = False
    error_notify_teams: bool = False
    report_send_slack: bool = False
    report_send_teams: bool = False
    degrade_notify_slack: bool = False
    degrade_notify_teams: bool = False
    compliance_report_slack: bool = False
    compliance_report_teams: bool = False
    maintenance_window_enabled: bool = True
    maintenance_start_hour_utc: int = 22
    maintenance_end_hour_utc: int = 6
    maintenance_days: list[int] = Field(default_factory=lambda: list(range(7)))


class GroupPolicyUpdate(BaseModel):
    group_name: str
    backup_interval_sec: int = 0
    model: str = ""
    mk_binary_enabled: Optional[bool] = None
    mk_export_enabled: Optional[bool] = None
    notify_telegram: Optional[bool] = None
    notify_email: Optional[bool] = None
    maintenance_override: Optional[bool] = None
    compliance_sla_hours: Optional[int] = None


class GitSettingsUpdate(BaseModel):
    git_remote_url: str = ""
    gitea_token: Optional[str] = None
    gitea_http_user: str = "oauth2"
    git_commit_user: str = "Oxidized"
    git_commit_email: str = "oxidized@localhost"
    git_branch: str = "main"
    oxidized_source_token: Optional[str] = None
    oxidized_public_url: str = ""


class ScanSettingsUpdate(BaseModel):
    scan_concurrency: int = 50
    discover_max_hosts: int = 4096
    discover_ping_workers: int = 100
    schedule_enabled: bool = False
    schedule_interval_hours: int = 24
    schedule_discover: bool = True
    ovn_user: str = "satcoadm"
    ovn_pass: Optional[str] = None
    us_user: str = "satcoadm"
    us_pass: Optional[str] = None


class BackupNotifyTestRequest(BaseModel):
    kind: str = "report"
    error_notify_telegram: Optional[bool] = None
    error_notify_email: Optional[bool] = None
    report_send_telegram: Optional[bool] = None
    report_send_email: Optional[bool] = None
    degrade_notify_telegram: Optional[bool] = None
    degrade_notify_email: Optional[bool] = None
    telegram_token: Optional[str] = None
    telegram_chat_notify: Optional[str] = None
    telegram_chat_report: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_ssl: Optional[bool] = None
    smtp_from: Optional[str] = None
    smtp_to_notify: Optional[str] = None
    smtp_to_report: Optional[str] = None
    error_notify_slack: Optional[bool] = None
    error_notify_teams: Optional[bool] = None
    report_send_slack: Optional[bool] = None
    report_send_teams: Optional[bool] = None
    degrade_notify_slack: Optional[bool] = None
    degrade_notify_teams: Optional[bool] = None
    compliance_report_slack: Optional[bool] = None
    compliance_report_teams: Optional[bool] = None
    slack_webhook_url: Optional[str] = None
    teams_webhook_url: Optional[str] = None


class IntegrationSettingsUpdate(BaseModel):
    snow_enabled: bool = False
    snow_instance_url: str = ""
    snow_username: str = ""
    snow_password: Optional[str] = None
    snow_assignment_group: str = ""
    jira_enabled: bool = False
    jira_url: str = ""
    jira_username: str = ""
    jira_api_token: Optional[str] = None
    jira_project_key: str = ""
    jira_issue_type: str = "Task"
    ticket_on_backup_failed: bool = True
    ticket_on_device_offline: bool = True
    ticket_cooldown_hours: int = 24
    audit_webhook_enabled: bool = False
    audit_webhook_url: str = ""
    audit_webhook_secret: Optional[str] = None
    audit_webhook_action_prefix: str = ""
    netbox_url: str = ""
    netbox_token: Optional[str] = None
    netbox_default_group: str = "default"
    librenms_url: str = ""
    librenms_token: Optional[str] = None
    librenms_default_group: str = "default"
    inventory_sync_enabled: bool = False
    inventory_sync_source: str = "netbox"
    inventory_sync_interval_hours: int = 24


class LdapTestResponse(BaseModel):
    ok: bool
    message: str
    role: Optional[str] = None


class BulkDeviceUpdate(BaseModel):
    names: list[str] = Field(min_length=1)
    enabled: Optional[bool] = None
    maintenance: Optional[bool] = None
    group: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: str = "viewer"
    permissions: list[str] = Field(default_factory=list)
    allowed_groups: list[str] = Field(default_factory=list)
    allowed_sites: list[str] = Field(default_factory=list)


class MikrotikRestoreRequest(BaseModel):
    type: str = Field(pattern=r"^(bin|rsc)$")
    file: str = Field(min_length=1, max_length=256)


class MikrotikBackupCompareRequest(BaseModel):
    type: str = Field(pattern=r"^(bin|rsc)$")
    file_a: str
    file_b: str


class TotpVerifyRequest(BaseModel):
    challenge: str
    code: str = ""
    recovery_code: str = ""


class TotpEnableRequest(BaseModel):
    secret: str
    code: str
    recovery_codes: list[str] = Field(default_factory=list)


class TotpDisableRequest(BaseModel):
    password: str
    code: str = ""
