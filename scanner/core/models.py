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
