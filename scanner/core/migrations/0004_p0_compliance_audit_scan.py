from django.db import migrations, models

import core.models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_backupconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="backupconfig",
            name="alert_cooldown_hours",
            field=models.PositiveIntegerField(default=24),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="degrade_notify_email",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="degrade_notify_telegram",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="stale_days_threshold",
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.CreateModel(
            name="ScanRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_id", models.CharField(blank=True, default="", max_length=32)),
                ("discover", models.BooleanField(default=False)),
                ("status", models.CharField(default="completed", max_length=16)),
                ("total", models.PositiveIntegerField(default=0)),
                ("online", models.PositiveIntegerField(default=0)),
                ("offline", models.PositiveIntegerField(default=0)),
                ("partial", models.PositiveIntegerField(default=0)),
                ("scanned_at", models.DateTimeField(db_index=True)),
                ("error", models.TextField(blank=True, default="")),
                ("results_json", core.models.LegacyJSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "scan_runs", "ordering": ["-scanned_at"]},
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=64)),
                ("action", models.CharField(db_index=True, max_length=64)),
                ("target", models.CharField(blank=True, default="", max_length=256)),
                ("detail", models.TextField(blank=True, default="")),
                ("ip_address", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"db_table": "audit_events", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="AlertState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alert_key", models.CharField(db_index=True, max_length=128, unique=True)),
                ("last_notified_at", models.DateTimeField()),
                ("device_count", models.PositiveIntegerField(default=0)),
            ],
            options={"db_table": "alert_states"},
        ),
    ]
