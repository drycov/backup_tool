from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_stage3_integrations"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConfigAuditRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(db_index=True, default="completed", max_length=16)),
                ("triggered_by", models.CharField(default="system", max_length=64)),
                ("devices_total", models.PositiveIntegerField(default=0)),
                ("devices_scanned", models.PositiveIntegerField(default=0)),
                ("devices_skipped", models.PositiveIntegerField(default=0)),
                ("findings_count", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "config_audit_runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="ConfigFinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_name", models.CharField(db_index=True, max_length=128)),
                ("device_ip", models.CharField(blank=True, default="", max_length=64)),
                ("device_model", models.CharField(blank=True, default="", max_length=64)),
                ("device_group", models.CharField(blank=True, default="", max_length=64)),
                ("device_site", models.CharField(blank=True, default="", max_length=128)),
                ("rule_id", models.CharField(db_index=True, max_length=64)),
                ("category", models.CharField(db_index=True, default="hardening", max_length=32)),
                ("severity", models.CharField(db_index=True, max_length=16)),
                ("title", models.CharField(max_length=256)),
                ("evidence", models.TextField(blank=True, default="")),
                ("line_number", models.PositiveIntegerField(blank=True, null=True)),
                ("remediation", models.TextField(blank=True, default="")),
                ("acknowledged", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="findings",
                        to="core.configauditrun",
                    ),
                ),
            ],
            options={
                "db_table": "config_findings",
                "ordering": ["-severity", "device_name"],
                "indexes": [
                    models.Index(fields=["run", "severity"], name="config_find_run_sev_idx"),
                    models.Index(fields=["device_name", "rule_id"], name="config_find_dev_rule_idx"),
                ],
            },
        ),
    ]
