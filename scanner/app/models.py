from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


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


class DeviceCreate(BaseModel):
    name: str
    ip: str
    model: str = "routeros"
    group: str = "default"
    enabled: bool = True
    ports: list[int] = Field(default_factory=lambda: [44333])


class CredentialProfile(BaseModel):
    name: str
    group_name: str
    username: str
    password: str


class CredentialProfileUpdate(BaseModel):
    username: str
    password: str


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


class AuthUserResponse(BaseModel):
    id: int
    username: str
    role: str
    permissions: list[str]


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
