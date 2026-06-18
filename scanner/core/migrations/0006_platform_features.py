from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_git_scan_settings_ui"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="critical",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="device",
            name="role",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="device",
            name="site",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="compliance_report_email",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="compliance_report_hour_utc",
            field=models.PositiveSmallIntegerField(default=7),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="compliance_report_last_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="compliance_report_telegram",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="degrade_webhook_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="degrade_webhook_url",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.CreateModel(
            name="GroupPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group_name", models.CharField(db_index=True, max_length=64, unique=True)),
                ("backup_interval_sec", models.PositiveIntegerField(default=0)),
                ("model", models.CharField(blank=True, default="", max_length=64)),
                ("mk_binary_enabled", models.BooleanField(blank=True, null=True)),
                ("mk_export_enabled", models.BooleanField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "group_policies"},
        ),
    ]
