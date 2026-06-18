from django.db import migrations, models

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_task_queue_observability"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="tags",
            field=core.models.LegacyJSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="ldapconfig",
            name="scope_mappings",
            field=core.models.LegacyJSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="ApiKey",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=64, unique=True)),
                ("key_prefix", models.CharField(max_length=16)),
                ("key_hash", models.CharField(max_length=128)),
                ("role", models.CharField(default="viewer", max_length=32)),
                (
                    "permissions",
                    core.models.LegacyJSONField(blank=True, default=list),
                ),
                (
                    "allowed_groups",
                    core.models.LegacyJSONField(blank=True, default=list),
                ),
                (
                    "allowed_sites",
                    core.models.LegacyJSONField(blank=True, default=list),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "api_keys",
                "ordering": ["name"],
            },
        ),
    ]
