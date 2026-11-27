from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0028_device_ai_enrichment")]
    operations = [
        migrations.CreateModel(
            name="BackupPolicyOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(max_length=16)),
                ("target", models.CharField(max_length=128)),
                ("values", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "backup_policy_overrides"},
        ),
        migrations.AddConstraint(model_name="backuppolicyoverride", constraint=models.UniqueConstraint(fields=["scope", "target"], name="backup_policy_scope_target")),
        migrations.CreateModel(
            name="ConfigChangeEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("commit_oid", models.CharField(max_length=64)),
                ("severity", models.CharField(db_index=True, max_length=16)),
                ("categories", models.JSONField(default=list)),
                ("added", models.PositiveIntegerField(default=0)),
                ("removed", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.device")),
            ],
            options={"db_table": "config_change_events"},
        ),
        migrations.AddConstraint(model_name="configchangeevent", constraint=models.UniqueConstraint(fields=["device", "commit_oid"], name="config_change_device_commit")),
    ]
