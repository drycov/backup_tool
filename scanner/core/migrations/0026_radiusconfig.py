from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_integration_zabbix_api"),
    ]

    operations = [
        migrations.CreateModel(
            name="RadiusConfig",
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
                ("enabled", models.BooleanField(default=False)),
                ("server", models.CharField(blank=True, default="", max_length=512)),
                ("port", models.PositiveIntegerField(default=1812)),
                ("secret", models.CharField(blank=True, default="", max_length=256)),
                ("timeout", models.PositiveIntegerField(default=5)),
                ("retries", models.PositiveIntegerField(default=3)),
                ("nas_identifier", models.CharField(blank=True, default="", max_length=128)),
                ("role_attribute", models.CharField(default="Filter-Id", max_length=64)),
                ("admin_values", models.TextField(blank=True, default="")),
                ("operator_values", models.TextField(blank=True, default="")),
                ("default_role", models.CharField(default="viewer", max_length=32)),
                ("fallback_local", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "radius_config"},
        ),
    ]
