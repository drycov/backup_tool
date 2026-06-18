from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_platform_features"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="maintenance",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="maintenance_window_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="maintenance_start_hour_utc",
            field=models.PositiveSmallIntegerField(default=22),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="maintenance_end_hour_utc",
            field=models.PositiveSmallIntegerField(default=6),
        ),
        migrations.AddField(
            model_name="backupconfig",
            name="maintenance_days",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="user",
            name="allowed_groups",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="user",
            name="allowed_sites",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
