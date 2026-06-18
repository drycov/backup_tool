from django.db import migrations, models

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_provisioning"),
    ]

    operations = [
        migrations.AddField(
            model_name="provisiontemplate",
            name="meta",
            field=core.models.LegacyJSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="provisiontemplate",
            name="scope_group",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="provisiontemplate",
            name="scope_site",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="provisiontemplate",
            name="source",
            field=models.CharField(db_index=True, default="manual", max_length=16),
        ),
    ]
