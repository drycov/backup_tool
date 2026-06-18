from django.db import migrations

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_system_config"),
    ]

    operations = [
        migrations.AlterField(
            model_name="backupconfig",
            name="maintenance_days",
            field=core.models.LegacyJSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="device",
            name="ports",
            field=core.models.LegacyJSONField(default=list),
        ),
        migrations.AlterField(
            model_name="user",
            name="allowed_groups",
            field=core.models.LegacyJSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="user",
            name="allowed_sites",
            field=core.models.LegacyJSONField(blank=True, default=list),
        ),
    ]
