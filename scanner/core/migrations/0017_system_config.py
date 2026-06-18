from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_stage3_sites_inventory"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("oxidized_engine", models.CharField(default="python", max_length=16)),
                ("oxidized_external_url", models.CharField(blank=True, default="http://oxidized:8888", max_length=512)),
                ("zabbix_auth_key", models.CharField(blank=True, default="", max_length=256)),
                ("zabbix_monitoring_enabled", models.BooleanField(default=True)),
                ("audit_retention_days", models.PositiveIntegerField(default=365)),
                ("metrics_enabled", models.BooleanField(default=True)),
                ("backup_data_dir", models.CharField(default="/data/backups", max_length=512)),
                ("access_token_expire_minutes", models.PositiveIntegerField(default=480)),
                ("behind_https_proxy", models.BooleanField(default=False)),
                ("task_worker_enabled", models.BooleanField(default=True)),
                ("task_worker_poll_sec", models.PositiveIntegerField(default=30)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "system_config",
            },
        ),
    ]
