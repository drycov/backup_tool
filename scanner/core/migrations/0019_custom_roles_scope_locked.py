from django.db import migrations, models

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_legacy_json_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.CharField(db_index=True, max_length=64, unique=True)),
                ("label", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True, default="")),
                ("permissions", core.models.LegacyJSONField(blank=True, default=list)),
                ("is_system", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "custom_roles",
                "ordering": ["slug"],
            },
        ),
        migrations.AddField(
            model_name="user",
            name="scope_locked",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="custom_role",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="users",
                to="core.customrole",
            ),
        ),
    ]
