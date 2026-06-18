from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_config_security_audit"),
    ]

    operations = [
        migrations.CreateModel(
            name="Site",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.CharField(db_index=True, max_length=128, unique=True)),
                ("name", models.CharField(default="", max_length=256)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="core.site",
                    ),
                ),
            ],
            options={
                "db_table": "sites",
                "ordering": ["slug"],
            },
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="inventory_sync_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="inventory_sync_interval_hours",
            field=models.PositiveIntegerField(default=24),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="inventory_sync_last_run_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="inventory_sync_source",
            field=models.CharField(default="netbox", max_length=16),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="librenms_default_group",
            field=models.CharField(default="default", max_length=64),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="librenms_token",
            field=models.CharField(blank=True, default="", max_length=256),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="librenms_url",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="netbox_default_group",
            field=models.CharField(default="default", max_length=64),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="netbox_token",
            field=models.CharField(blank=True, default="", max_length=256),
        ),
        migrations.AddField(
            model_name="integrationconfig",
            name="netbox_url",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
