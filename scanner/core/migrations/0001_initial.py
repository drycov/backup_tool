# Generated manually for existing PostgreSQL schema compatibility

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CredentialProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=64, unique=True)),
                ("group_name", models.CharField(db_index=True, max_length=64)),
                ("username", models.CharField(default="admin", max_length=128)),
                ("password", models.CharField(default="changeme", max_length=256)),
            ],
            options={"db_table": "credential_profiles"},
        ),
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=128, unique=True)),
                ("ip", models.CharField(max_length=64)),
                ("model", models.CharField(default="routeros", max_length=64)),
                ("group", models.CharField(default="default", max_length=64)),
                ("enabled", models.BooleanField(default=True)),
                ("ports", models.JSONField(default=list)),
            ],
            options={"db_table": "devices"},
        ),
        migrations.CreateModel(
            name="Network",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("network", models.CharField(db_index=True, max_length=64)),
                ("group_name", models.CharField(db_index=True, default="default", max_length=64)),
                ("environment_name", models.CharField(blank=True, max_length=128, null=True)),
                ("gateway", models.CharField(blank=True, max_length=64, null=True)),
            ],
            options={"db_table": "networks"},
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=64, unique=True)),
                ("password_hash", models.CharField(max_length=256)),
                ("role", models.CharField(default="viewer", max_length=32)),
                ("is_active", models.BooleanField(default=True)),
                ("auth_source", models.CharField(default="local", max_length=16)),
                ("created_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "users"},
        ),
    ]
