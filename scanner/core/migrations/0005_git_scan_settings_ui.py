from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_p0_compliance_audit_scan"),
    ]

    operations = [
        migrations.AddField(
            model_name="backupconfig",
            name="degrade_check_interval_sec",
            field=models.PositiveIntegerField(default=3600),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="mk_backup_git_push",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="GitConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("git_remote_url", models.CharField(blank=True, default="", max_length=512)),
                ("gitea_token", models.CharField(blank=True, default="", max_length=256)),
                ("gitea_http_user", models.CharField(default="oauth2", max_length=64)),
                ("git_commit_user", models.CharField(default="Oxidized", max_length=128)),
                ("git_commit_email", models.CharField(default="oxidized@localhost", max_length=256)),
                ("git_branch", models.CharField(default="main", max_length=64)),
                ("oxidized_source_token", models.CharField(blank=True, default="", max_length=256)),
                ("oxidized_public_url", models.CharField(blank=True, default="", max_length=512)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "git_config"},
        ),
        migrations.CreateModel(
            name="ScanConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scan_concurrency", models.PositiveIntegerField(default=50)),
                ("discover_max_hosts", models.PositiveIntegerField(default=4096)),
                ("discover_ping_workers", models.PositiveIntegerField(default=100)),
                ("ovn_user", models.CharField(default="satcoadm", max_length=128)),
                ("ovn_pass", models.CharField(blank=True, default="", max_length=256)),
                ("us_user", models.CharField(default="satcoadm", max_length=128)),
                ("us_pass", models.CharField(blank=True, default="", max_length=256)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "scan_config"},
        ),
    ]
