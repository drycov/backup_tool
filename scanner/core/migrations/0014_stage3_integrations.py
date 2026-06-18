from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_user_totp"),
    ]

    operations = [
        migrations.AddField(
            model_name="backupconfig",
            name="compliance_report_slack",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="compliance_report_teams",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="degrade_notify_slack",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="degrade_notify_teams",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="error_notify_slack",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="error_notify_teams",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="report_send_slack",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="report_send_teams",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="slack_webhook_url",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="teams_webhook_url",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.CreateModel(
            name="IntegrationConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snow_enabled", models.BooleanField(default=False)),
                ("snow_instance_url", models.CharField(blank=True, default="", max_length=512)),
                ("snow_username", models.CharField(blank=True, default="", max_length=128)),
                ("snow_password", models.CharField(blank=True, default="", max_length=256)),
                ("snow_assignment_group", models.CharField(blank=True, default="", max_length=128)),
                ("jira_enabled", models.BooleanField(default=False)),
                ("jira_url", models.CharField(blank=True, default="", max_length=512)),
                ("jira_username", models.CharField(blank=True, default="", max_length=128)),
                ("jira_api_token", models.CharField(blank=True, default="", max_length=256)),
                ("jira_project_key", models.CharField(blank=True, default="", max_length=32)),
                ("jira_issue_type", models.CharField(default="Task", max_length=64)),
                ("ticket_on_backup_failed", models.BooleanField(default=True)),
                ("ticket_on_device_offline", models.BooleanField(default=True)),
                ("ticket_cooldown_hours", models.PositiveIntegerField(default=24)),
                ("audit_webhook_enabled", models.BooleanField(default=False)),
                ("audit_webhook_url", models.CharField(blank=True, default="", max_length=512)),
                ("audit_webhook_secret", models.CharField(blank=True, default="", max_length=256)),
                ("audit_webhook_action_prefix", models.CharField(blank=True, default="", max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "integration_config",
            },
        ),
    ]
