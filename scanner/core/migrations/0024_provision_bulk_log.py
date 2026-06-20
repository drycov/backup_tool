from django.db import migrations

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_network_site_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="provisionbulkrun",
            name="log",
            field=core.models.LegacyJSONField(blank=True, default=list),
        ),
    ]
