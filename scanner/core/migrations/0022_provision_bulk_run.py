from django.db import migrations, models

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_provision_template_generated"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProvisionBulkRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("template_slug", models.CharField(blank=True, default="", max_length=64)),
                ("scope_group", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("scope_site", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("scope_model", models.CharField(blank=True, default="", max_length=64)),
                ("dry_run", models.BooleanField(default=True)),
                ("exclude_complex", models.BooleanField(default=False)),
                ("status", models.CharField(db_index=True, default="queued", max_length=16)),
                ("triggered_by", models.CharField(blank=True, default="", max_length=64)),
                ("correlation_id", models.CharField(blank=True, default="", max_length=64)),
                ("background_task_id", models.PositiveIntegerField(blank=True, null=True)),
                ("devices_total", models.PositiveIntegerField(default=0)),
                ("devices_completed", models.PositiveIntegerField(default=0)),
                ("devices_failed", models.PositiveIntegerField(default=0)),
                ("results", core.models.LegacyJSONField(blank=True, default=list)),
                ("error", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "template",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="bulk_runs",
                        to="core.provisiontemplate",
                    ),
                ),
            ],
            options={
                "db_table": "provision_bulk_runs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="provisionrun",
            name="bulk_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="device_runs",
                to="core.provisionbulkrun",
            ),
        ),
    ]
