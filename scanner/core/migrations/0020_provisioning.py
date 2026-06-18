from django.db import migrations, models

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_custom_roles_scope_locked"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProvisionTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.CharField(db_index=True, max_length=64, unique=True)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True, default="")),
                ("model", models.CharField(db_index=True, default="routeros", max_length=64)),
                ("body", models.TextField()),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "provision_templates",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ProvisionRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("template_slug", models.CharField(blank=True, default="", max_length=64)),
                ("device_name", models.CharField(db_index=True, max_length=128)),
                ("device_ip", models.CharField(blank=True, default="", max_length=64)),
                ("device_model", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(db_index=True, default="pending", max_length=16)),
                ("dry_run", models.BooleanField(default=False)),
                ("rendered_config", models.TextField(blank=True, default="")),
                ("output", models.TextField(blank=True, default="")),
                ("error", models.TextField(blank=True, default="")),
                ("triggered_by", models.CharField(blank=True, default="", max_length=64)),
                ("correlation_id", models.CharField(blank=True, default="", max_length=64)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "template",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="runs",
                        to="core.provisiontemplate",
                    ),
                ),
            ],
            options={
                "db_table": "provision_runs",
                "ordering": ["-created_at"],
            },
        ),
    ]
