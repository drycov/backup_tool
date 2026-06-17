from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_ldapconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackupConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("binary_enabled", models.BooleanField(default=True)),
                ("export_enabled", models.BooleanField(default=True)),
                ("hide_sensitive", models.BooleanField(default=False)),
                ("encrypt_password", models.CharField(blank=True, default="", max_length=256)),
                ("purge_enabled", models.BooleanField(default=True)),
                ("purge_keep", models.PositiveIntegerField(default=10)),
                ("bin_dir", models.CharField(default="/var/lib/oxidized/bin", max_length=512)),
                ("rsc_dir", models.CharField(default="/var/lib/oxidized/rsc", max_length=512)),
                ("backup_timeout", models.PositiveIntegerField(default=300)),
                ("error_notify_telegram", models.BooleanField(default=False)),
                ("error_notify_email", models.BooleanField(default=False)),
                ("report_send_telegram", models.BooleanField(default=False)),
                ("report_send_email", models.BooleanField(default=False)),
                ("telegram_token", models.CharField(blank=True, default="", max_length=256)),
                ("telegram_chat_notify", models.CharField(blank=True, default="", max_length=64)),
                ("telegram_chat_report", models.CharField(blank=True, default="", max_length=64)),
                ("smtp_server", models.CharField(blank=True, default="", max_length=256)),
                ("smtp_port", models.PositiveIntegerField(default=465)),
                ("smtp_user", models.CharField(blank=True, default="", max_length=256)),
                ("smtp_password", models.CharField(blank=True, default="", max_length=256)),
                ("smtp_ssl", models.BooleanField(default=True)),
                ("smtp_from", models.CharField(blank=True, default="", max_length=256)),
                ("smtp_to_notify", models.CharField(blank=True, default="", max_length=256)),
                ("smtp_to_report", models.CharField(blank=True, default="", max_length=256)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "backup_config"},
        ),
    ]
